# ==========================================
# RICE HEALTH APP - COLOR ANALYSIS MODULE
# ==========================================
# This module identifies healthy vs. diseased tissue based on color ranges.

import cv2 # Computer Vision library | CHANGE: Update if using a different image processing library
import numpy as np # Numerical math library | CHANGE: Standard dependency for arrays

def analyze_color(img): # Main color engine | CHANGE: Add 'sensitivity' parameter to adjust ranges dynamically
    """
    Analyze the color of rice to determine health and INFECTED areas.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) # Convert BGR to HSV for easier color math
    
    # --- 1. FIND HEALTHY COLORS ---
    # Defines what a "Healthy" leaf looks like in terms of Hue, Saturation, and Value.
    lower_green = np.array([35, 45, 40]) # Start of healthy green | CHANGE: [30, 40, 30] for darker forest green
    upper_green = np.array([90, 255, 255]) # End of healthy green | CHANGE: [80, 255, 255] if catching too much background
    green_mask = cv2.inRange(hsv, lower_green, upper_green) # Isolate green pixels
    
    # Healthy Yellow (must be high saturation to not be confused with 'straw' disease color)
    lower_yellow = np.array([25, 80, 80]) # Start of vibrant yellow | CHANGE: [20, 70, 70] if leaves are very pale
    upper_yellow = np.array([35, 255, 255]) # End of vibrant yellow | CHANGE: [40, 255, 255] for broader yellow range
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow) # Isolate yellow pixels
    
    healthy_colors = cv2.bitwise_or(green_mask, yellow_mask) # Combine Green + Yellow into one mask
    
    # --- 2. FIND SPECIFIC DISEASE DAMAGE COLORS ---
    # Target 'Straw', 'Tan', and 'Necrotic White' specifically.
    
    # Straw/Tan (Common in Blight)
    lower_straw = np.array([10, 20, 80]) # Start of straw | CHANGE: [5, 10, 70] for darker tan spots
    upper_straw = np.array([30, 160, 255]) # End of straw | CHANGE: [35, 180, 255] for broader tan range
    straw_damage = cv2.inRange(hsv, lower_straw, upper_straw) # Isolate straw colors
    
    # Necrotic Brown (Dead tissue)
    lower_brown = np.array([0, 30, 20]) # Start of brown | CHANGE: [0, 50, 10] for deeper black-browns
    upper_brown = np.array([20, 255, 180]) # End of brown | CHANGE: [25, 255, 200] if missing light brown spots
    brown_damage = cv2.inRange(hsv, lower_brown, upper_brown) # Isolate brown colors
    
    # Blight White / Pale Gray (Advanced lesions)
    lower_white = np.array([0, 0, 150]) # Start of pale gray/white | CHANGE: [0, 0, 120] to catch darker grays
    upper_white = np.array([180, 70, 255]) # End of pale gray/white | CHANGE: [180, 50, 255] for pure white only
    white_damage = cv2.inRange(hsv, lower_white, upper_white) # Isolate white colors

    # Rust / Reddish-Orange-Brown Lesions (Characteristic rust color on rice leaves)
    lower_rust = np.array([5, 50, 50]) # Start of reddish-orange rust lesions
    upper_rust = np.array([18, 255, 220]) # End of reddish-orange rust lesions
    rust_damage = cv2.inRange(hsv, lower_rust, upper_rust) # Isolate rust-colored lesion pixels

    # Combine all damage types into one master "unhealthy" mask
    specific_damage = cv2.bitwise_or(straw_damage, brown_damage) # Merge straw and brown
    specific_damage = cv2.bitwise_or(specific_damage, white_damage) # Add white damage
    specific_damage = cv2.bitwise_or(specific_damage, rust_damage) # Add rust reddish-orange lesions
    
    # --- 3. ISOLATE THE LEAF ---
    # This step removes the background by identifying everything that is either healthy OR damaged.
    potential_leaf = cv2.bitwise_or(healthy_colors, specific_damage) # Sum of all leaf-colored pixels
    height, width = img.shape[:2]
    total_pixels = height * width
    leaf_candidate_pixels = cv2.countNonZero(potential_leaf)
    
    # If practically no leaf colors are present (< 2% of the image), check if it's a solid background wall/surface
    if (leaf_candidate_pixels / total_pixels) < 0.02:
        bg_white_mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([180, 50, 255]))
        bg_brown_mask = cv2.inRange(hsv, np.array([0, 30, 20]), np.array([30, 255, 150]))
        bg_black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 40]))
        if (cv2.countNonZero(bg_white_mask) / total_pixels) > 0.75:
            return 0, None, None, "Unknown", "white"
        if (cv2.countNonZero(bg_brown_mask) / total_pixels) > 0.75:
            return 0, None, None, "Unknown", "brown"
        if (cv2.countNonZero(bg_black_mask) / total_pixels) > 0.75:
            return 0, None, None, "Unknown", "black"

    kernel = np.ones((7,7), np.uint8) # Shaping tool for smoothing | CHANGE: (11,11) for more aggressive smoothing
    leaf_mask_rough = cv2.morphologyEx(potential_leaf, cv2.MORPH_CLOSE, kernel) # Fill small gaps inside the leaf
    leaf_mask_rough = cv2.morphologyEx(leaf_mask_rough, cv2.MORPH_OPEN, np.ones((5,5), np.uint8)) # Remove tiny background noise
    
    # Use contours to find the largest connected object (the main leaf)
    contours, _ = cv2.findContours(leaf_mask_rough, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) # Find outlines
    final_leaf_mask = np.zeros_like(leaf_mask_rough) # Create black canvas for the final leaf shape
    if contours: # Check if any leaf-like shapes were found
        contours = sorted(contours, key=cv2.contourArea, reverse=True) # Rank all found shapes by their surface area
        main_contour = contours[0]
        area = cv2.contourArea(main_contour)
        
        # --- CONTOUR CHECK FOR IRREGULAR NON-LEAF OBJECTS ---
        if area > 500: # Ensure the largest object is actually a leaf and not noise
            hull = cv2.convexHull(main_contour)
            hull_area = cv2.contourArea(hull)
            solidity = float(area) / hull_area if hull_area > 0 else 0
            
            perimeter = cv2.arcLength(main_contour, True)
            hull_perimeter = cv2.arcLength(hull, True)
            perimeter_ratio = perimeter / hull_perimeter if hull_perimeter > 0 else 1.0
            
            # Realistic weed check: only reject if extremely fragmented/spiky and porous
            if solidity < 0.25 and perimeter_ratio > 4.5:
                # Shape is too complex, stringy, scattered, or spiky (e.g. weed flowers or whole plant)
                return 0, None, None, "Unknown", "complex"
                
            cv2.drawContours(final_leaf_mask, [main_contour], -1, 255, thickness=cv2.FILLED) # Fill the largest object with solid white
            # Include other fragments (e.g. split leaves or multiple leaves in one shot)
            for cnt in contours[1:]: # Loop through secondary detected shapes
                if cv2.contourArea(cnt) > 0.1 * area: # Check if shape is at least 10% of main leaf size
                    cv2.drawContours(final_leaf_mask, [cnt], -1, 255, thickness=cv2.FILLED) # Add these secondary shapes to final mask
    else: # If contour detection fails completely
        final_leaf_mask = leaf_mask_rough # Use the rough morphology mask as the final mask
 
    # --- 4. IDENTIFY ACTUAL DAMAGE VS HEALTHY ---
    # Damage takes precedence: if a pixel is in a damage range, it's counted as infected.
    final_infected_mask = cv2.bitwise_and(specific_damage, final_leaf_mask) # Filter damage so only spots on the actual leaf are kept
    
    # Healthy area is the rest of the leaf
    final_healthy_mask = cv2.bitwise_and(final_leaf_mask, cv2.bitwise_not(final_infected_mask)) # Subtract infected spots from total leaf area
    
    # Final smoothing for cleaner visualization in the UI
    final_infected_mask = cv2.morphologyEx(final_infected_mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8)) # Clean up noisy edges of spots
    
    # --- 5. SCORE & SIZE ANALYSIS ---
    leaf_pixels = cv2.countNonZero(final_leaf_mask) # Calculate the total number of pixels belonging to the rice leaf
    healthy_pixels = cv2.countNonZero(final_healthy_mask) # Calculate total number of healthy green/yellow pixels
    
    height, width = img.shape[:2] # Get image dimensions (height and width)
    total_pixels = height * width # Calculate total image resolution
    leaf_ratio = leaf_pixels / total_pixels if total_pixels > 0 else 0 # Calculate how much of the frame the leaf covers
    
    # NEW PRECISION SCORING ALGORITHM
    # Calculate pure raw score independent of distance or leaf size
    raw_score = float(healthy_pixels) / leaf_pixels if leaf_pixels > 0 else 0
    
    # Directly use raw score. The health percentage will reflect exactly how much of the leaf is healthy vs damaged.
    health_score = max(min(raw_score, 1.0), 0.05) # Cap at 5% minimum and 100% maximum
    
    # --- 6. AUTOMATIC GROWTH STAGE DETECTION ---
    yellow_pixels = cv2.countNonZero(cv2.bitwise_and(yellow_mask, final_leaf_mask)) # Count yellow pixels on the leaf surface
    yellow_ratio = yellow_pixels / leaf_pixels if leaf_pixels > 0 else 0 # Calculate percentage of yellow vs total leaf
    
    growth_stage = "Heading" # Default growth stage assumption
    if yellow_ratio > 0.35: # If more than 35% of the leaf is yellowing (natural maturity)
        growth_stage = "Maturity" # Assign Maturity stage
    elif leaf_ratio < 0.15: # If the leaf is very small relative to the frame
        growth_stage = "Seedling" # Assign Seedling stage
    elif leaf_ratio > 0.4: # If the leaf/plant is large and dense
        growth_stage = "Tillering" # Assign Tillering stage
         
    print(f"Blight Capture - Healthy: {healthy_pixels}, Leaf: {leaf_pixels}, Score: {health_score}, Stage: {growth_stage}") # Log diagnostic metrics
    
    return health_score, final_healthy_mask, final_infected_mask, growth_stage, None # Return all calculated results to main app


def extract_lesion_hotspots(infected_mask, max_spots=5):
    """
    Finds prominent lesion contours in the infected mask and computes
    normalized percentage coordinates (x%, y%, w%, h%) guaranteed to land
    directly inside the red highlighted lesion area using distance transforms.
    """
    if infected_mask is None:
        return []
    
    height, width = infected_mask.shape[:2]
    total_pixels = height * width
    if total_pixels == 0:
        return []
        
    contours, _ = cv2.findContours(infected_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = max(8, int(total_pixels * 0.0001)) # Filter out tiny single-pixel noise
    valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not valid_contours and len(contours) > 0:
        valid_contours = contours
    
    # Sort largest lesion clusters first
    valid_contours.sort(key=lambda c: cv2.contourArea(c), reverse=True)
    
    hotspots = []
    for idx, cnt in enumerate(valid_contours[:max_spots]):
        x, y, w, h = cv2.boundingRect(cnt)
        c_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(c_mask, [cnt], -1, 255, -1, offset=(-x, -y))
        dist_map = cv2.distanceTransform(c_mask, cv2.DIST_L2, 3)
        _, _, _, max_loc = cv2.minMaxLoc(dist_map)
        
        # Exact lesion coordinate guaranteed to be directly on the red highlighted pixels
        best_x = x + max_loc[0]
        best_y = y + max_loc[1]
        
        center_x = round((float(best_x) / float(width)) * 100, 1)
        center_y = round((float(best_y) / float(height)) * 100, 1)
        w_pct = round((w / float(width)) * 100, 1)
        h_pct = round((h / float(height)) * 100, 1)
        area_px = int(cv2.contourArea(cnt))
        
        hotspots.append({
            "id": idx + 1,
            "x": max(1.0, min(99.0, center_x)),
            "y": max(1.0, min(99.0, center_y)),
            "w": max(w_pct, 2.5),
            "h": max(h_pct, 2.5),
            "area_px": area_px
        })
    return hotspots