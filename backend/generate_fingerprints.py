# =========================================================================
# PALAYSCAN - HIGH-PRECISION FINGERPRINT GENERATOR (generate_fingerprints.py)
# =========================================================================
# Extracts multi-dimensional visual fingerprints (global color, lesion-specific
# color, and texture/edge morphometry) for ALL dataset images without artificial caps.
# Saves pre-stacked normalized NumPy matrices for sub-millisecond k-NN matching.
# =========================================================================

import os
import sys
import glob
import time
import pickle
import re
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BACKEND_DIR, "dataset", "Rice Disease")
CACHE_FILE  = os.path.join(BACKEND_DIR, "fingerprints.pkl")

# Standardized Disease Mapping
NAME_MAP = {
    "blight":             "Blight",
    "blast":              "Blast",
    "brown spot":         "Brown Spot",
    "brownspot":          "Brown Spot",
    "leaf strip":         "Leaf Strip",
    "leaf streak":        "Leaf Strip",
    "leafstrip":          "Leaf Strip",
    "healthy":            "Healthy",
}

def normalize_name(raw):
    cleaned = re.sub(r'[_ \-]\d+$', '', raw).strip().lower()
    return NAME_MAP.get(cleaned, raw.strip().title())

def extract_features(img):
    """
    Extracts high-dimensional, L2-normalized feature representation:
    1. Global HSV Histograms: H (32), S (32), V (32) = 96 features
    2. Lesion-specific HSV Histograms: H (32), S (32), V (32) = 96 features
    3. Structural & Edge Metrics: std_dev, edge_density, contrast, lesion_ratio = 4 features
    Total vector dimension: 196 floats.
    """
    if img is None or img.size == 0:
        return None

    # Resize to standard analysis canvas (256x256)
    img_256 = cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(img_256, cv2.COLOR_BGR2HSV)

    # 1. Global HSV histograms (32 bins each)
    h_glob = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
    s_glob = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
    v_glob = cv2.calcHist([hsv], [2], None, [32], [0, 256]).flatten()

    # 2. Lesion Mask (detect necrotic / discolored tissue vs healthy green)
    # Healthy green: H in [35, 88], S in [40, 255], V in [30, 255]
    h_chan, s_chan, v_chan = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    green_mask = (h_chan >= 35) & (h_chan <= 88) & (s_chan >= 40) & (v_chan >= 30)
    lesion_mask = (~green_mask) & (v_chan >= 20)  # non-green, non-black pixels
    lesion_mask_uint8 = (lesion_mask * 255).astype(np.uint8)
    lesion_ratio = float(np.count_nonzero(lesion_mask) / (256 * 256))

    if np.count_nonzero(lesion_mask) > 50:
        h_lesion = cv2.calcHist([hsv], [0], lesion_mask_uint8, [32], [0, 180]).flatten()
        s_lesion = cv2.calcHist([hsv], [1], lesion_mask_uint8, [32], [0, 256]).flatten()
        v_lesion = cv2.calcHist([hsv], [2], lesion_mask_uint8, [32], [0, 256]).flatten()
    else:
        # If image is almost purely healthy green, lesion hist is zeros
        h_lesion = np.zeros(32, dtype=np.float32)
        s_lesion = np.zeros(32, dtype=np.float32)
        v_lesion = np.zeros(32, dtype=np.float32)

    # 3. Structural & Edge features
    gray = cv2.cvtColor(img_256, cv2.COLOR_BGR2GRAY)
    std_dev = float(np.std(gray)) / 128.0
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.count_nonzero(edges) / (256 * 256))
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 1000.0

    # Assemble and normalize sub-vectors
    def norm_vec(v):
        n = np.linalg.norm(v)
        return (v / n) if n > 1e-6 else v

    glob_vec = norm_vec(np.concatenate([h_glob, s_glob, v_glob]))
    lesion_vec = norm_vec(np.concatenate([h_lesion, s_lesion, v_lesion]))
    struct_vec = np.array([std_dev, edge_density, laplacian_var, lesion_ratio], dtype=np.float32)

    # Weighted composite vector: Global (0.45) + Lesion (0.45) + Structure (0.10)
    composite = np.concatenate([glob_vec * 0.45, lesion_vec * 0.45, struct_vec * 0.10]).astype(np.float32)
    composite = norm_vec(composite)

    return composite

def process_image(img_path):
    try:
        img = cv2.imread(img_path)
        if img is None:
            return None
        return extract_features(img)
    except Exception:
        return None

def build_all_fingerprints():
    print("=" * 65)
    print("   PALAYSCAN FULL-DATASET FINGERPRINT GENERATOR")
    print("=" * 65)

    if not os.path.exists(DATASET_DIR):
        print(f"[ERROR] Dataset directory not found: {DATASET_DIR}")
        return False

    classes = [d for d in sorted(os.listdir(DATASET_DIR)) if os.path.isdir(os.path.join(DATASET_DIR, d))]
    print(f"[INFO] Found {len(classes)} disease categories: {classes}\n")

    # Collect all image paths per disease
    dataset_files = {}
    total_found = 0
    for cls in classes:
        disease_name = normalize_name(cls)
        folder = os.path.join(DATASET_DIR, cls)
        paths = []
        for ext in ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG'):
            paths += glob.glob(os.path.join(folder, '**', ext), recursive=True)
        paths = sorted(list(set(paths)))
        dataset_files[disease_name] = paths
        total_found += len(paths)
        print(f"   - {disease_name:<12}: {len(paths):>5} images")

    print(f"\n[INFO] Total images to process: {total_found}")
    print("[INFO] Utilizing multi-threaded CPU pool for maximum speed...\n")

    start_time = time.time()
    extracted_data = {}  # {disease: np.ndarray of shape (N, 196)}
    metadata = {}

    num_workers = min(16, max(4, (os.cpu_count() or 4) * 2))

    for disease_name, paths in dataset_files.items():
        if not paths:
            continue
        print(f"[*] Processing '{disease_name}' ({len(paths)} images)...", flush=True)
        vectors = []
        cls_start = time.time()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            results = executor.map(process_image, paths)
            for vec in results:
                if vec is not None:
                    vectors.append(vec)

        if vectors:
            mat = np.vstack(vectors).astype(np.float32)
            extracted_data[disease_name] = mat
            metadata[disease_name] = len(vectors)
            elapsed_cls = time.time() - cls_start
            print(f"    -> Extracted {len(vectors)}/{len(paths)} fingerprints in {elapsed_cls:.1f}s ({len(vectors)/max(elapsed_cls, 0.01):.0f} imgs/s)")

    total_extracted = sum(metadata.values())
    total_elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print(f"   Extraction Complete! {total_extracted}/{total_found} fingerprints in {total_elapsed:.1f}s")
    print("=" * 65)

    # Save to fingerprints.pkl
    cache_payload = {
        'version': 2.0,
        'matrices': extracted_data,
        'counts': metadata,
        'timestamp': time.time(),
        'feature_dim': 196
    }

    print(f"[INFO] Writing to {CACHE_FILE}...")
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump(cache_payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    file_size_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
    print(f"[SUCCESS] Saved {CACHE_FILE} ({file_size_mb:.2f} MB)")
    print(f"[SUMMARY] Breakdown:")
    for k, v in metadata.items():
        print(f"   - {k:<12}: {v:>5} fingerprints")
    print("=" * 65 + "\n")
    return True

if __name__ == "__main__":
    build_all_fingerprints()
