"""
routes/bot_routes.py - KisaanBot conversational AI assistant endpoints
Protected: requires authentication for page access and chat API.
"""

from flask import Blueprint, render_template, request, jsonify, session
from services.kisaanbot_engine import process_kisaanbot_query, get_suggestions

from auth.decorators import login_required, verified_required, get_current_user

bot_bp = Blueprint("bot", __name__)


@bot_bp.route("/kisaanbot")
@login_required
def kisaanbot_page():
    user_profile = session.get("user_profile", {})
    initial_suggestions = get_suggestions("why_rice", "en")

    return render_template(
        "kisaanbot.html",
        user=user_profile,
        initial_suggestions=initial_suggestions,
        active_page="kisaanbot"
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

    user_profile = session.get("user_profile", {})
    farm_context = {
        "farmer_name": user_profile.get("name", "Farmer"),
        "state": user_profile.get("state", ""),
        "district": user_profile.get("district", ""),
        "soil_type": user_profile.get("soil_type", ""),
        "ph": 6.5,
        "farm_size": f"{user_profile.get('farm_size', '4.5')} acres",
        "irrigation": user_profile.get("irrigation", ""),
        "current_crop": "Rice (Paddy)",
        "season": "Kharif"
    }

    if not message:
        result = process_kisaanbot_query("help", language=language, farm_context=farm_context)
    else:
        result = process_kisaanbot_query(message, language=language, farm_context=farm_context)

    response = jsonify({
        "success": True,
        "reply": result["reply"],
        "language": result["language"],
        "intent": result["intent"],
        "suggestions": result["suggestions"],
        "context": farm_context
    })

    # Enable CORS for embeddable external widgets
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
