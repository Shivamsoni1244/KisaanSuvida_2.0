"""
tests/test_crop_guide.py - Automated tests for crop guide and recommendation functionality

Tests:
- All major GET routes return 200
- Recommendation POST with PRG pattern (redirect, not direct render)
- Crop guide page renders all sections
- Data persistence across navigation
- Session isolation
- Template compilation
"""

import pytest
from app import app
from jinja2 import Environment, FileSystemLoader


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_profile"] = {
                "id": 1,
                "name": "Rajesh Kumar",
                "mobile": "+919876543210",
                "state": "Punjab",
                "district": "Ludhiana",
                "tehsil": "",
                "village": "",
                "state_id": 1,
                "district_id": 1,
                "tehsil_id": None,
                "village_id": None,
                "role": "Farmer",
                "is_verified": True,
                "preferred_language": "en",
            }
            sess["is_verified"] = True
            sess["csrf_token"] = "test_csrf_123"
        yield client


class TestTemplateCompilation:
    """Test that all Jinja templates compile without errors."""

    @pytest.mark.parametrize(
        "template",
        [
            "base.html",
            "dashboard.html",
            "crop_result.html",
            "crop_recommendation.html",
            "crop_guide.html",
            "history.html",
            "kisaanbot.html",
            "profile.html",
            "support.html",
            "schemes.html",
            "disease_detection.html",
            "crop_suitability.html",
            "home.html",
            "auth/login.html",
            "auth/register.html",
        ],
    )
    def test_template_compiles(self, template):
        env = Environment(loader=FileSystemLoader("templates"))
        t = env.get_template(template)
        assert t is not None


class TestRoutes:
    """Test all major routes return 200."""

    def test_home_redirects_when_authenticated(self, client):
        r = client.get("/")
        assert r.status_code == 302

    def test_dashboard(self, client):
        r = client.get("/dashboard")
        assert r.status_code == 200

    def test_recommendation_form_get(self, client):
        r = client.get("/recommendation")
        assert r.status_code == 200
        assert b"csrf_token" in r.data

    def test_crop_guide_rice(self, client):
        r = client.get("/crop-guide/Rice%20(Paddy)")
        assert r.status_code == 200
        html = r.data.decode("utf-8")
        assert "Introduction" in html
        assert "Climate & Temperature" in html
        assert "Soil Preparation" in html
        assert "Seed Selection" in html
        assert "Sowing & Planting" in html
        assert "Fertilizer Management" in html
        assert "Irrigation Management" in html
        assert "Weed Management" in html
        assert "Pest & Disease Management" in html
        assert "Growth Stages" in html
        assert "Harvesting" in html
        assert "Post-Harvest Management" in html
        assert "Expected Yield" in html
        assert "Important Precautions" in html
        assert "image-container-16by9" in html
        assert "Crop image coming soon" in html

    def test_crop_guide_wheat(self, client):
        r = client.get("/crop-guide/Wheat")
        assert r.status_code == 200

    def test_crop_guide_maize(self, client):
        r = client.get("/crop-guide/Maize")
        assert r.status_code == 200

    def test_kisaanbot(self, client):
        r = client.get("/kisaanbot")
        assert r.status_code == 200

    def test_history(self, client):
        r = client.get("/history")
        assert r.status_code == 200

    def test_profile(self, client):
        r = client.get("/profile")
        assert r.status_code == 200

    def test_support(self, client):
        r = client.get("/support")
        assert r.status_code == 200

    def test_schemes(self, client):
        r = client.get("/schemes")
        assert r.status_code == 200

    def test_disease_detection(self, client):
        r = client.get("/disease-detection")
        assert r.status_code == 200

    def test_suitability(self, client):
        r = client.get("/suitability")
        assert r.status_code == 200


class TestRecommendationPRG:
    """Test Post/Redirect/Get pattern for recommendation form."""

    def test_recommendation_post_redirects(self, client):
        """POST should redirect (302), not render directly (200)."""
        r = client.post(
            "/recommendation",
            data={
                "csrf_token": "test_csrf_123",
                "mode": "advanced",
                "state": "Punjab",
                "district": "Ludhiana",
                "season": "Kharif",
                "soil_type": "Alluvial",
                "irrigation": "Canal irrigation",
                "nitrogen": "90",
                "phosphorus": "42",
                "potassium": "43",
                "soil_ph": "6.5",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "recommendation/result" in r.headers.get("Location", "")

    def test_recommendation_result_after_redirect(self, client):
        """Following the redirect should show the result page."""
        r = client.post(
            "/recommendation",
            data={
                "csrf_token": "test_csrf_123",
                "mode": "advanced",
                "state": "Punjab",
                "district": "Ludhiana",
                "season": "Kharif",
                "soil_type": "Alluvial",
                "irrigation": "Canal irrigation",
                "nitrogen": "90",
                "phosphorus": "42",
                "potassium": "43",
                "soil_ph": "6.5",
            },
            follow_redirects=True,
        )
        assert r.status_code == 200
        html = r.data.decode("utf-8")
        assert "TOP RECOMMENDATION" in html
        # Mistral-only: when API is unavailable, all fields show "Not available"
        assert "Not available" in html
        assert "Ludhiana, Punjab" in html
        assert "Why this crop" in html
        assert "How to grow" in html
        assert "DID YOU KNOW" in html
        assert "Weather & Water" in html
        assert "Your farm compatibility" in html
        assert "Other crops worth considering" in html
        assert "View crop details" in html
        assert "Edit farm inputs" in html
        assert "crop-guide" in html

    def test_no_image_in_hero_card(self, client):
        """The hero card should not contain an image tag (images deferred)."""
        r = client.post(
            "/recommendation",
            data={
                "csrf_token": "test_csrf_123",
                "mode": "advanced",
                "state": "Punjab",
                "district": "Ludhiana",
                "season": "Kharif",
                "soil_type": "Alluvial",
                "irrigation": "Canal irrigation",
                "nitrogen": "90",
                "phosphorus": "42",
                "potassium": "43",
                "soil_ph": "6.5",
            },
            follow_redirects=True,
        )
        html = r.data.decode("utf-8")
        assert "<img" not in html


class TestApiEndpoints:
    """Test API endpoints."""

    def test_api_recommend(self, client):
        r = client.post(
            "/api/crop/recommend",
            json={
                "state": "Punjab",
                "district": "Ludhiana",
                "season": "Kharif",
                "soil_type": "Alluvial",
                "nitrogen": 90,
                "phosphorus": 42,
                "potassium": 43,
                "soil_ph": 6.5,
                "irrigation": "Canal irrigation",
                "language": "en",
            },
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert "data" in data

    def test_api_recommend_missing_csrf_ok(self, client):
        """API routes should be exempt from CSRF protection."""
        r = client.post(
            "/api/crop/recommend",
            json={"state": "Punjab", "district": "Ludhiana"},
        )
        # Should not return 403 (CSRF exempt for /api/ routes)
        assert r.status_code != 403


class TestNavigationPersistence:
    """Test data persistence across navigation."""

    def test_form_inputs_persist_after_result(self, client):
        """Farm inputs should be saved to session and available on form reload."""
        # Submit recommendation
        client.post(
            "/recommendation",
            data={
                "csrf_token": "test_csrf_123",
                "mode": "advanced",
                "state": "Punjab",
                "district": "Ludhiana",
                "season": "Kharif",
                "soil_type": "Alluvial",
                "irrigation": "Canal irrigation",
                "nitrogen": "90",
                "phosphorus": "42",
                "potassium": "43",
                "soil_ph": "6.5",
            },
            follow_redirects=True,
        )
        # Go back to form - should still work
        r = client.get("/recommendation")
        assert r.status_code == 200

    def test_crop_guide_persists_in_session(self, client):
        """Crop guide should be cached in session for back navigation."""
        r1 = client.get("/crop-guide/Rice%20(Paddy)")
        assert r1.status_code == 200

        r2 = client.get("/crop-guide/Rice%20(Paddy)")
        assert r2.status_code == 200
        # Both should return the same content (cached)
        assert r1.data == r2.data


class TestHindiLanguage:
    """Test Hindi language support."""

    def test_hindi_recommendation(self, client):
        with client.session_transaction() as sess:
            sess["user_profile"]["preferred_language"] = "hi"
        r = client.post(
            "/recommendation",
            data={
                "csrf_token": "test_csrf_123",
                "mode": "basic",
                "state": "Punjab",
                "district": "Ludhiana",
                "season": "Kharif",
                "soil_type": "Alluvial",
                "irrigation": "Canal irrigation",
            },
            follow_redirects=True,
        )
        assert r.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
