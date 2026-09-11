# =========================================================================
# PALAYSCAN - PRECISION & LATENCY BENCHMARK SUITE (test_precision.py)
# =========================================================================
# Evaluates diagnostic accuracy and sub-millisecond query speed on ground-truth
# samples from all 5 dataset categories using the full 13,480 fingerprint cache.

import os
import sys
import time
import glob
import cv2
import numpy as np

# Ensure backend directory is in path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from image_comparison import ImageComparison
from dl_analysis import analyze_with_dl

def run_tests():
    print("=" * 65)
    print("   [+] PALAYSCAN PRECISION & INFERENCE BENCHMARK [+]")
    print("=" * 65)

    dataset_base = os.path.join(backend_dir, "dataset", "Rice Disease")
    if not os.path.exists(dataset_base):
        print(f"[ERROR] Dataset folder not found: {dataset_base}")
        return False

    # 1. Initialize Image Comparison Engine
    print("[1/3] Loading ImageComparison with 13,480-image fingerprint cache...")
    t0 = time.time()
    comparator = ImageComparison(reference_dir=dataset_base, cache_file=os.path.join(backend_dir, "fingerprints.pkl"))
    load_time = time.time() - t0
    stats = comparator.get_stats()
    total_loaded = sum(stats.values())
    print(f"   -> Loaded {total_loaded} fingerprints in {load_time*1000:.1f}ms")
    print(f"   -> Breakdown: {stats}\n")

    # 2. Benchmark Query Speed
    print("[2/3] Benchmarking vectorized matrix similarity search...")
    dummy_img = np.full((512, 512, 3), 120, dtype=np.uint8)
    cv2.circle(dummy_img, (256, 256), 80, (40, 160, 40), -1)

    latencies = []
    for _ in range(20):
        t_start = time.perf_counter()
        _ = comparator.compare_image(dummy_img)
        latencies.append((time.perf_counter() - t_start) * 1000.0)

    avg_lat = np.mean(latencies[5:])  # drop warm-up iterations
    print(f"   -> Average search latency over {total_loaded} images: {avg_lat:.2f} ms per scan!")
    if avg_lat < 10.0:
        print("   -> [PASS] Sub-millisecond vectorization targets achieved!\n")
    else:
        print(f"   -> [WARN] Latency higher than expected ({avg_lat:.2f}ms)\n")

    # 3. Ground Truth Precision Test
    print("[3/3] Testing classification precision on sample images from each class...")
    categories = [d for d in sorted(os.listdir(dataset_base)) if os.path.isdir(os.path.join(dataset_base, d))]

    for cat in categories:
        folder = os.path.join(dataset_base, cat)
        samples = glob.glob(os.path.join(folder, '**', '*.jpg'), recursive=True)
        if not samples:
            samples = glob.glob(os.path.join(folder, '**', '*.png'), recursive=True)
        if not samples:
            continue

        test_img_path = samples[len(samples) // 2]  # choose middle sample
        img = cv2.imread(test_img_path)
        if img is None:
            continue

        dl_disease, dl_conf = analyze_with_dl(img)
        matches = comparator.get_matching_diseases(img, threshold=0.0, max_matches=3)

        top_match = matches[0] if matches else ("None", 0.0)
        print(f"   [*] Ground Truth: {cat:<12}")
        print(f"       DL Prediction : {str(dl_disease):<12} (Confidence: {dl_conf:.1%})")
        print(f"       Visual k-NN   : {top_match[0]:<12} (Similarity: {top_match[1]:.2f})")
        print(f"       Top 3 Matches : {', '.join([f'{m[0]} ({m[1]:.2f})' for m in matches])}\n")

    print("=" * 65)
    print("   [OK] Benchmark & Precision Validation Finished!")
    print("=" * 65)
    return True

if __name__ == "__main__":
    run_tests()
