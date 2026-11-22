"""
routes/schemes_routes.py - Government agricultural support programmes
"""

from flask import Blueprint, render_template, request, jsonify, session
from data.store import GOVERNMENT_SCHEMES

schemes_bp = Blueprint("schemes", __name__)


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


@schemes_bp.route("/schemes")
def schemes_page():
    user = get_current_user() or {}
    category = request.args.get("cat", "all")
    
    if category != "all":
        filtered_schemes = [s for s in GOVERNMENT_SCHEMES if s["category"] == category]
    else:
        filtered_schemes = GOVERNMENT_SCHEMES
        
    return render_template(
        "schemes.html",
        user=user,
        schemes=filtered_schemes,
        selected_category=category,
        active_page="schemes"
    )


@schemes_bp.route("/api/schemes")
def api_schemes():
    category = request.args.get("category", "all")
    if category != "all":
        data = [s for s in GOVERNMENT_SCHEMES if s["category"] == category]
    else:
        data = GOVERNMENT_SCHEMES
    return jsonify({"success": True, "schemes": data})
