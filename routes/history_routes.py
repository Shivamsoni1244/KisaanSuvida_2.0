"""
routes/history_routes.py - Historical recommendations, analyses, and diagnostics
"""

from flask import Blueprint, render_template, request, jsonify, session

history_bp = Blueprint("history", __name__)


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


@history_bp.route("/history")
def history_page():
    user = get_current_user() or {}
    
    # Guest or new user: empty history
    records = []
    recom_count = 0
    analysis_count = 0
    disease_count = 0
    
    return render_template(
        "history.html",
        user=user,
        records=records,
        recom_count=recom_count,
        analysis_count=analysis_count,
        disease_count=disease_count,
        active_page="history"
    )


@history_bp.route("/api/history")
def api_history():
    return jsonify({
        "success": True,
        "count": 0,
        "records": []
    })
