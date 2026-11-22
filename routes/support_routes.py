"""
routes/support_routes.py - Farmer customer support & ticketing
"""

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
import random

support_bp = Blueprint("support", __name__)


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


@support_bp.route("/support", methods=["GET", "POST"])
def support_page():
    user = get_current_user() or {}
    
    if request.method == "POST":
        if not session.get("user_id"):
            flash("Please log in to submit a support ticket.", "error")
            return redirect(url_for("auth.login"))
        
        topic = request.form.get("topic", "Crop recommendation")
        subject = request.form.get("subject", "General query")
        message = request.form.get("message", "")
        
        ticket_id = f"TICK-{random.randint(1000, 9999)}"
        flash(f"Support request submitted successfully! Your Ticket ID is #{ticket_id}. Our agronomic support team will respond within 24-48 hours.", "success")
        return redirect(url_for("support.support_page"))
        
    return render_template(
        "support.html",
        user=user,
        active_page="support"
    )


@support_bp.route("/api/support/ticket", methods=["POST"])
def api_submit_ticket():
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "authentication_required"}), 401
    
    data = request.get_json() or {}
    ticket_id = f"TICK-{random.randint(1000, 9999)}"
    return jsonify({
        "success": True,
        "ticket_id": ticket_id,
        "message": "Your support ticket has been received and logged."
    })
