# ==========================================
# RICE HEALTH APP - IMAGE COMPARISON MODULE
# ==========================================
# This file takes the user's uploaded image and compares it against
# a folder of known disease reference images to find the closest match.

import cv2 # Computer Vision library | CHANGE: Update if using a different image processing library
import numpy as np # Numerical math library | CHANGE: Standard dependency
import os # System path library | CHANGE: Standard dependency
import glob # Filename pattern matching | CHANGE: Standard dependency
import re # Regular expression library | CHANGE: Use for name cleaning
from pathlib import Path # Path object management | CHANGE: Modern way to handle file paths
from concurrent.futures import ThreadPoolExecutor # Parallel processing | CHANGE: Remove for low-power systems

class ImageComparison: # Core AI comparison class | CHANGE: Rename if adding non-image comparison features
    def __init__(self, reference_dir): # Constructor | CHANGE: Add 'cache_file' param to save fingerprints
        """
        Initializes the ImageComparison object and loads ALL reference images.
        """
        self.reference_dir = reference_dir # Store the root path of the reference dataset
        self.reference_images = {} # Dictionary to store disease names and their corresponding image fingerprints
        self.load_reference_images() # Trigger the initial data loading process | CHANGE: Move to an async task for faster startup

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

    def load_reference_images(self): # Bulk image loader | CHANGE: Add 'limit' parameter to test with few images
        """
        Scans the reference directory and extracts fingerprints from all images.
        """
        if not os.path.exists(self.reference_dir): # Check if the reference directory actually exists on disk
            print(f"[ImageComparison] WARNING: Reference directory not found: {self.reference_dir}") # Log warning
            return # Exit early if directory is missing
        total_loaded = 0 # Initialize counter for tracking total images processed
        for entry in os.scandir(self.reference_dir): # Iterate through all entries in the reference directory
            if entry.is_dir(): # Check if the entry is a directory (representing a disease class)
                disease_name = self._normalize_disease_name(entry.name) # Get the standardized name for this category
                sub_images = [] # Temporary list to hold image paths for this disease
                for ext in ('*.jpg', '*.jpeg', '*.png'): # Loop through supported file extensions
                    sub_images += glob.glob(os.path.join(entry.path, '**', ext), recursive=True) # Recursively find all images
                if not sub_images: continue # Skip this folder if no valid images were found
                
                # OPTIMIZATION: Sub-sampling to prevent memory overload
                MAX_PER_DISEASE = 5000 # Increased limit to ensure the entire dataset is loaded for higher accuracy
                if len(sub_images) > MAX_PER_DISEASE: # If folder exceeds the limit
                    stride = len(sub_images) // MAX_PER_DISEASE # Calculate skip interval
                    sub_images = sub_images[::stride][:MAX_PER_DISEASE] # Take evenly distributed samples
                
                if disease_name not in self.reference_images: # Check if category already exists in storage
                    self.reference_images[disease_name] = [] # Initialize empty list for this disease
                for img_path in sub_images: # Loop through the sampled image paths
                    img = cv2.imread(img_path) # Read the image file from disk
                    if img is not None: # Ensure the image was read correctly
                        self.reference_images[disease_name].append(self._extract_features(img)) # Extract and store features
                        total_loaded += 1 # Increment total count
            
            elif entry.is_file(): # Check if entry is a single file (for flat-folder legacy support)
                stem = Path(entry.path).stem # Extract the filename without extension
                disease_name = self._normalize_disease_name(stem) # Normalize the name
                img = cv2.imread(entry.path) # Read the image file
                if img is not None: # Ensure image was loaded successfully
                    if disease_name not in self.reference_images: # Initialize category if missing
                        self.reference_images[disease_name] = [] # Set up storage list
                    self.reference_images[disease_name].append(self._extract_features(img)) # Extract features
                    total_loaded += 1 # Increment counter
        print(f"[ImageComparison] Loaded {total_loaded} images.") # Print summary report to console

    def _extract_features(self, img): # Create numerical fingerprint | CHANGE: Add ORB or SIFT keypoint detection
        """
        Converts an image into a numerical summary of colors and textures.
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) # Convert BGR image to HSV for robust color analysis
        h_hist = cv2.calcHist([hsv], [0], None, [64], [0, 180]) # Calculate 64-bin Hue histogram
        s_hist = cv2.calcHist([hsv], [1], None, [64], [0, 256]) # Calculate 64-bin Saturation histogram
        v_hist = cv2.calcHist([hsv], [2], None, [64], [0, 256]) # Calculate 64-bin Value (Brightness) histogram
        cv2.normalize(h_hist, h_hist, 0, 1, cv2.NORM_MINMAX) # Normalize Hue histogram to [0,1] range
        cv2.normalize(s_hist, s_hist, 0, 1, cv2.NORM_MINMAX) # Normalize Saturation histogram to [0,1] range
        cv2.normalize(v_hist, v_hist, 0, 1, cv2.NORM_MINMAX) # Normalize Brightness histogram to [0,1] range
        
        resized = cv2.resize(img, (256, 256)) # Resize image to 256x256 for consistent texture analysis | CHANGE: 512x512
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) # Convert resized image to grayscale
        std_dev = np.std(gray) # Calculate standard deviation as a measure of texture contrast
        edges = cv2.Canny(gray, 50, 150) # Use Canny edge detection to find patterns | CHANGE: (30, 100)
        edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1] * 255) # Calculate density of edge pixels
        
        return { # Return the extracted feature dictionary (the "fingerprint")
            'h_hist': h_hist, 's_hist': s_hist, 'v_hist': v_hist,
            'std_dev': std_dev, 'edge_density': edge_density,
        }

    def _score_disease(self, disease_name, features_list, img_features): # Math logic for match | CHANGE: Use Cosine Similarity
        """
        Compares user features against a list of reference features for ONE disease.
        """
        all_scores = [] # Initialize list to hold scores for individual reference images
        for ref_features in features_list: # Iterate through every reference image in this category
            h_sim = cv2.compareHist(img_features['h_hist'], ref_features['h_hist'], cv2.HISTCMP_CORREL) # Compare Hue similarity
            s_sim = cv2.compareHist(img_features['s_hist'], ref_features['s_hist'], cv2.HISTCMP_CORREL) # Compare Saturation similarity
            v_sim = cv2.compareHist(img_features['v_hist'], ref_features['v_hist'], cv2.HISTCMP_CORREL) # Compare Brightness similarity
            max_std = max(img_features['std_dev'], ref_features['std_dev']) # Determine denominator for texture comparison
            tex_sim = 1 - (abs(img_features['std_dev'] - ref_features['std_dev']) / max_std) if max_std > 0 else 1 # Calc texture sim
            max_edge = max(img_features['edge_density'], ref_features['edge_density']) # Determine denominator for edge comparison
            edge_sim = 1 - (abs(img_features['edge_density'] - ref_features['edge_density']) / max_edge) if max_edge > 0 else 1 # Calc edge sim
            score = (h_sim * 0.20 + s_sim * 0.20 + v_sim * 0.10 + tex_sim * 0.25 + edge_sim * 0.25) # Compute weighted final score
            all_scores.append(score) # Append score to list
        if not all_scores: return (disease_name, 0.0) # Guard clause for empty datasets
        all_scores.sort(reverse=True) # Sort individual scores from highest to lowest
        top_n = min(len(all_scores), 3) # Select the top 3 best matching scores | CHANGE: top 5
        avg_score = sum(all_scores[:top_n]) / top_n # Calculate average of the top matches for robustness
        return (disease_name, float(avg_score)) # Return the disease name and its averaged similarity score

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