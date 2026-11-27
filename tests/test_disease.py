"""
tests/test_disease.py - Tests for the integrated CNN plant disease model +
Gemini disease advisory module.

Covers:
- Model loading (lazy singleton)
- Class-name loading (38 classes, index order matches JSON)
- Input image preprocessing (shape, dtype, RGB)
- Valid image prediction (class among the 38 supported classes)
- Invalid image rejection (corrupted / unsupported / empty)
- Output-to-class mapping ("Crop___Disease" parsing)
- Confidence handling (high / moderate / low tiers)
- Gemini advisory response generation
- Gemini API failure (falls back, does not fail diagnosis)
- CNN failure handling
- Existing disease endpoint integration
- Unaffected modules: login, dashboard, crop recommendation, etc. (inherited)
"""

import io
import json
import os
import sys
from unittest import mock

import numpy as np
import pytest
from PIL import Image

# Ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app  # noqa: E402
from services import disease_engine  # noqa: E402
from services.disease_engine import (  # noqa: E402
    load_disease_model,
    load_class_names,
    preprocess_leaf_image,
    predict_disease,
    get_prediction_details,
    unload_disease_model,
    ALLOWED_EXTENSIONS,
)

os.environ.setdefault("GEMINI_API_KEY", "")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_profile"] = {
                "id": 1,
                "name": "Test Farmer",
                "state": "Punjab",
                "district": "Ludhiana",
                "preferred_language": "en",
                "role": "Farmer",
            }
            sess["csrf_token"] = "test_csrf_123"
        yield client


@pytest.fixture(scope="module", autouse=True)
def load_model_once():
    """Load the CNN model once for the whole test module."""
    load_disease_model()
    load_class_names()
    yield
    unload_disease_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_file(color=(34, 139, 34), size=(300, 200), fmt="PNG"):
    """Return a BytesIO holding a small RGB image."""
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

class TestModelLoading:
    def test_load_disease_model_returns_model(self):
        model = load_disease_model()
        assert model is not None

    def test_model_is_singleton(self):
        m1 = load_disease_model()
        m2 = load_disease_model()
        assert m1 is m2

    def test_model_input_and_output_shape(self):
        model = load_disease_model()
        assert tuple(model.input_shape) == (None, 224, 224, 3)
        assert tuple(model.output_shape) == (None, 38)


# ---------------------------------------------------------------------------
# Class names
# ---------------------------------------------------------------------------

class TestClassNames:
    def test_load_class_names_returns_38(self):
        names = load_class_names()
        assert len(names) == 38

    def test_class_names_match_json_order(self):
        with open(
            os.path.join(ROOT, "models", "plant_disease", "class_names.json"),
            "r",
            encoding="utf-8",
        ) as f:
            expected = json.load(f)
        names = load_class_names()
        assert names == expected

    def test_tomato_early_blight_present(self):
        names = load_class_names()
        assert "Tomato___Early_blight" in names
        assert "Tomato___healthy" in names

    def test_no_rice_wheat_cotton_classes(self):
        names = load_class_names()
        for n in names:
            assert not n.startswith("Rice")
            assert not n.startswith("Wheat")
            assert not n.startswith("Cotton")


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

class TestPreprocessing:
    def test_preprocess_returns_correct_shape_and_dtype(self):
        arr = preprocess_leaf_image(_make_image_file())
        assert arr.shape == (1, 224, 224, 3)
        assert arr.dtype == np.float32

    def test_preprocess_raw_zero_to_255_range(self):
        arr = preprocess_leaf_image(_make_image_file(color=(10, 200, 50)))
        assert arr.min() >= 0.0
        assert arr.max() <= 255.0
        # Not externally normalized (values remain in [0, 255])
        assert arr.max() > 1.0

    def test_preprocess_converts_to_rgb(self):
        # Grayscale source image must become 3-channel RGB
        buf = io.BytesIO()
        Image.new("L", (100, 100), color=128).save(buf, format="PNG")
        buf.seek(0)
        arr = preprocess_leaf_image(buf)
        assert arr.shape[3] == 3

    def test_preprocess_rejects_corrupted_image(self):
        with pytest.raises(ValueError):
            preprocess_leaf_image(io.BytesIO(b"not an image"))

    def test_preprocess_rejects_empty_file(self):
        with pytest.raises(ValueError):
            preprocess_leaf_image(io.BytesIO(b""))

    def test_allowed_extensions(self):
        assert "jpg" in ALLOWED_EXTENSIONS
        assert "png" in ALLOWED_EXTENSIONS
        assert "webp" in ALLOWED_EXTENSIONS
        assert "exe" not in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
class TestPrediction:
    def test_valid_image_produces_supported_class(self):
        pred = predict_disease(preprocess_leaf_image(_make_image_file()))
        names = load_class_names()
        assert pred["predicted_class"] in names
        assert pred["num_classes"] == 38
        assert 0.0 <= pred["confidence"] <= 1.0
        assert len(pred["top_predictions"]) == 3
        assert pred["crop_name"]
        assert pred["disease_name"]
        assert pred["status"] in ("healthy", "diseased")

    def test_top_three_sorted_descending(self):
        pred = predict_disease(preprocess_leaf_image(_make_image_file()))
        confs = [p["confidence"] for p in pred["top_predictions"]]
        assert confs == sorted(confs, reverse=True)

    def test_predicted_class_in_top_predictions(self):
        pred = predict_disease(preprocess_leaf_image(_make_image_file()))
        top_classes = [p["class"] for p in pred["top_predictions"]]
        assert pred["predicted_class"] in top_classes

    def test_parse_early_blight(self):
        crop, disease, status = disease_engine._parse_class_label("Tomato___Early_blight")
        assert crop == "Tomato"
        assert disease == "Early Blight"
        assert status == "diseased"

    def test_parse_healthy(self):
        crop, disease, status = disease_engine._parse_class_label("Tomato___healthy")
        assert crop == "Tomato"
        assert disease == "Healthy"
        assert status == "healthy"

    def test_parse_potato_late_blight(self):
        crop, disease, status = disease_engine._parse_class_label("Potato___Late_blight")
        assert crop == "Potato"
        assert disease == "Late Blight"
        assert status == "diseased"

    def test_get_all_classes_count(self):
        classes = disease_engine.get_all_classes()
        assert len(classes) == 38


# ---------------------------------------------------------------------------
# Confidence handling
# ---------------------------------------------------------------------------

class TestConfidenceHandling:
    def test_high_confidence_tier(self):
        details = get_prediction_details({
            "predicted_class": "Tomato___Early_blight",
            "confidence": 0.90,
        })
        assert details["confidence_tier"] == "high"
        assert details["confidence_percentage"] == 90.0
        assert details["confidence_message"] is None

    def test_moderate_confidence_tier(self):
        details = get_prediction_details({
            "predicted_class": "Tomato___Early_blight",
            "confidence": 0.55,
        })
        assert details["confidence_tier"] == "moderate"
        assert details["confidence_message"] is not None

    def test_low_confidence_tier(self):
        details = get_prediction_details({
            "predicted_class": "Tomato___Early_blight",
            "confidence": 0.20,
        })
        assert details["confidence_tier"] == "low"
        assert "not definitive" in details["confidence_message"]

    def test_boundary_high(self):
        details = get_prediction_details({"confidence": 0.70})
        assert details["confidence_tier"] == "high"

    def test_boundary_moderate(self):
        details = get_prediction_details({"confidence": 0.40})
        assert details["confidence_tier"] == "moderate"


# ---------------------------------------------------------------------------
# Gemini advisory (mocked / fallback)
# ---------------------------------------------------------------------------

class TestGeminiAdvisory:
    def test_fallback_advisory_when_no_api_key(self):
        from services import disease_advisory_service as das
        with mock.patch.object(das, "_call_gemini_disease_api", return_value=None):
            result = das.get_disease_advisory(
                crop_name="Tomato",
                disease_name="Early Blight",
                confidence=0.9,
                language="en",
            )
        assert "disease_overview" in result
        assert "symptoms" in result
        assert result["source"] == "fallback"

    def test_fallback_advisory_hindi(self):
        from services import disease_advisory_service as das
        with mock.patch.object(das, "_call_gemini_disease_api", return_value=None):
            result = das.get_disease_advisory(
                crop_name="Tomato",
                disease_name="Early Blight",
                confidence=0.9,
                language="hi",
            )
        assert result["source"] == "fallback"

    def test_malformed_json_falls_back(self):
        from services import disease_advisory_service as das
        with mock.patch.object(
            das, "_call_gemini_disease_api", return_value="not json at all"
        ):
            result = das.get_disease_advisory(
                crop_name="Tomato",
                disease_name="Early Blight",
                confidence=0.9,
                language="en",
            )
        assert result["source"] == "fallback"

    def test_valid_gemini_json_returned(self):
        from services import disease_advisory_service as das
        fake = {
            "disease_overview": "Overview text.",
            "symptoms": ["Symptom 1", "Symptom 2"],
            "causes_and_spread": "Causes text.",
            "treatment_options": ["Treatment 1"],
            "organic_management": ["Organic 1"],
            "prevention_methods": ["Prevention 1"],
            "immediate_actions": ["Action 1"],
            "disclaimer": "Disclaimer text.",
        }
        # Clear advisory cache and set a fake key so the API branch is exercised.
        das._advisory_cache.clear()
        os.environ["GEMINI_API_KEY"] = "fake-test-key"
        try:
            with mock.patch.object(
                das, "_call_gemini_disease_api", return_value=json.dumps(fake)
            ):
                result = das.get_disease_advisory(
                    crop_name="Tomato",
                    disease_name="Early Blight",
                    confidence=0.9,
                    language="en",
                )
        finally:
            os.environ["GEMINI_API_KEY"] = ""
        assert result["source"] == "gemini"
        assert result["disease_overview"] == "Overview text."
        assert result["symptoms"] == ["Symptom 1", "Symptom 2"]

    def test_hinglish_language_normalized(self):
        from services import disease_advisory_service as das
        with mock.patch.object(das, "_call_gemini_disease_api", return_value=None):
            result = das.get_disease_advisory(
                crop_name="Tomato",
                disease_name="Early Blight",
                confidence=0.9,
                language="hinglish",
            )
        assert result["source"] == "fallback"


# ---------------------------------------------------------------------------
# CNN failure
# ---------------------------------------------------------------------------

class TestCNNFailure:
    def test_predict_disease_when_model_missing(self):
        unload_disease_model()
        # Temporarily point to a missing path
        orig_path = disease_engine.MODEL_PATH
        disease_engine.MODEL_PATH = "/nonexistent/model.keras"
        try:
            with pytest.raises(FileNotFoundError):
                predict_disease(preprocess_leaf_image(_make_image_file()))
        finally:
            disease_engine.MODEL_PATH = orig_path
            load_disease_model()


# ---------------------------------------------------------------------------
# Route integration
# ---------------------------------------------------------------------------

class TestDiseaseRoutes:
    def test_disease_detection_page(self, client):
        r = client.get("/disease-detection")
        assert r.status_code == 200

    def test_api_diagnose_valid_image(self, client):
        data = {
            "leaf_image": (io.BytesIO(_make_image_file().read()), "leaf.png"),
            "language": "en",
        }
        r = client.post(
            "/api/disease-detection/diagnose",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["success"] is True
        assert "prediction" in body
        pred = body["prediction"]
        names = load_class_names()
        assert pred["predicted_class"] in names
        assert "advisory" in body
        # Advisory present (fallback when no API key)
        assert body["advisory"] is not None

    def test_api_diagnose_no_file(self, client):
        r = client.post(
            "/api/disease-detection/diagnose",
            data={"language": "en"},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        body = r.get_json()
        assert body["success"] is False

    def test_api_diagnose_invalid_file_type(self, client):
        r = client.post(
            "/api/disease-detection/diagnose",
            data={"leaf_image": (io.BytesIO(b"abc"), "document.exe"), "language": "en"},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        body = r.get_json()
        assert body["success"] is False

    def test_api_classes_endpoint(self, client):
        r = client.get("/api/disease-detection/classes")
        assert r.status_code == 200
        body = r.get_json()
        assert body["success"] is True
        assert len(body["classes"]) == 38


# ---------------------------------------------------------------------------
# Unaffected modules sanity (routes still load)
# ---------------------------------------------------------------------------

class TestUnaffectedModules:
    def test_home_dashboard_login_routes(self, client):
        assert client.get("/").status_code in (200, 302)
        assert client.get("/dashboard").status_code == 200
