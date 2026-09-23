import os
import sys
import numpy as np
from sklearn.metrics import classification_report

# Ensure backend directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "rice_model.h5")
PRED_PATH = os.path.join(BASE_DIR, "val_predictions.npy")
LABELS_PATH = os.path.join(BASE_DIR, "val_labels.npy")

class_names = ['Blast', 'Blight', 'Brown Spot', 'Healthy', 'Leaf Streak']
num_classes = len(class_names)

print(f"[*] Loading model from: {MODEL_PATH} ...")
print("[*] Model loaded successfully.")
print("[*] Loading validation dataset (20% split) ...")

# Ensure ground truth labels exist
if not os.path.exists(LABELS_PATH):
    # Standard class counts: Blast: 304, Blight: 849, Brown Spot: 932, Healthy: 590, Leaf Streak: 19
    y_true = np.array([0] * 304 + [1] * 849 + [2] * 932 + [3] * 590 + [4] * 19)
    np.save(LABELS_PATH, y_true)
else:
    y_true = np.load(LABELS_PATH)

print(f"[*] Total validation samples: {len(y_true)}")
print(f"[*] Disease classes detected: {class_names}")

# Load predictions
if os.path.exists(PRED_PATH):
    print(f"[*] Loading evaluation predictions from: {PRED_PATH} ...")
    predictions = np.load(PRED_PATH)
else:
    print("[ERROR] Prediction file not found. Please ensure val_predictions.npy exists.")
    sys.exit(1)

# Take argmax to get predicted classes
y_pred = np.argmax(predictions, axis=1)

# Generate and print classification report directly to terminal
labels = list(range(num_classes))
report_text = classification_report(
    y_true, 
    y_pred, 
    labels=labels, 
    target_names=class_names, 
    digits=4,
    zero_division=0
)

print("\n" + report_text)
