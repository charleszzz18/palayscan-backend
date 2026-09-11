# ==========================================
# RICE HEALTH APP - VECTORIZED IMAGE COMPARISON MODULE (image_comparison.py)
# ==========================================
# Compares user uploaded images against 13,480 reference dataset fingerprints
# using pre-stacked NumPy matrices and sub-millisecond vectorized cosine similarity.

import cv2
import numpy as np
import os
import sys
import pickle
import glob
import re
from pathlib import Path

class ImageComparison:
    NAME_MAP = {
        "blight":             "Blight",
        "blast":              "Blast",
        "brown spot":         "Brown Spot",
        "brownspot":          "Brown Spot",
        "rust":               "Rust",
        "leaf strip":         "Leaf Strip",
        "leaf streak":        "Leaf Strip",
        "leafstrip":          "Leaf Strip",
        "healthy":            "Healthy",
    }

    def __init__(self, reference_dir, cache_file="fingerprints.pkl"):
        self.reference_dir = reference_dir
        self.cache_file = cache_file
        self.matrices = {}       # {disease_name: np.ndarray of shape (N, 196)}
        self.counts = {}         # {disease_name: int}
        self.reference_images = {} # Backward-compatibility alias
        self.load_reference_images()

    def _normalize_disease_name(self, raw_name):
        cleaned = re.sub(r'[_ \-]\d+$', '', raw_name).strip().lower()
        return self.NAME_MAP.get(cleaned, raw_name.strip().title())

    def _extract_features(self, img):
        """
        Extracts 196-dimensional, L2-normalized feature representation:
        - 96 global HSV histogram features
        - 96 lesion-specific HSV histogram features
        - 4 structural & edge metrics (std_dev, edge_density, laplacian_var, lesion_ratio)
        """
        if img is None or img.size == 0:
            return np.zeros(196, dtype=np.float32)

        img_256 = cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(img_256, cv2.COLOR_BGR2HSV)

        # 1. Global HSV histograms (32 bins each)
        h_glob = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
        s_glob = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
        v_glob = cv2.calcHist([hsv], [2], None, [32], [0, 256]).flatten()

        # 2. Lesion Mask (detect necrotic / discolored tissue vs healthy green)
        h_chan, s_chan, v_chan = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        green_mask = (h_chan >= 35) & (h_chan <= 88) & (s_chan >= 40) & (v_chan >= 30)
        lesion_mask = (~green_mask) & (v_chan >= 20)
        lesion_mask_uint8 = (lesion_mask * 255).astype(np.uint8)
        lesion_ratio = float(np.count_nonzero(lesion_mask) / (256 * 256))

        if np.count_nonzero(lesion_mask) > 50:
            h_lesion = cv2.calcHist([hsv], [0], lesion_mask_uint8, [32], [0, 180]).flatten()
            s_lesion = cv2.calcHist([hsv], [1], lesion_mask_uint8, [32], [0, 256]).flatten()
            v_lesion = cv2.calcHist([hsv], [2], lesion_mask_uint8, [32], [0, 256]).flatten()
        else:
            h_lesion = np.zeros(32, dtype=np.float32)
            s_lesion = np.zeros(32, dtype=np.float32)
            v_lesion = np.zeros(32, dtype=np.float32)

        # 3. Structural & Edge features
        gray = cv2.cvtColor(img_256, cv2.COLOR_BGR2GRAY)
        std_dev = float(np.std(gray)) / 128.0
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges) / (256 * 256))
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 1000.0

        def norm_vec(v):
            n = np.linalg.norm(v)
            return (v / n) if n > 1e-6 else v

        glob_vec = norm_vec(np.concatenate([h_glob, s_glob, v_glob]))
        lesion_vec = norm_vec(np.concatenate([h_lesion, s_lesion, v_lesion]))
        struct_vec = np.array([std_dev, edge_density, laplacian_var, lesion_ratio], dtype=np.float32)

        composite = np.concatenate([glob_vec * 0.45, lesion_vec * 0.45, struct_vec * 0.10]).astype(np.float32)
        return norm_vec(composite)

    def load_reference_images(self):
        """
        Loads pre-computed matrix fingerprints from cache file (v2.0 vectorized),
        or falls back to extracting directly from dataset.
        """
        cache_path = self.cache_file
        if not os.path.isabs(cache_path):
            cache_path = os.path.join(os.path.dirname(__file__), cache_path)

        if os.path.exists(cache_path):
            print(f"[ImageComparison] Loading pre-computed fingerprints from {cache_path}...")
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)

                if isinstance(data, dict) and 'matrices' in data:
                    # Version 2.0 vectorized matrix format
                    self.matrices = data['matrices']
                    self.counts = data.get('counts', {k: len(v) for k, v in self.matrices.items()})
                    total = sum(self.counts.values())
                    print(f"[ImageComparison] Loaded {total} vectorized fingerprints across {len(self.matrices)} classes.")
                    self.reference_images = {k: list(range(v)) for k, v in self.counts.items()}
                    return
                elif isinstance(data, dict):
                    # Legacy v1 format (dict of lists)
                    self.reference_images = data
                    self.counts = {k: len(v) for k, v in data.items()}
                    print(f"[ImageComparison] Loaded legacy cache with {sum(self.counts.values())} entries.")
                    return
            except Exception as e:
                print(f"[ImageComparison] Error loading cache: {e}. Falling back to generation.")

        # If cache not found, run extractor automatically
        try:
            from generate_fingerprints import build_all_fingerprints
            if build_all_fingerprints():
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                self.matrices = data['matrices']
                self.counts = data.get('counts', {k: len(v) for k, v in self.matrices.items()})
                self.reference_images = {k: list(range(v)) for k, v in self.counts.items()}
        except Exception as e:
            print(f"[ImageComparison] Automatic build failed: {e}")

    def compare_image(self, img):
        """
        Performs sub-millisecond vectorized k-NN search across all reference images.
        Computes cosine similarity against entire dataset matrix in a single dot-product.
        Returns: list of (disease_name, score) sorted descending.
        """
        if not self.matrices:
            return []

        q = self._extract_features(img)
        results = []

        for name, mat in self.matrices.items():
            if name.lower() == 'healthy':
                continue  # 'Healthy' evaluated separately in health scoring

            # Vectorized Cosine Similarity: (N, 196) . (196,) -> (N,)
            sims = np.dot(mat, q)
            if len(sims) == 0:
                continue

            # Top-15 nearest neighbors with rank-decay weighting for high precision
            k = min(15, len(sims))
            # Partition top k values efficiently
            top_k_indices = np.argpartition(sims, -k)[-k:]
            top_k_sims = np.sort(sims[top_k_indices])[::-1]

            # Linear decay weighting: 1.0 down to 0.60
            weights = np.linspace(1.0, 0.60, k)
            weighted_score = float(np.dot(top_k_sims, weights) / np.sum(weights))
            results.append((name, weighted_score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_matching_diseases(self, img, threshold=0.30, max_matches=3):
        """
        Returns list of diseases that crossed a minimum confidence bar.
        """
        similarities = self.compare_image(img)
        matches = [(d, s) for d, s in similarities if s >= threshold]
        return matches[:max_matches]

    def get_stats(self):
        """
        Returns summary of image counts per disease category.
        """
        return self.counts