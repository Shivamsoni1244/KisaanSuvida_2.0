"""
routes/disease_routes.py - AI Crop Disease Detection endpoints
"""

import os
from flask import Blueprint, render_template, request, jsonify, session, current_app
from services.disease_engine import diagnose_crop_image, get_all_samples, DISEASE_CATALOG

disease_bp = Blueprint("disease", __name__)


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


@disease_bp.route("/disease-detection")
def disease_detection():
    user = get_current_user() or {}
    samples = get_all_samples()
    # Initial sample disease for visual demonstration
    initial_diagnosis = DISEASE_CATALOG["rice_blast"]
    
    return render_template(
        "disease_detection.html",
        user=user,
        samples=samples,
        initial_diagnosis=initial_diagnosis,
        active_page="disease"
    )


@disease_bp.route("/api/disease-detection/diagnose", methods=["POST"])
def api_diagnose():
    """
    Accepts image file upload or sample_id.
    Designed for seamless integration with PyTorch / ONNX deep learning models.
    """
    sample_id = request.form.get("sample_id")
    crop_hint = request.form.get("crop", "Rice (Paddy)")
    uploaded_file = request.files.get("leaf_image")
    
    filename = None
    if uploaded_file and uploaded_file.filename:
        filename = uploaded_file.filename
        # Save temporarily if needed for future training or batch processing
        upload_folder = os.path.join(current_app.root_path, "static", "images", "uploads")
        os.makedirs(upload_folder, exist_ok=True)
        # Safe filename
        safe_name = os.path.basename(filename)
        save_path = os.path.join(upload_folder, safe_name)
        try:
            uploaded_file.save(save_path)
        except Exception:
            pass
            
    diagnosis = diagnose_crop_image(
        filename=filename,
        crop_hint=crop_hint,
        sample_id=sample_id
    )
    
    return jsonify({
        "success": True,
        "diagnosis": diagnosis
    })


@disease_bp.route("/api/disease-detection/samples")
def api_samples():
    return jsonify({
        "success": True,
        "samples": get_all_samples()
    })
