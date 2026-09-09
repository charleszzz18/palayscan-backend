# ==========================================
# RICE HEALTH APP - TEXTURE ANALYSIS MODULE
# ==========================================
# This file looks for patterns, spots, and edge densities in the image.

import cv2 # Computer Vision library | CHANGE: Update if using a different image processing library
import numpy as np # Numerical math library | CHANGE: Standard dependency

def analyze_texture(img, sensitivity=1.0): # Texture analysis function | CHANGE: Add 'min_edge_threshold'
    """
    Analyze texture patterns in rice to detect potential diseases.
    """
    # --- 1. PREPARE THE IMAGE ---
    # Convert to grayscale to focus on shapes/lines rather than color
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # Convert BGR image to grayscale
    
    # Blur to remove noise (low-pass filter)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0) # Apply Gaussian blur to smooth the image | CHANGE: (3,3) for sharper detail, (7,7) for smoother
    
    # --- 2. FIND EDGES (TEXTURE) ---
    # Canny Edge Detection identifies boundaries of spots and lesions.
    edges = cv2.Canny(blurred, 50, 150) # Use Canny algorithm to find edges in the blurred image | CHANGE: (30, 100) for more sensitive detection
    
    # Calculate "edge density" - how much of the leaf is textured/spotted
    hist = cv2.calcHist([edges], [0], None, [256], [0, 256]) # Generate a histogram of edge pixel intensities
    edge_density = np.sum(hist[50:]) / (img.shape[0] * img.shape[1]) # Calculate ratio of edge pixels to total pixels | CHANGE: Change 50 to 100 for stronger edges only
    
    # --- 3. COLOR PATTERN RECOGNITION ---
    # While color_analysis.py looks at health, we look for specific symptom colors.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) # Convert original BGR image to HSV color space
    
    # Brown/rust range (Blast, Brown Spot)
    lower_brown = np.array([5, 50, 50]) # Define lower bound for brown symptoms | CHANGE: [0, 40, 40] for darker browns
    upper_brown = np.array([25, 255, 255]) # Define upper bound for brown symptoms | CHANGE: [30, 255, 255] for broader brown range
    brown_mask = cv2.inRange(hsv, lower_brown, upper_brown) # Create a mask for brown-colored pixels
    
    # Straw/Tan range (Bacterial Panicle Blight)
    lower_straw = np.array([20, 30, 150]) # Define lower bound for straw-colored symptoms | CHANGE: [15, 20, 140]
    upper_straw = np.array([30, 150, 255]) # Define upper bound for straw-colored symptoms | CHANGE: [35, 170, 255]
    straw_mask = cv2.inRange(hsv, lower_straw, upper_straw) # Create a mask for straw-colored pixels
    
    # Black/Dark range (Black Kernel)
    lower_black = np.array([0, 0, 0]) # Define lower bound for black spots (pure black)
    upper_black = np.array([180, 255, 40]) # Define upper bound for black spots (dark gray) | CHANGED: Max value 40 for stricter black spots
    black_mask = cv2.inRange(hsv, lower_black, upper_black) # Create a mask for black/dark pixels
    
    # White/Pale range (Hispa, White Tip)
    lower_white = np.array([0, 0, 200]) # Define lower bound for white/scraped symptoms (light gray)
    upper_white = np.array([180, 30, 255]) # Define upper bound for white symptoms (pure white) | CHANGE: Max saturation 50 for off-white
    white_mask = cv2.inRange(hsv, lower_white, upper_white) # Create a mask for white-colored pixels
    
    # Yellow range (False Smut, Tungro)
    lower_yellow = np.array([25, 100, 100]) # Define lower bound for disease-related yellowing | CHANGE: [20, 80, 80]
    upper_yellow = np.array([35, 255, 255]) # Define upper bound for disease-related yellowing | CHANGE: [40, 255, 255]
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow) # Create a mask for yellow pixels
    
    # Orange range (Leaf Scald)
    lower_orange = np.array([5, 80, 80]) # Define lower bound for orange/reddish symptoms
    upper_orange = np.array([20, 255, 255]) # Define upper bound for orange/reddish symptoms
    orange_mask = cv2.inRange(hsv, lower_orange, upper_orange) # Create a mask for orange pixels
    
    # Gray range (Stackburn)
    lower_gray = np.array([0, 0, 100]) # Define lower bound for gray lesions (mid-gray)
    upper_gray = np.array([180, 30, 180]) # Define upper bound for gray lesions (darker gray) | CHANGE: [180, 50, 200]
    gray_mask = cv2.inRange(hsv, lower_gray, upper_gray) # Create a mask for gray pixels
    
    # --- 4. CALCULATE RATIOS ---
    # Find percentage of image covered by each symptom color
    total_pixels = img.shape[0] * img.shape[1] # Calculate the total number of pixels in the image
    brown_ratio = float(cv2.countNonZero(brown_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of brown symptoms
    straw_ratio = float(cv2.countNonZero(straw_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of straw symptoms
    black_ratio = float(cv2.countNonZero(black_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of black symptoms
    white_ratio = float(cv2.countNonZero(white_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of white symptoms
    yellow_ratio = float(cv2.countNonZero(yellow_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of yellow symptoms
    orange_ratio = float(cv2.countNonZero(orange_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of orange symptoms
    gray_ratio = float(cv2.countNonZero(gray_mask)) / total_pixels if total_pixels > 0 else 0 # Calculate ratio of gray symptoms
    
    # --- 5. APPLY WEATHER SENSITIVITY ---
    # Boost ratios if weather is difficult for detection
    brown_ratio *= sensitivity # Adjust brown ratio based on sensitivity input
    straw_ratio *= sensitivity # Adjust straw ratio based on sensitivity input
    black_ratio *= sensitivity # Adjust black ratio based on sensitivity input
    white_ratio *= sensitivity # Adjust white ratio based on sensitivity input
    yellow_ratio *= sensitivity # Adjust yellow ratio based on sensitivity input
    orange_ratio *= sensitivity # Adjust orange ratio based on sensitivity input
    gray_ratio *= sensitivity # Adjust gray ratio based on sensitivity input
    
    # Debug report
    print(f"Texture Analysis - Edge density: {edge_density}, Brown ratio: {brown_ratio}, " +
          f"Straw ratio: {straw_ratio}, Black ratio: {black_ratio}, White ratio: {white_ratio}, " +
          f"Yellow ratio: {yellow_ratio}, Orange ratio: {orange_ratio}, Gray ratio: {gray_ratio}") # Print diagnostic log
    
    # --- 6. DISEASE LOGIC RULES ---
    # Map symptoms to specific disease names
    possible_diseases = [] # Initialize list for identified diseases
    

    # RULE: Brown Spot (Lower brown + lower texture)
    if brown_ratio > 0.05 and edge_density < 0.15: # Check for Brown Spot symptoms
        possible_diseases.append("Brown Spot")
        
    # RULE: Leaf Strip (Thin linear streaks)
    if brown_ratio > 0.05 and edge_density > 0.10: # High edge density due to thin lines
        possible_diseases.append("Leaf Strip")

    # RULE: Blight (Streaks - white/straw + high texture)
    if edge_density > 0.10 and (straw_ratio > 0.05 or white_ratio > 0.05): # Check for Blight streaks
        possible_diseases.append("Blight")
    
    # RULE: Blast (Brown borders with gray centers)
    if brown_ratio > 0.05 and gray_ratio > 0.02: 
        possible_diseases.append("Blast")
        
    # RULE: Rust (Orange/rust colored spots)
    if orange_ratio > 0.03 or (brown_ratio > 0.08 and orange_ratio > 0.01): 
        possible_diseases.append("Rust")
 

    
    # --- 7. CLEAN UP RESULTS ---
    possible_diseases = list(set(possible_diseases)) # Filter out any duplicate disease names
    
    return possible_diseases # Return the final list of possible diseases to the caller
