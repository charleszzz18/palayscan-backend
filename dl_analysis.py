import os # Import OS module for path operations
import sys # Import System module for error logging
import numpy as np # Import Numpy for numerical array operations
import cv2 # Import OpenCV for image processing
import json # Import JSON for index mapping

MODEL_PATH = "rice_model.h5" # Define the path to the pre-trained model file
CLASS_INDICES_PATH = "class_indices.json" # Define the path to the class index mapping file

_model = None # Initialize model variable as None (Lazy Loading)
_class_labels = None # Initialize class labels variable as None

def load_dl_model(): # Function to load the deep learning model into memory
    """Lazy load the TensorFlow model so it doesn't slow down the server startup."""
    global _model, _class_labels # Reference global variables
    if _model is not None: # Check if model is already loaded
        return True # Return True if already in memory
        
    if not os.path.exists(MODEL_PATH) or not os.path.exists(CLASS_INDICES_PATH): # Check if files exist
        return False # Return False if model files are missing
        
    try: # Start error handling block
        import tensorflow as tf # Import TensorFlow library
        _model = tf.keras.models.load_model(MODEL_PATH) # Load the H5 model file
        
        with open(CLASS_INDICES_PATH, 'r') as f: # Open the indices JSON file
            class_indices = json.load(f) # Parse the JSON content
            # Invert dictionary to get {index: "Class Name"}
            _class_labels = {v: k for k, v in class_indices.items()} # Create reverse lookup dictionary
        return True # Return True on successful load
    except Exception as e: # Catch any loading errors
        print(f"[DL] Error loading model: {e}", file=sys.stderr) # Log error to stderr
        return False # Return False on failure

def analyze_with_dl(img): # Primary function for Deep Learning analysis
    """
    Takes a cv2 image, runs it through the Deep Learning model.
    Returns: (predicted_disease_name, confidence_score) or (None, 0)
    """
    if not load_dl_model(): # Ensure model is loaded before proceeding
        return None, 0.0 # Return None if model fails to load
        
    try: # Start inference error handling
        # Preprocess the image for MobileNetV2 (224x224, RGB, normalized 0-1)
        # OpenCV uses BGR, convert to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) # Convert image color space to RGB
        img_resized = cv2.resize(img_rgb, (224, 224)) # Resize image to 224x224 for the model
        
        # Expand dims to create a batch of 1: shape (1, 224, 224, 3)
        img_array = np.expand_dims(img_resized, axis=0) # Add batch dimension
        img_array = img_array.astype('float32') / 255.0 # Rescale pixel values to [0, 1]
        
        # Predict
        predictions = _model.predict(img_array) # Run image through the neural network
        predicted_class_idx = np.argmax(predictions[0]) # Get index of the highest probability
        confidence = float(predictions[0][predicted_class_idx]) # Extract the confidence score
        
        raw_label = _class_labels[predicted_class_idx] # Get the raw class label string
        
        # Format the label nicely (e.g., "Bacterial leaf blight" -> "Bacterial Leaf Blight")
        disease_name = raw_label.title() # Convert string to title case
        
        return disease_name, confidence # Return the prediction and confidence
        
    except Exception as e: # Catch inference errors
        print(f"[DL] Inference error: {e}", file=sys.stderr) # Log error message
        return None, 0.0 # Return failure state
