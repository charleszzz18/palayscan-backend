# ==========================================
# RICE HEALTH APP - IMAGE COMPARISON MODULE
# ==========================================
# This file takes the user's uploaded image and compares it against
# a folder of known disease reference images to find the closest match.

import cv2 # Computer Vision library | CHANGE: Update if using a different image processing library
import numpy as np # Numerical math library | CHANGE: Standard dependency
import os # System path library | CHANGE: Standard dependency
import sys
import pickle
import glob # Filename pattern matching | CHANGE: Standard dependency
import re # Regular expression library | CHANGE: Use for name cleaning
from pathlib import Path # Path object management | CHANGE: Modern way to handle file paths
from concurrent.futures import ThreadPoolExecutor # Parallel processing | CHANGE: Remove for low-power systems

class ImageComparison: # Core AI comparison class | CHANGE: Rename if adding non-image comparison features
    def __init__(self, reference_dir, cache_file="fingerprints.pkl"):
        """
        Initializes the ImageComparison object and loads ALL reference images.
        """
        self.reference_dir = reference_dir # Store the root path of the reference dataset
        self.cache_file = cache_file # Path to save/load pre-computed features
        self.reference_images = {} # Dictionary to store disease names and their corresponding image fingerprints
        self.load_reference_images() # Trigger the initial data loading process

    # ------------------------------------------------------------------
    # DISEASE NAME NORMALIZATION MAP
    # ------------------------------------------------------------------
    # Maps any folder name or filename to the official database name.
    # ------------------------------------------------------------------
    NAME_MAP = { # Translation table for standardizing disease folder names
        "blight":             "Blight",
        "blast":              "Blast",
        "brown spot":         "Brown Spot",
        "rust":               "Rust",
        "leaf strip":         "Leaf Strip",
        "healthy":            "Healthy",
    }

    def _normalize_disease_name(self, raw_name): # Clean up messy names | CHANGE: Add advanced regex for specific filenames
        """
        Converts folder names into official database names.
        """
        cleaned = re.sub(r'[_ \-]\d+$', '', raw_name).strip() # Use Regex to strip trailing numbers from folder names
        lower = cleaned.lower() # Convert name to lowercase for case-insensitive matching
        if lower in self.NAME_MAP: # Check if the cleaned name exists in our mapping table
            return self.NAME_MAP[lower] # Return the mapped official name
        return cleaned.title() # Default to title case if no mapping is found | CHANGE: Return 'Unknown' instead of raw name

    def load_reference_images(self):
        """
        Scans the reference directory and extracts fingerprints from all images,
        or loads them directly from a cache file if it exists.
        """
        # 1. Try to load from cache first
        if self.cache_file and os.path.exists(self.cache_file):
            print(f"[ImageComparison] Loading pre-computed fingerprints from {self.cache_file}...")
            try:
                with open(self.cache_file, 'rb') as f:
                    self.reference_images = pickle.load(f)
                count = sum(len(v) for v in self.reference_images.values())
                print(f"[ImageComparison] Loaded {count} fingerprints from cache.")
                return # Skip image processing!
            except Exception as e:
                print(f"[ImageComparison] Error loading cache: {e}. Falling back to image processing.")
                self.reference_images = {}

        # 2. If no cache, process images from dataset directory
        actual_dir = self.reference_dir
        if not os.path.exists(actual_dir):
            print(f"[ImageComparison] WARNING: Reference directory not found: {self.reference_dir}")
            return

        # Auto-detect if disease classes are nested inside a subfolder (e.g. dataset/Rice Disease/...)
        sub_dir = os.path.join(actual_dir, "Rice Disease")
        if os.path.exists(sub_dir) and os.path.isdir(sub_dir):
            actual_dir = sub_dir

        total_loaded = 0
        for entry in os.scandir(actual_dir):
            if entry.is_dir():
                disease_name = self._normalize_disease_name(entry.name)
                sub_images = []
                for ext in ('*.jpg', '*.jpeg', '*.png'):
                    sub_images += glob.glob(os.path.join(entry.path, '**', ext), recursive=True)
                if not sub_images:
                    continue
                
                # Sample up to 50 reference images per disease for ultra-fast comparison
                MAX_PER_DISEASE = 50
                if len(sub_images) > MAX_PER_DISEASE:
                    stride = max(1, len(sub_images) // MAX_PER_DISEASE)
                    sub_images = sub_images[::stride][:MAX_PER_DISEASE]
                
                if disease_name not in self.reference_images:
                    self.reference_images[disease_name] = []
                for img_path in sub_images:
                    img = cv2.imread(img_path)
                    if img is not None:
                        self.reference_images[disease_name].append(self._extract_features(img))
                        total_loaded += 1

        print(f"[ImageComparison] Loaded {total_loaded} images.")
        
        # 3. Save newly extracted features to cache
        if self.cache_file and self.reference_images:
            print(f"[ImageComparison] Saving fingerprints to {self.cache_file}...")
            try:
                with open(self.cache_file, 'wb') as f:
                    pickle.dump(self.reference_images, f)
                print("[ImageComparison] Fingerprints saved successfully.")
            except Exception as e:
                print(f"[ImageComparison] Error saving cache: {e}")

    def _extract_features(self, img):
        """
        Converts an image into a numerical summary of colors and textures.
        Outputs pure Python types for universal NumPy 1.x / 2.x pickle compatibility.
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_hist = cv2.calcHist([hsv], [0], None, [64], [0, 180])
        s_hist = cv2.calcHist([hsv], [1], None, [64], [0, 256])
        v_hist = cv2.calcHist([hsv], [2], None, [64], [0, 256])
        cv2.normalize(h_hist, h_hist, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(s_hist, s_hist, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(v_hist, v_hist, 0, 1, cv2.NORM_MINMAX)
        
        resized = cv2.resize(img, (256, 256))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        std_dev = float(np.std(gray))
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.sum(edges) / (edges.shape[0] * edges.shape[1] * 255))
        
        return {
            'h_hist': h_hist.flatten().tolist(),
            's_hist': s_hist.flatten().tolist(),
            'v_hist': v_hist.flatten().tolist(),
            'std_dev': std_dev,
            'edge_density': edge_density,
        }

    def _score_disease(self, disease_name, features_list, img_features):
        """
        Compares user features against a list of reference features for ONE disease.
        """
        # Convert user features to float32 numpy arrays for cv2.compareHist
        img_h = np.asarray(img_features['h_hist'], dtype=np.float32).reshape(64, 1)
        img_s = np.asarray(img_features['s_hist'], dtype=np.float32).reshape(64, 1)
        img_v = np.asarray(img_features['v_hist'], dtype=np.float32).reshape(64, 1)

        all_scores = []
        for ref_features in features_list:
            ref_h = np.asarray(ref_features['h_hist'], dtype=np.float32).reshape(64, 1)
            ref_s = np.asarray(ref_features['s_hist'], dtype=np.float32).reshape(64, 1)
            ref_v = np.asarray(ref_features['v_hist'], dtype=np.float32).reshape(64, 1)

            h_sim = cv2.compareHist(img_h, ref_h, cv2.HISTCMP_CORREL)
            s_sim = cv2.compareHist(img_s, ref_s, cv2.HISTCMP_CORREL)
            v_sim = cv2.compareHist(img_v, ref_v, cv2.HISTCMP_CORREL)

            max_std = max(img_features['std_dev'], ref_features['std_dev'])
            tex_sim = 1 - (abs(img_features['std_dev'] - ref_features['std_dev']) / max_std) if max_std > 0 else 1
            max_edge = max(img_features['edge_density'], ref_features['edge_density'])
            edge_sim = 1 - (abs(img_features['edge_density'] - ref_features['edge_density']) / max_edge) if max_edge > 0 else 1

            score = (h_sim * 0.20 + s_sim * 0.20 + v_sim * 0.10 + tex_sim * 0.25 + edge_sim * 0.25)
            all_scores.append(score)

        if not all_scores:
            return (disease_name, 0.0)
        all_scores.sort(reverse=True)
        top_n = min(len(all_scores), 3)
        avg_score = sum(all_scores[:top_n]) / top_n
        return (disease_name, float(avg_score))

    def compare_image(self, img): # Main entry point for search | CHANGE: Limit searching to certain categories
        """
        Searches the database for the most similar diseases in parallel.
        """
        if not self.reference_images: return [] # Exit if no reference data is loaded
        img_features = self._extract_features(img) # Extract features from the user's uploaded image
        with ThreadPoolExecutor() as executor: # Initialize parallel processing to speed up comparison
            futures = [] # List to track asynchronous tasks
            for name, flist in self.reference_images.items(): # Iterate through all loaded disease categories
                if name.lower() == 'healthy': continue # Skip the 'Healthy' category during disease matching
                futures.append(executor.submit(self._score_disease, name, flist, img_features)) # Queue comparison task
            similarities = [f.result() for f in futures] # Wait for and collect results from all threads
        similarities.sort(key=lambda x: x[1], reverse=True) # Sort the entire list by similarity score (descending)
        return similarities # Return the ranked list of similarities

    def get_matching_diseases(self, img, threshold=0.45, max_matches=3): # Filtered API | CHANGE: Add 'min_confidence' parameter
        """
        Returns list of diseases that crossed a minimum confidence bar.
        """
        similarities = self.compare_image(img) # Perform the full database comparison
        matches = [(d, s) for d, s in similarities if s >= threshold] # Filter out results below the confidence threshold
        return matches[:max_matches] # Return only the requested number of top matches

    def get_stats(self): # Data audit | CHANGE: Add 'Last Modified' date for each dataset
        """
        Returns summary of images loaded per disease category.
        """
        stats = {} # Initialize results dictionary
        for disease, flist in self.reference_images.items(): # Iterate through disease groups
            stats[disease] = len(flist) # Store the number of image fingerprints per group
        return stats # Return the final statistics report