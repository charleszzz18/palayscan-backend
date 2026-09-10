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
        # Ensure we don't force legacy keras flag which breaks imports when tf_keras is absent
        os.environ.pop("TF_USE_LEGACY_KERAS", None)

        import tensorflow as tf
        from tensorflow import keras

        # Define patched layer subclasses to safely handle older serialized H5 model configs
        class PatchedBatchNormalization(keras.layers.BatchNormalization):
            def __init__(self, *args, **kwargs):
                for k in ['renorm', 'renorm_clipping', 'renorm_momentum']:
                    kwargs.pop(k, None)
                super().__init__(*args, **kwargs)

        class PatchedDense(keras.layers.Dense):
            def __init__(self, *args, **kwargs):
                kwargs.pop('quantization_config', None)
                super().__init__(*args, **kwargs)

        custom_objects = {
            'BatchNormalization': PatchedBatchNormalization,
            'Dense': PatchedDense
        }

        # Load with custom_objects and compile=False (inference only)
        _model = keras.models.load_model(
            MODEL_PATH,
            custom_objects=custom_objects,
            compile=False
        )
        
        with open(CLASS_INDICES_PATH, 'r') as f: # Open the indices JSON file
            class_indices = json.load(f) # Parse the JSON content
            # Invert dictionary to get {index: "Class Name"}
            _class_labels = {v: k for k, v in class_indices.items()} # Create reverse lookup dictionary
        return True # Return True on successful load
    except Exception as e: # Catch any loading errors
        print(f"[DL] Error loading model: {e}", file=sys.stderr) # Log error to stderr
        return False # Return False on failure

def analyze_with_dl(img, return_all_preds=False): # Primary function for Deep Learning analysis
    """
    Takes a cv2 image, runs it through the Deep Learning model.
    Preserves natural aspect ratio to avoid squashing portrait smartphone photos.
    Returns: (predicted_disease_name, confidence_score) or (predicted_disease, confidence, all_predictions)
    """
    if not load_dl_model(): # Ensure model is loaded before proceeding
        return (None, 0.0, {}) if return_all_preds else (None, 0.0)
        
    try: # Start inference error handling
        # 1. Preserve aspect ratio by center-cropping elongated phone images to square
        h, w = img.shape[:2]
        if abs(h - w) > min(h, w) * 0.15:
            min_dim = min(h, w)
            cy, cx = h // 2, w // 2
            img_square = img[cy - min_dim//2 : cy + min_dim//2, cx - min_dim//2 : cx + min_dim//2]
        else:
            img_square = img

        # 2. Convert to RGB and resize to 224x224
        img_rgb = cv2.cvtColor(img_square, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img_rgb, (224, 224), interpolation=cv2.INTER_AREA)
        
        # 3. Expand dims to create batch: shape (1, 224, 224, 3)
        img_array = np.expand_dims(img_resized, axis=0).astype('float32') / 255.0
        
        # 4. Predict using fast direct model call
        predictions = _model(img_array, training=False).numpy()[0]
        predicted_class_idx = int(np.argmax(predictions))
        confidence = float(predictions[predicted_class_idx])
        
        raw_label = _class_labels[predicted_class_idx]
        disease_name = raw_label.title()
        
        all_preds = {
            _class_labels[i].title(): float(predictions[i])
            for i in range(len(predictions))
            if i in _class_labels
        }

        if return_all_preds:
            return disease_name, confidence, all_preds
        return disease_name, confidence
        
    except Exception as e: # Catch inference errors
        print(f"[DL] Inference error: {e}", file=sys.stderr) # Log error message
        return (None, 0.0, {}) if return_all_preds else (None, 0.0)
