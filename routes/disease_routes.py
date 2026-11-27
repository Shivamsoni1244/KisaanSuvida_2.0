"""
routes/disease_routes.py - AI Crop Disease Detection endpoints

Flow:
  1. Receive uploaded leaf image (or class sample label).
  2. Validate file type, MIME type, size and image integrity.
  3. Run real CNN inference (services/disease_engine.py).
  4. Pass prediction details to Gemini disease advisory
     (services/disease_advisory_service.py).
  5. Return structured JSON. Gemini failures do NOT fail the diagnosis.
"""

import os
from typing import Optional

from flask import Blueprint, current_app, jsonify, render_template, request, session

from services.disease_advisory_service import get_disease_advisory
from services.disease_engine import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    allowed_file,
    allowed_mime,
    get_all_classes,
    get_prediction_details,
    load_class_names,
    load_disease_model,
    preprocess_leaf_image,
    predict_disease,
    unload_disease_model,
)

disease_bp = Blueprint("disease", __name__)

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


def _read_uploaded_file(uploaded_file) -> bytes:
    """Read uploaded file into memory and validate size."""
    uploaded_file.seek(0, os.SEEK_END)
    size = uploaded_file.tell()
    uploaded_file.seek(0)
    if size == 0:
        raise ValueError("Uploaded file is empty.")
    if size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large ({size / (1024 * 1024):.1f} MB). Max 16 MB allowed."
        )
    data = uploaded_file.read()
    return data


def _build_sample_image_bytes(class_label: str) -> Optional[bytes]:
    """
    Samples are no longer shipped as pre-made images (those were SVG
    illustrations that do not represent real leaves). Return None so the
    caller falls back to requiring a real upload.
    """
    return None


@disease_bp.route("/disease-detection")
def disease_detection():
    user = get_current_user() or {}
    classes = get_all_classes()
    initial_diagnosis = {
        "disease_name": "—",
        "scientific_name": "—",
        "pathogen_type": "—",
        "default_confidence": 0,
        "severity": "—",
        "description": "Upload a leaf image to get a diagnosis.",
        "symptoms": [],
        "chemical_treatment": [],
        "organic_treatment": [],
        "kisaanbot_prompt": "",
    }
    return render_template(
        "disease_detection.html",
        user=user,
        classes=classes,
        active_page="disease",
        initial_diagnosis=initial_diagnosis,
    )


@disease_bp.route("/api/disease-detection/diagnose", methods=["POST"])
def api_diagnose():
    """
    Accepts an uploaded leaf image file.
    Returns structured JSON with CNN prediction + Gemini advisory.
    """
    uploaded_file = request.files.get("leaf_image")
    language = request.form.get("language", "en")
    symptoms = request.form.get("symptoms") or None
    location = request.form.get("location") or None

    # ---- Validate image upload ----
    if not uploaded_file or not uploaded_file.filename:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "No leaf image uploaded. Please select a JPG, PNG or WEBP image.",
                }
            ),
            400,
        )

    filename = uploaded_file.filename
    if not allowed_file(filename):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Unsupported file type. Please upload JPG, PNG or WEBP images only.",
                }
            ),
            400,
        )

    mime_type = uploaded_file.mimetype or ""
    if mime_type and not allowed_mime(mime_type):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Unsupported image format. Please upload JPG, PNG or WEBP images only.",
                }
            ),
            400,
        )

    try:
        image_bytes = _read_uploaded_file(uploaded_file)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    # ---- Preprocess + CNN inference ----
    import io

    try:
        image_array = preprocess_leaf_image(io.BytesIO(image_bytes))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger = current_app.logger
        logger.exception("Image preprocessing failed")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Unable to process the uploaded image. Please upload a clear leaf photograph.",
                }
            ),
            400,
        )

    try:
        prediction = predict_disease(image_array)
    except FileNotFoundError as exc:
        current_app.logger.error("Disease model missing: %s", exc)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Disease detection model is not available on the server.",
                }
            ),
            503,
        )
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.exception("CNN inference failed")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Disease inference failed. Please try again with another image.",
                }
            ),
            503,
        )

    prediction_details = get_prediction_details(prediction)

    # ---- Gemini advisory (must NOT fail the diagnosis) ----
    advisory = None
    advisory_error = None
    try:
        advisory = get_disease_advisory(
            crop_name=prediction_details["crop_name"],
            disease_name=prediction_details["disease_name"],
            scientific_name=None,  # scientific name not stored in class labels
            confidence=prediction_details["confidence"],
            language=language,
            symptoms=symptoms,
            location=location,
        )
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.exception("Gemini disease advisory failed")
        advisory_error = "Advisory generation temporarily unavailable."

    return jsonify(
        {
            "success": True,
            "prediction": prediction_details,
            "advisory": advisory,
            "advisory_error": advisory_error,
        }
    )


@disease_bp.route("/api/disease-detection/classes")
def api_classes():
    """Return all supported model classes (38)."""
    try:
        classes = get_all_classes()
    except FileNotFoundError as exc:
        current_app.logger.error("Class names missing: %s", exc)
        return jsonify({"success": False, "error": "Class names not available."}), 503
    return jsonify({"success": True, "classes": classes})
