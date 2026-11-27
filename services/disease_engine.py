"""
services/disease_engine.py - AI Crop Disease Detection Engine

Real CNN (EfficientNetB0, TensorFlow/Keras) inference for plant leaf disease
classification. Replaces the previous simulated/diagnosis-by-filename approach.

The trained model (best_plant_disease_finetuned.keras) supports 38 classes.
Class labels follow the format "Crop___Disease" (e.g. "Tomato___Early_blight",
"Tomato___healthy") and are loaded from class_names.json. The output index
maps exactly to the JSON ordering.

CNN responsibilities:
  - Identify crop + disease from a leaf image
  - Return confidence score and top-3 predictions

Gemini (services/disease_advisory_service.py) is responsible for advisory only
and must NOT identify or override the CNN prediction.
"""

import json
import logging
import os
import threading
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, UnidentifiedImageError

from tensorflow import keras

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "models", "plant_disease")
MODEL_PATH = os.path.join(MODEL_DIR, "best_plant_disease_finetuned.keras")
CLASS_NAMES_PATH = os.path.join(MODEL_DIR, "class_names.json")

INPUT_SIZE = (224, 224)
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Confidence tiers (configurable)
HIGH_CONFIDENCE_THRESHOLD = 0.70
MODERATE_CONFIDENCE_THRESHOLD = 0.40

# Module-level singletons (lazy-loaded, never reloaded per prediction)
_model = None
_model_lock = threading.Lock()
_class_names = None
_class_names_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Model / class-name loading
# ---------------------------------------------------------------------------

def load_class_names() -> List[str]:
    """Load class names from JSON. Output index maps exactly to JSON ordering."""
    global _class_names
    with _class_names_lock:
        if _class_names is None:
            if not os.path.exists(CLASS_NAMES_PATH):
                raise FileNotFoundError(
                    f"Class names file not found: {CLASS_NAMES_PATH}"
                )
            with open(CLASS_NAMES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("Class names file must contain a non-empty list.")
            _class_names = [str(c) for c in data]
            logger.info("Loaded %d disease class names", len(_class_names))
        return list(_class_names)


def load_disease_model():
    """
    Load the Keras model once using a lazy-loaded singleton.
    Downloads the model from PLANT_DISEASE_MODEL_URL if it is missing locally.
    Never reloads the model for every prediction.
    """
    global _model
    with _model_lock:
        if _model is None:
            model_url = os.getenv("PLANT_DISEASE_MODEL_URL")
            if not os.path.exists(MODEL_PATH):
                if model_url:
                    logger.info(
                        "Disease model not found locally; downloading from %s",
                        model_url,
                    )
                    _download_model(model_url)
                else:
                    raise FileNotFoundError(
                        f"Disease model not found: {MODEL_PATH} "
                        "and PLANT_DISEASE_MODEL_URL is not set."
                    )
            _model = keras.models.load_model(MODEL_PATH)
            expected = (None, 224, 224, 3)
            if tuple(_model.input_shape) != expected:
                logger.warning(
                    "Unexpected model input shape: %s (expected %s)",
                    _model.input_shape,
                    expected,
                )
            logger.info("Disease CNN model loaded: %s", MODEL_PATH)
        return _model


def _download_model(url: str) -> None:
    """Download the disease model from a URL to MODEL_PATH."""
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)
        urllib.request.urlretrieve(url, MODEL_PATH)
        logger.info("Disease model downloaded to: %s", MODEL_PATH)
    except Exception as exc:
        logger.error("Failed to download disease model from %s: %s", url, exc)
        raise


def unload_disease_model() -> None:
    """Reset singletons (test helper only)."""
    global _model, _class_names
    with _model_lock:
        _model = None
    with _class_names_lock:
        _class_names = None


# ---------------------------------------------------------------------------
# Image validation & preprocessing
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    """Check file extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def allowed_mime(mime_type: Optional[str]) -> bool:
    """Check MIME type."""
    return mime_type in ALLOWED_MIME_TYPES


def preprocess_leaf_image(image_file) -> np.ndarray:
    """
    Accept an uploaded file-like object, validate it, and preprocess for the CNN.

    Steps:
      1. Validate image integrity (PIL verify + re-open)
      2. Convert to RGB
      3. Resize to 224 x 224
      4. Convert to float32 numpy array in RAW [0, 255] range

    IMPORTANT: The saved Keras model already contains internal Rescaling and
    Normalization layers (rescaling -> normalization -> rescaling_1 inside
    efficientnetb0). Therefore NO external normalization (no /255, no
    EfficientNet preprocess_input) is applied here, to avoid double
    normalization. Pixel values are passed through raw in [0, 255].

    Returns:
        np.ndarray of shape (1, 224, 224, 3), dtype float32.
    """
    image_file.seek(0)

    try:
        img = Image.open(image_file)
    except UnidentifiedImageError:
        raise ValueError(
            "Unable to identify image file. It may be corrupted or an unsupported format."
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Failed to open image: {exc}")

    # Verify integrity, then re-open (verify() can leave the file in an odd state)
    try:
        img.verify()
    except Exception:
        raise ValueError("Image integrity check failed (corrupted image).")

    image_file.seek(0)
    try:
        img = Image.open(image_file)
    except Exception as exc:
        raise ValueError(f"Failed to re-open image after verification: {exc}")

    # Convert to RGB
    img = img.convert("RGB")

    # Resize to model input size
    img = img.resize(INPUT_SIZE, Image.Resampling.BILINEAR)

    # Raw [0, 255] float32 array; model handles internal rescaling/normalization
    arr = np.asarray(img, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("Image must be a 3-channel RGB image.")

    arr = np.expand_dims(arr, axis=0)  # (1, 224, 224, 3)
    return arr


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def predict_disease(image_array: np.ndarray) -> Dict[str, Any]:
    """
    Run CNN inference on a preprocessed image array.

    The model's final layer is a Dense with softmax activation, so the output
    is already normalized probabilities. softmax is NOT applied again.

    Returns:
        dict with predicted_class, crop_name, disease_name, status, confidence,
        top_predictions, num_classes.
    """
    model = load_disease_model()
    class_names = load_class_names()

    predictions = model.predict(image_array, verbose=0)  # training=False
    probabilities = predictions[0]  # shape (38,)

    top_idx = int(np.argmax(probabilities))
    top_confidence = float(probabilities[top_idx])

    # Top-3 diagnostic predictions
    top3_indices = np.argsort(probabilities)[::-1][:3]
    top_predictions = [
        {
            "class": class_names[int(idx)],
            "confidence": float(probabilities[int(idx)]),
        }
        for idx in top3_indices
    ]

    predicted_class = class_names[top_idx]
    crop_name, disease_name, status = _parse_class_label(predicted_class)

    return {
        "predicted_class": predicted_class,
        "crop_name": crop_name,
        "disease_name": disease_name,
        "status": status,
        "confidence": top_confidence,
        "top_predictions": top_predictions,
        "num_classes": len(class_names),
    }


def _parse_class_label(class_label: str) -> Tuple[str, str, str]:
    """
    Parse a 'Crop___Disease' label into (crop_name, disease_name, status).

    Examples:
        "Tomato___Early_blight"  -> ("Tomato", "Early Blight", "diseased")
        "Tomato___healthy"       -> ("Tomato", "Healthy", "healthy")
    """
    if "___" in class_label:
        crop_part, disease_part = class_label.split("___", 1)
    else:
        crop_part, disease_part = class_label, "healthy"

    crop_name = crop_part.replace("_", " ").strip()

    disease_part_clean = disease_part.strip()
    is_healthy = disease_part_clean.lower() == "healthy"
    status = "healthy" if is_healthy else "diseased"

    if is_healthy:
        disease_name = "Healthy"
    else:
        disease_name = " ".join(
            w.capitalize() for w in disease_part_clean.replace("_", " ").split()
        )

    return crop_name, disease_name, status


def get_prediction_details(prediction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attach confidence tier and a human-readable message to a prediction dict
    without altering the underlying CNN result.

    Tiers:
        high     (>= 0.70)  -> show prediction with confidence
        moderate (>= 0.40)  -> show prediction with a caution message
        low      (< 0.40)   -> request another photo; not definitive
    """
    confidence = float(prediction.get("confidence", 0.0))

    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        tier = "high"
        message = None
    elif confidence >= MODERATE_CONFIDENCE_THRESHOLD:
        tier = "moderate"
        message = (
            "Model confidence is moderate. "
            "Consider retaking a clearer photo of the leaf for confirmation."
        )
    else:
        tier = "low"
        message = (
            "Model confidence is low. Please upload a clearer, well-lit leaf "
            "photograph; the result below is not definitive."
        )

    details = dict(prediction)
    details["confidence_tier"] = tier
    details["confidence_percentage"] = round(confidence * 100, 2)
    details["confidence_message"] = message
    return details


def get_all_classes() -> List[Dict[str, str]]:
    """
    Return all 38 supported classes with parsed crop/disease info.
    Used to populate the UI crop selector / sample list.
    """
    class_names = load_class_names()
    classes = []
    for label in class_names:
        crop_name, disease_name, status = _parse_class_label(label)
        classes.append(
            {
                "label": label,
                "crop": crop_name,
                "disease": disease_name,
                "status": status,
            }
        )
    return classes
