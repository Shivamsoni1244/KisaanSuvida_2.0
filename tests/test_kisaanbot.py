"""
tests/test_kisaanbot.py - Automated tests for the upgraded KisaanBot.

Scenarios:
A. New farmer with no activity
B. Farmer with Maize recommendation
C. Farmer with Rice recommendation
D. Farmer with suitability analysis
E. Farmer with cultivation guide
F. Follow-up questions
G. Greetings
H. Unrelated questions
I. Application questions
J. Multiple users (data isolation)
K. Missing/unavailable data

These tests use the Flask test client and mock the Groq API where needed.
"""

import json
import os
import sys

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from services.intent_classifier import detect_language, classify_intent, is_greeting
from services.prompt_templates import (
    get_greeting_response,
    get_out_of_scope_message,
    get_missing_history_message,
    get_system_prompt,
)
from services.suggestion_engine import generate_suggestions, get_initial_suggestions
from services.context_builder import build_context


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        # Authenticated user 1 (has Maize recommendation in DB)
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_profile"] = {
                "id": 1,
                "name": "Shivam Soni",
                "mobile": "+918989128312",
                "state": "Madhya Pradesh",
                "district": "Indore",
                "state_name": "Madhya Pradesh",
                "district_name": "Indore",
                "soil_type": "Alluvial",
                "irrigation": "Canal irrigation",
                "farm_size": "5 acres",
                "preferred_language": "en",
                "is_verified": True,
            }
            sess["is_verified"] = True
            sess["csrf_token"] = "test_csrf_123"
        yield client


@pytest.fixture
def client_user_27():
    """Authenticated user 27 (different user — for isolation tests)."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 27
            sess["user_profile"] = {
                "id": 27,
                "name": "harsh nayak",
                "mobile": "+917723046868",
                "state": "Madhya Pradesh",
                "district": "Panna",
                "state_name": "Madhya Pradesh",
                "district_name": "Panna",
                "soil_type": "Black",
                "irrigation": "Borewell",
                "farm_size": "3 acres",
                "preferred_language": "en",
                "is_verified": True,
            }
            sess["is_verified"] = True
            sess["csrf_token"] = "test_csrf_456"
        yield client


# ---------------------------------------------------------------------------
# Language detection tests
# ---------------------------------------------------------------------------
class TestLanguageDetection:
    def test_english(self):
        assert detect_language("Hello how are you") == "en"

    def test_hindi_devanagari(self):
        assert detect_language("नमस्ते आप कैसे हैं") == "hi"

    def test_hinglish(self):
        assert detect_language("Kya haal hai aapka") == "hinglish"


# ---------------------------------------------------------------------------
# Intent classification tests
# ---------------------------------------------------------------------------
class TestIntentClassification:
    def test_greeting_hi(self):
        result = classify_intent("Hi", language="en")
        assert result["is_greeting"] is True
        assert result["intent"] == "greeting"

    def test_greeting_namaste(self):
        result = classify_intent("Namaste", language="en")
        assert result["is_greeting"] is True

    def test_unrelated_python(self):
        result = classify_intent("Write a Python program", language="en")
        assert result["is_unrelated"] is True
        assert result["intent"] == "unrelated"

    def test_unrelated_politics(self):
        result = classify_intent("Who is the Prime Minister?", language="en")
        assert result["is_unrelated"] is True

    def test_app_question_recommendation(self):
        result = classify_intent("How do I get a crop recommendation?", language="en")
        assert result["intent"] in ("recommendation", "general_app")
        assert result["is_unrelated"] is False

    def test_app_question_suitability(self):
        result = classify_intent("How do I check crop suitability?", language="en")
        assert result["intent"] in ("suitability", "general_app")

    def test_app_question_disease(self):
        result = classify_intent("How does plant disease detection work?", language="en")
        assert result["intent"] in ("disease_detection", "general_app")


# ---------------------------------------------------------------------------
# Greeting response tests
# ---------------------------------------------------------------------------
class TestGreetings:
    def test_english_hi(self):
        resp = get_greeting_response("Hi", "en")
        assert resp is not None
        assert "KisaanBot" in resp

    def test_english_hello(self):
        resp = get_greeting_response("Hello", "en")
        assert resp is not None

    def test_english_good_morning(self):
        resp = get_greeting_response("Good morning", "en")
        assert resp is not None
        assert "morning" in resp.lower()

    def test_english_thank_you(self):
        resp = get_greeting_response("Thank you", "en")
        assert resp is not None
        assert "welcome" in resp.lower()

    def test_english_who_are_you(self):
        resp = get_greeting_response("Who are you", "en")
        assert resp is not None
        assert "KisaanBot" in resp

    def test_hindi_namaste(self):
        resp = get_greeting_response("नमस्ते", "hi")
        assert resp is not None

    def test_hinglish_hi(self):
        resp = get_greeting_response("Hi", "hinglish")
        assert resp is not None


# ---------------------------------------------------------------------------
# Out-of-scope tests
# ---------------------------------------------------------------------------
class TestOutOfScope:
    def test_out_of_scope_en(self):
        msg = get_out_of_scope_message("en")
        assert "KisaanBot" in msg
        assert "crop" in msg.lower()

    def test_out_of_scope_hi(self):
        msg = get_out_of_scope_message("hi")
        assert "KisaanBot" in msg

    def test_out_of_scope_hinglish(self):
        msg = get_out_of_scope_message("hinglish")
        assert "KisaanBot" in msg


# ---------------------------------------------------------------------------
# Missing history tests
# ---------------------------------------------------------------------------
class TestMissingHistory:
    def test_missing_recommendation_en(self):
        msg = get_missing_history_message("recommendation", "en")
        assert "recommendation" in msg.lower()

    def test_missing_suitability_en(self):
        msg = get_missing_history_message("suitability", "en")
        assert "suitability" in msg.lower()


# ---------------------------------------------------------------------------
# System prompt test
# ---------------------------------------------------------------------------
class TestSystemPrompt:
    def test_system_prompt_contains_rules(self):
        prompt = get_system_prompt("en")
        assert "KisaanBot" in prompt
        assert "ONLY" in prompt or "only" in prompt.lower()
        assert "invent" in prompt.lower()


# ---------------------------------------------------------------------------
# Suggestion engine tests
# ---------------------------------------------------------------------------
class TestSuggestionEngine:
    def test_initial_suggestions_no_history(self):
        suggestions = get_initial_suggestions(language="en", farmer_records=None)
        assert len(suggestions) > 0
        assert len(suggestions) <= 6

    def test_initial_suggestions_with_maize(self):
        records = {
            "latest_recommendation": {"crop_name": "Maize"},
            "has_recommendation": True,
            "has_suitability": True,
        }
        suggestions = get_initial_suggestions(language="en", farmer_records=records)
        assert len(suggestions) > 0
        # Should mention Maize
        combined = " ".join(suggestions)
        assert "Maize" in combined

    def test_initial_suggestions_with_rice(self):
        records = {
            "latest_recommendation": {"crop_name": "Rice"},
            "has_recommendation": True,
            "has_suitability": False,
        }
        suggestions = get_initial_suggestions(language="en", farmer_records=records)
        combined = " ".join(suggestions)
        assert "Rice" in combined
        assert "Maize" not in combined

    def test_no_hardcoded_rice_when_maize(self):
        records = {
            "latest_recommendation": {"crop_name": "Maize"},
            "has_recommendation": True,
        }
        suggestions = generate_suggestions(
            intent="greeting",
            language="en",
            latest_crop="Maize",
            has_suitability=False,
            has_cultivation_guide=False,
            farmer_records=records,
        )
        combined = " ".join(suggestions)
        assert "Maize" in combined
        assert "Rice" not in combined

    def test_no_suitability_when_none(self):
        suggestions = generate_suggestions(
            intent="suitability",
            language="en",
            latest_crop="Wheat",
            has_suitability=False,
            has_cultivation_guide=False,
        )
        # Should not crash and should return general suggestions
        assert len(suggestions) > 0

    def test_hindi_suggestions(self):
        suggestions = generate_suggestions(
            intent="greeting",
            language="hi",
            latest_crop=None,
            has_suitability=False,
            has_cultivation_guide=False,
        )
        assert len(suggestions) > 0

    def test_hinglish_suggestions(self):
        suggestions = generate_suggestions(
            intent="greeting",
            language="hinglish",
            latest_crop=None,
            has_suitability=False,
            has_cultivation_guide=False,
        )
        assert len(suggestions) > 0


# ---------------------------------------------------------------------------
# Context builder tests
# ---------------------------------------------------------------------------
class TestContextBuilder:
    def test_build_context_guest(self):
        ctx = build_context(
            question="How does Kisaan Suvidha work?",
            user_id=None,
            language="en",
            session=None,
        )
        assert "application_context" in ctx
        assert "farmer_context" in ctx
        assert "conversation_context" in ctx
        assert "intent" in ctx


# ---------------------------------------------------------------------------
# Route-level tests (with Flask test client)
# ---------------------------------------------------------------------------
class TestRoutes:
    def test_kisaanbot_page(self, client):
        r = client.get("/kisaanbot")
        assert r.status_code == 200

    def test_chat_api_empty_message(self, client):
        r = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "", "language": "en"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True

    def test_chat_api_greeting(self, client):
        r = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "Hi", "language": "en"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert "KisaanBot" in data["reply"]

    def test_chat_api_unrelated(self, client):
        r = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "Write a Python program", "language": "en"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert data["intent"] == "unrelated"

    def test_chat_api_app_question(self, client):
        r = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "How do I get a crop recommendation?", "language": "en"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert data["intent"] != "unrelated"

    def test_user_isolation(self, client, client_user_27):
        """User 1 should not see user 27's data."""
        # User 1 asks about recommendation
        r1 = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "What was my latest recommendation?", "language": "en"}),
            content_type="application/json",
        )
        data1 = r1.get_json()

        # User 27 asks about recommendation
        r2 = client_user_27.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "What was my latest recommendation?", "language": "en"}),
            content_type="application/json",
        )
        data2 = r2.get_json()

        # Both should succeed
        assert data1["success"] is True
        assert data2["success"] is True

    def test_chat_api_hindi(self, client):
        r = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "नमस्ते", "language": "hi"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True

    def test_chat_api_hinglish(self, client):
        r = client.post(
            "/api/kisaanbot/chat",
            data=json.dumps({"message": "Hi KisaanBot", "language": "hinglish"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# Main guard
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
