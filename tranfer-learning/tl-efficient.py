import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

class ThermalImageClassifierEfficientNet:
    def __init__(self, train_dir: str, val_dir: str, test_dir: str, num_classes: int = 12):
        """
        Initialize the Thermal Image Classifier using EfficientNetV2B3.
        
        Args:
            train_dir: Directory containing training data
            val_dir: Directory containing validation data
            test_dir: Directory containing test data
            num_classes: Number of classification categories
        """
        self.num_classes = num_classes
        self.height = 75
        self.width = int(self.height * (320/240))
        self.image_size = (self.height, self.width)
        
        # Check GPU availability
        self._setup_gpu()
        
        # Initialize datasets
        self.train_ds = self._prepare_dataset(train_dir)
        self.val_ds = self._prepare_dataset(val_dir)
        self.test_ds = self._prepare_dataset(test_dir)
        
        # Initialize model attributes
        self.model = None
        self.history = None

    def _setup_gpu(self):
        """Configure GPU if available."""
        if not tf.config.list_physical_devices('GPU'):
            print("No GPU detected. Training will proceed on CPU.")
        else:
            print(f"Using GPU: {tf.config.list_physical_devices('GPU')}")
            
    @tf.autograph.experimental.do_not_convert
    def _grey_to_rgb(self, image):
        """Convert grayscale images to RGB if needed."""
        return tf.image.grayscale_to_rgb(image) if image.shape[-1] == 1 else image

    def _prepare_dataset(self, directory: str, batch_size: int = 32):
        """
        Prepare and augment the dataset.
        
        Args:
            directory: Path to dataset directory
            batch_size: Batch size for training
            
        Returns:
            Preprocessed tensorflow dataset
        """
        ds = tf.keras.utils.image_dataset_from_directory(
            directory,
            image_size=self.image_size,
            batch_size=batch_size
        )
        
        # Apply one-hot encoding and convert to RGB
        ds = ds.map(
            lambda x, y: (x, tf.one_hot(y, self.num_classes))
        ).map(
            lambda x, y: (self._grey_to_rgb(x), y)
        )
        
        return ds.cache().prefetch(buffer_size=tf.data.AUTOTUNE)

    def build_model(self):
        """Build and compile the model architecture using EfficientNetV2B3."""
        # Data augmentation layers
        input_layer = tf.keras.layers.Input(shape=(self.height, self.width, 3))
        augmentation = self._create_augmentation_model(input_layer)
        
        # Load pre-trained EfficientNetV2B3
        pretrained = tf.keras.applications.EfficientNetV2B3(
            include_top=False,
            weights='imagenet',
            input_shape=(self.height, self.width, 3)
        )
        pretrained.trainable = False
        
        # Build final model
        x = augmentation.output
        x = pretrained(x)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        output = tf.keras.layers.Dense(self.num_classes, activation='sigmoid')(x)
        
        self.model = tf.keras.models.Model(inputs=augmentation.input, outputs=output)
        
        self._compile_model()
        
    def _create_augmentation_model(self, input_layer):
        """Create data augmentation pipeline optimized for EfficientNetV2."""
        x = tf.keras.layers.Resizing(self.height, self.width)(input_layer)
        x = tf.keras.layers.RandomBrightness((-0.5, 0.5))(x)
        x = tf.keras.layers.RandomContrast(0.9)(x)
        x = tf.keras.layers.RandomFlip()(x)
        x = tf.keras.layers.Lambda(
            tf.keras.applications.efficientnet_v2.preprocess_input
        )(x)
        
        return tf.keras.models.Model(inputs=input_layer, outputs=x)
    
    def _compile_model(self, learning_rate: float = 1e-3):
        """Compile the model with optimizer and loss function."""
        self.model.compile(
            optimizer=tf.keras.optimizers.Nadam(learning_rate=learning_rate),
            loss=tf.keras.losses.CategoricalCrossentropy(name="val_loss"),
            metrics=[tf.keras.metrics.Accuracy()]
        )

    def train(self, epochs: int = 40, model_path: str = "thermal_model_efficientnet.keras"):
        """
        Train the model.
        
        Args:
            epochs: Number of training epochs
            model_path: Path to save the best model
        """
        callbacks = [
            tf.keras.callbacks.ModelCheckpoint(
                model_path, 
                save_best_only=True, 
                monitor="val_binary_accuracy"
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="loss",
                factor=0.1,
                patience=10,
                verbose=1
            )
        ]
        
        self.history = self.model.fit(
            self.train_ds,
            validation_data=self.val_ds,
            epochs=epochs,
            callbacks=callbacks
        )
    
    def fine_tune(self, start_layer: int = 402):
        """
        Fine-tune the last layers of the model starting from a specific layer.
        
        Args:
            start_layer: Layer index to start fine-tuning from
        """
        for layer in self.model.layers[2].layers[start_layer:]:
            layer.trainable = True
            
        self._compile_model(learning_rate=1e-4)  # Lower learning rate for fine-tuning
        
    def evaluate(self, dataset='val'):
        """
        Evaluate the model on the specified dataset.
        
        Args:
            dataset: Which dataset to evaluate on ('train', 'val', or 'test')
        """
        eval_ds = {
            'train': self.train_ds,
            'val': self.val_ds,
            'test': self.test_ds
        }.get(dataset)
        
        return self.model.evaluate(eval_ds)
    
    def save_model(self, path: str):
        """Save the trained model."""
        self.model.save(path)

    @classmethod
    def load_model(cls, path: str):
        """Load a saved model."""
        return tf.keras.models.load_model(
            path,
            custom_objects={
                'preprocess_input': tf.keras.applications.efficientnet_v2.preprocess_input
            }
        )

    def plot_training_history(self):
        """Plot training history."""
        if self.history is None:
            print("No training history available. Train the model first.")
            return
            
        plt.figure(figsize=(12, 4))
        
        plt.subplot(1, 2, 1)
        plt.plot(self.history.history['loss'], label='Training Loss')
        plt.plot(self.history.history['val_loss'], label='Validation Loss')
        plt.title('Model Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
        plt.subplot(1, 2, 2)
        plt.plot(self.history.history['accuracy'], label='Training Accuracy')
        plt.plot(self.history.history['val_accuracy'], label='Validation Accuracy')
        plt.title('Model Accuracy')
        plt.xlabel('Epoch')
        plt.ylabel('Accuracy')
        plt.legend()
        
        plt.tight_layout()
        plt.show()

# Usage example:
if __name__ == "__main__":
    # Initialize paths
    base_dir = Path("/content/drive/MyDrive/Thermal Imaging Project/Greyscale Images/Dataset")
    model_path = base_dir / "EfficientNetV2B3.keras"
    
    # Create classifier instance
    classifier = ThermalImageClassifierEfficientNet(
        train_dir=str(base_dir / "train"),
        val_dir=str(base_dir / "val"),
        test_dir=str(base_dir / "test")
    )
    
    # Train model
    classifier.build_model()
    classifier.train(epochs=40, model_path=str(model_path))
    
    # Plot training progress
    classifier.plot_training_history()
    
    # Fine-tune model
    classifier.fine_tune(start_layer=402)
    classifier.train(epochs=40, model_path=str(model_path))
    
    # Evaluate and save
    classifier.evaluate('val')
    classifier.save_model(str(model_path))
