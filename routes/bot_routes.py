"""
routes/bot_routes.py - KisaanBot conversational AI assistant endpoints.
Protected: requires authentication for page access and chat API.

The chatbot uses:
- ChromaDB for application knowledge (RAG)
- MySQL for authenticated farmer's personal history
- Flask session for conversation memory
- Groq LLM for response generation

No hardcoded crop names — all crop names come from actual farmer records.
"""

from flask import Blueprint, render_template, request, jsonify, session

from services.kisaanbot_engine import (
    process_kisaanbot_query,
    get_initial_suggestions_for_user,
)

from auth.decorators import login_required, get_current_user_id

bot_bp = Blueprint("bot", __name__)


@bot_bp.route("/kisaanbot")
@login_required
def kisaanbot_page():
    """Dedicated KisaanBot page."""
    user_profile = session.get("user_profile", {})
    language = user_profile.get("preferred_language", "en")
    user_id = session.get("user_id")

    initial_suggestions = get_initial_suggestions_for_user(
        language=language,
        user_id=user_id,
    )

    return render_template(
        "kisaanbot.html",
        user=user_profile,
        initial_suggestions=initial_suggestions,
        active_page="kisaanbot",
    )


@bot_bp.route("/api/kisaanbot/chat", methods=["POST", "OPTIONS"])
@login_required
def api_chat():
    """
    Unified JSON chat API used by:
    1. Dedicated /kisaanbot page
    2. Floating in-app assistant widget
    3. External embeddable websites via kisaanbot-widget.js
    """
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response

    data = request.get_json(silent=True) or request.form or {}
    message = data.get("message", "").strip()
    language = data.get("language", "en")

    user_id = get_current_user_id()
    user_profile = session.get("user_profile", {})

    result = process_kisaanbot_query(
        query=message,
        language=language,
        user_id=user_id,
        session_obj=session,
    )

    response = jsonify({
        "success": True,
        "reply": result["reply"],
        "language": result["language"],
        "intent": result["intent"],
        "suggestions": result["suggestions"],
    })

    # Enable CORS for embeddable external widgets
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
