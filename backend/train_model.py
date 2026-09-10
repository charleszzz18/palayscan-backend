import os # Import OS module for file path manipulations
import sys # Import System module for exiting and logging

def train(): # Main training function definition
    try: # Start error protection block for dependencies
        import tensorflow as tf # Import TensorFlow core library
        # pyrefly: ignore [missing-import]
        from tensorflow.keras.preprocessing.image import ImageDataGenerator # Import data loading utilities
        # pyrefly: ignore [missing-import]
        from tensorflow.keras.applications import MobileNetV2 # Import pre-trained MobileNetV2 architecture
        from tensorflow.keras.layers import Dense, GlobalAveragePooling2D, Dropout # Import neural network layers
        from tensorflow.keras.models import Model # Import Model class for defining the network
        from tensorflow.keras.optimizers import Adam # Import Adam optimizer for gradient descent
        from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint # Import training monitoring tools
    except ImportError: # Catch missing library errors
        print("[ERROR] TensorFlow is not installed. Please run 'pip install tensorflow'") # Advise user
        sys.exit(1) # Stop script execution

    DATASET_DIR = "dataset" # Define the root folder containing training images
    if not os.path.exists(DATASET_DIR): # Check if the folder exists on disk
        print(f"[ERROR] Dataset folder '{DATASET_DIR}' not found in the backend folder.") # Log error
        print("Please create a 'dataset' folder and put the extracted Kaggle folders inside it.") # Advise user
        sys.exit(1) # Stop execution

    # Auto-detect the actual directory containing the classes (handles nested Kaggle downloads)
    actual_data_dir = DATASET_DIR # Initialize detection variable
    for root, dirs, files in os.walk(DATASET_DIR): # Walk through directory structure
        if len(dirs) >= 2 and not any(d.startswith('.') for d in dirs): # Detect folders with multiple subfolders
            actual_data_dir = root # Set as the training source
            break # Exit loop once found

    # Group 'Rust' dataset folder into 'Others' class due to limited Rust samples
    import shutil
    rust_dir = os.path.join(actual_data_dir, "Rust")
    others_dir = os.path.join(actual_data_dir, "Others")
    if os.path.exists(rust_dir):
        print("[INFO] Merging 'Rust' images into 'Others' class folder due to limited dataset...")
        os.makedirs(others_dir, exist_ok=True)
        for fname in os.listdir(rust_dir):
            src_file = os.path.join(rust_dir, fname)
            dst_file = os.path.join(others_dir, f"rust_{fname}")
            if os.path.isfile(src_file):
                shutil.move(src_file, dst_file)
        try:
            os.rmdir(rust_dir)
        except Exception:
            pass
        print("[INFO] Successfully merged 'Rust' into 'Others'.")

    print(f"[INFO] Loading dataset from: {actual_data_dir}") # Log the source path
    
    # Advanced Image Augmentation for higher precision (synthetically increases data diversity)
    datagen = ImageDataGenerator( # Initialize the generator
        rescale=1./255, # Normalize pixel values from [0, 255] to [0, 1]
        rotation_range=30, # Randomly rotate images up to 30 degrees
        width_shift_range=0.2, # Randomly shift images horizontally
        height_shift_range=0.2, # Randomly shift images vertically
        shear_range=0.2, # Apply random shearing transformations
        zoom_range=0.2, # Randomly zoom in/out of images
        horizontal_flip=True, # Randomly flip images horizontally
        fill_mode='nearest', # Strategy for filling empty pixels after rotation/shift
        validation_split=0.2 # Reserves 20% of the images for accuracy testing
    )

    train_generator = datagen.flow_from_directory( # Create training data stream
        actual_data_dir, # Source folder
        target_size=(224, 224), # Resize images to MobileNetV2 expected size
        batch_size=32, # Process 32 images at a time
        class_mode='categorical', # Use multi-class classification mode
        subset='training' # Use the 80% training slice
    )

    val_generator = datagen.flow_from_directory( # Create validation data stream
        actual_data_dir, # Source folder
        target_size=(224, 224), # Resize images
        batch_size=32, # Batch size
        class_mode='categorical', # Multi-class mode
        subset='validation' # Use the 20% validation slice
    )

    if train_generator.num_classes < 2: # Verify that at least two disease classes exist
        print("[ERROR] Less than 2 classes found. Please check dataset extraction.") # Log error
        sys.exit(1) # Stop execution

    # Save class indices (maps folder names to numerical IDs for later inference)
    import json # Import JSON library
    with open('class_indices.json', 'w') as f: # Open file for writing
        json.dump(train_generator.class_indices, f) # Write mapping dictionary
    print(f"[INFO] Found {train_generator.num_classes} classes.") # Log category count

    # ---------------------------------------------------------
    # BUILD HIGH-PRECISION MODEL (Fine-Tuning)
    # ---------------------------------------------------------
    print("[INFO] Building High-Precision Model...") # Log start
    base_model = MobileNetV2(weights='imagenet', include_top=False, input_shape=(224, 224, 3)) # Load pre-trained weights
    
    # Unfreeze the top 30 layers to let the AI learn specific leaf textures
    for layer in base_model.layers[:-30]: # Freeze early layers (general image features)
        layer.trainable = False # Disable learning for these
    for layer in base_model.layers[-30:]: # Unfreeze late layers (specific rice features)
        layer.trainable = True # Enable learning for these

    x = base_model.output # Get output of base model
    x = GlobalAveragePooling2D()(x) # Compress 2D features into 1D vector
    x = Dense(256, activation='relu')(x) # Add a fully connected layer with 256 neurons
    x = Dropout(0.5)(x) # Randomly disable 50% of neurons to prevent "memorizing" (overfitting)
    predictions = Dense(train_generator.num_classes, activation='softmax')(x) # Final layer for probability output

    model = Model(inputs=base_model.input, outputs=predictions) # Define the final model structure
    
    # Use a lower learning rate because we are fine-tuning pre-trained layers
    model.compile(optimizer=Adam(learning_rate=0.0001), loss='categorical_crossentropy', metrics=['accuracy']) # Setup loss and metric

    # ---------------------------------------------------------
    # SMART CALLBACKS (AI Brain Control)
    # ---------------------------------------------------------
    MODEL_PATH = "rice_model.h5" # Path where the final model will be saved
    
    # Stop early if the AI stops improving after 5 rounds (saves time and electricity)
    early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True, verbose=1)
    
    # Slow down studying if the AI gets confused (reduces learning rate to find fine details)
    reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=2, min_lr=1e-6, verbose=1)

    # Save the absolute best version of the model automatically during training
    checkpoint = ModelCheckpoint(MODEL_PATH, monitor='val_accuracy', save_best_only=True, verbose=1)

    print("[INFO] Starting Advanced Training (Up to 30 Epochs)...") # Log training start
    
    history = model.fit( # Begin training process
        train_generator, # Training stream
        epochs=30, # Run up to 30 training rounds
        validation_data=val_generator, # Validation stream
        callbacks=[early_stop, reduce_lr, checkpoint] # Active monitoring tools
    )

    print(f"[SUCCESS] Advanced Training Complete! The most precise model was saved to '{MODEL_PATH}'!") # Final success log

if __name__ == "__main__": # Run check
    train() # Invoke training
