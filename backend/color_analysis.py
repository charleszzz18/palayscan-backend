# ==========================================
# RICE HEALTH APP - COLOR ANALYSIS MODULE
# ==========================================
# This module identifies healthy vs. diseased tissue based on color ranges.

import cv2 # Computer Vision library | CHANGE: Update if using a different image processing library
import numpy as np # Numerical math library | CHANGE: Standard dependency for arrays

def analyze_color(img): # Main color engine | CHANGE: Add 'sensitivity' parameter to adjust ranges dynamically
    """
    Analyze the color of rice to determine health and INFECTED areas.
    Isolates the rice leaf from brown desks, black backgrounds, or white sheets,
    and rejects images that do not contain a genuine rice leaf.
    """
    height, width = img.shape[:2]
    total_pixels = height * width
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) # Convert BGR to HSV for easier color math
    
    # --- 1. FIND HEALTHY PLANT COLORS ---
    # Defines what a "Healthy" leaf looks like in terms of Hue, Saturation, and Value.
    lower_green = np.array([30, 40, 35]) # Start of healthy green (accommodates darker/lighter rice leaves)
    upper_green = np.array([90, 255, 255]) # End of healthy green
    green_mask = cv2.inRange(hsv, lower_green, upper_green) # Isolate green pixels
    
    # Healthy Yellow (must be vibrant yellow to represent mature healthy plant tissue)
    lower_yellow = np.array([20, 60, 60]) # Start of vibrant yellow
    upper_yellow = np.array([35, 255, 255]) # End of vibrant yellow
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow) # Isolate yellow pixels
    
    healthy_colors = cv2.bitwise_or(green_mask, yellow_mask) # Combine Green + Yellow into one mask
    plant_pixels = cv2.countNonZero(healthy_colors)

    # --- 1.1 RICE LEAF PRESENCE VALIDATION ---
    # A legitimate rice leaf photograph MUST have detectable plant chlorophyll tissue.
    # If there is practically no green/plant color (< 0.5% of the frame and < 350 pixels),
    # this image is NOT a rice leaf (e.g. empty brown desk, solid black screen, floor, book, pet, etc.).
    if plant_pixels < 350 or (plant_pixels / total_pixels) < 0.005:
        return 0, None, None, "Unknown", "no_leaf"

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

    # --- 3. INTELLIGENT BACKGROUND SEPARATION & LEAF ISOLATION ---
    # Sample perimeter border pixels to detect if the leaf is set on a solid/uniform background
    # (e.g. brown wooden desk, black cloth/board, white paper, floor tile)
    border_pixels = np.concatenate([
        img[0, :],      # Top row
        img[-1, :],     # Bottom row
        img[:, 0],      # Left col
        img[:, -1]      # Right col
    ], axis=0)

    border_hsv = cv2.cvtColor(border_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    median_hsv = np.median(border_hsv, axis=0)
    std_hsv = np.std(border_hsv, axis=0)

    # Check if border is reasonably uniform (indicating an artificial or plain background)
    is_uniform_bg = (std_hsv[0] < 35 and std_hsv[1] < 55 and std_hsv[2] < 55)

    if is_uniform_bg:
        # Calculate dynamic tolerance around the background color
        h_tol = max(15, int(std_hsv[0] * 2.5))
        s_tol = max(40, int(std_hsv[1] * 2.5))
        v_tol = max(40, int(std_hsv[2] * 2.5))

        lower_bg = np.array([max(0, median_hsv[0] - h_tol), max(0, median_hsv[1] - s_tol), max(0, median_hsv[2] - v_tol)], dtype=np.uint8)
        upper_bg = np.array([min(180, median_hsv[0] + h_tol), min(255, median_hsv[1] + s_tol), min(255, median_hsv[2] + v_tol)], dtype=np.uint8)

        raw_bg_mask = cv2.inRange(hsv, lower_bg, upper_bg)
        # Background cannot be the healthy green plant tissue
        bg_mask = cv2.bitwise_and(raw_bg_mask, cv2.bitwise_not(healthy_colors))
        # Non-background is foreground candidate
        fg_candidate = cv2.bitwise_not(bg_mask)
    else:
        # Natural field/outdoor background:
        # Lesions are spatially adjacent to/enclosed in plant core
        plant_clean = cv2.morphologyEx(healthy_colors, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
        dil_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
        plant_dilated = cv2.dilate(plant_clean, dil_kernel, iterations=1)
        valid_damage = cv2.bitwise_and(specific_damage, plant_dilated)
        fg_candidate = cv2.bitwise_or(healthy_colors, valid_damage)

    # Clean foreground candidate
    fg_clean = cv2.morphologyEx(fg_candidate, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    fg_clean = cv2.morphologyEx(fg_clean, cv2.MORPH_CLOSE, np.ones((11,11), np.uint8))

    contours, _ = cv2.findContours(fg_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0, None, None, "Unknown", "no_leaf"

    # Only accept contours that actually contain rice plant tissue
    valid_leaf_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 400:
            c_mask = np.zeros((height, width), dtype=np.uint8)
            cv2.drawContours(c_mask, [cnt], -1, 255, -1)
            plant_inside = cv2.countNonZero(cv2.bitwise_and(healthy_colors, c_mask))
            if plant_inside > 200:
                valid_leaf_contours.append((cnt, area, plant_inside))

    if not valid_leaf_contours:
        return 0, None, None, "Unknown", "no_leaf"

    valid_leaf_contours.sort(key=lambda x: x[1], reverse=True)
    main_contour = valid_leaf_contours[0][0]
    main_area = valid_leaf_contours[0][1]

    # --- CONTOUR CHECK FOR IRREGULAR NON-LEAF OBJECTS ---
    hull = cv2.convexHull(main_contour)
    hull_area = cv2.contourArea(hull)
    solidity = float(main_area) / hull_area if hull_area > 0 else 0
    
    perimeter = cv2.arcLength(main_contour, True)
    hull_perimeter = cv2.arcLength(hull, True)
    perimeter_ratio = perimeter / hull_perimeter if hull_perimeter > 0 else 1.0
    
    # Weed check: reject if extremely fragmented/spiky and porous
    if solidity < 0.22 and perimeter_ratio > 4.5:
        return 0, None, None, "Unknown", "complex"

    final_leaf_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.drawContours(final_leaf_mask, [main_contour], -1, 255, thickness=cv2.FILLED)
    for cnt, area, _ in valid_leaf_contours[1:]:
        if area > 0.10 * main_area:
            cv2.drawContours(final_leaf_mask, [cnt], -1, 255, thickness=cv2.FILLED)

    # --- 4. IDENTIFY ACTUAL DAMAGE VS HEALTHY ---
    # Damage spots strictly within the isolated leaf boundary
    final_infected_mask = cv2.bitwise_and(specific_damage, final_leaf_mask)
    # Healthy area is the rest of the leaf
    final_healthy_mask = cv2.bitwise_and(final_leaf_mask, cv2.bitwise_not(final_infected_mask))
    # Final smoothing for cleaner visualization in the UI
    final_infected_mask = cv2.morphologyEx(final_infected_mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))

    # --- 5. SCORE & SIZE ANALYSIS ---
    leaf_pixels = cv2.countNonZero(final_leaf_mask)
    healthy_pixels = cv2.countNonZero(final_healthy_mask)
    
    leaf_ratio = leaf_pixels / total_pixels if total_pixels > 0 else 0
    raw_score = float(healthy_pixels) / leaf_pixels if leaf_pixels > 0 else 0
    health_score = max(min(raw_score, 1.0), 0.05)

    # --- 6. AUTOMATIC GROWTH STAGE DETECTION ---
    yellow_pixels = cv2.countNonZero(cv2.bitwise_and(yellow_mask, final_leaf_mask))
    yellow_ratio = yellow_pixels / leaf_pixels if leaf_pixels > 0 else 0

    growth_stage = "Heading" # Default growth stage assumption
    if yellow_ratio > 0.35: # If more than 35% of the leaf is yellowing (natural maturity)
        growth_stage = "Maturity" # Assign Maturity stage
    elif leaf_ratio < 0.15: # If the leaf is very small relative to the frame
        growth_stage = "Seedling" # Assign Seedling stage
    elif leaf_ratio > 0.4: # If the leaf/plant is large and dense
        growth_stage = "Tillering" # Assign Tillering stage

    print(f"Blight Capture - Healthy: {healthy_pixels}, Leaf: {leaf_pixels}, Score: {health_score}, Stage: {growth_stage}")
    return health_score, final_healthy_mask, final_infected_mask, growth_stage, None


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
