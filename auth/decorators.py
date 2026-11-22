"""
auth/decorators.py - Authentication and authorization decorators
"""

from functools import wraps
from flask import session, redirect, url_for, request, jsonify, flash, current_app


def login_required(view_func):
    """
    Decorator: requires an authenticated user.
    If not authenticated, redirects to login (for HTML) or returns 401 (for API/JSON).
    """
    @wraps(view_func)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            # Detect if the request expects JSON (API call)
            accept_header = request.headers.get("Accept", "")
            is_json_request = (
                request.is_json
                or "application/json" in accept_header
                or request.path.startswith("/api/")
                or request.path.startswith("/crop-suitability/api/")
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            )
            if is_json_request:
                return jsonify({"success": False, "error": "authentication_required", "message": "Please log in to access this resource."}), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view_func(*args, **kwargs)
    return decorated


def guest_required(view_func):
    """
    Decorator: requires the user to NOT be authenticated.
    If already authenticated, redirects to dashboard.
    Useful for login, register, forgot-password pages.
    """
    @wraps(view_func)
    def decorated(*args, **kwargs):
        if session.get("user_id"):
            return redirect(url_for("main.dashboard"))
        return view_func(*args, **kwargs)
    return decorated


def verified_required(view_func):
    """
    Decorator: requires an authenticated AND verified user.
    If authenticated but not verified, redirects to login with a message.
    """
    @wraps(view_func)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            accept_header = request.headers.get("Accept", "")
            is_json_request = (
                request.is_json
                or "application/json" in accept_header
                or request.path.startswith("/api/")
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            )
            if is_json_request:
                return jsonify({"success": False, "error": "authentication_required", "message": "Please log in to access this resource."}), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        if not session.get("is_verified"):
            flash("Your account is not verified. Please complete mobile verification.", "error")
            if session.get("pending_mobile"):
                return redirect(url_for("auth.verify_otp"))
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)
    return decorated


def get_current_user_id() -> int | None:
    """Return the authenticated user's ID from the session, or None."""
    return session.get("user_id")


def get_current_user() -> dict | None:
    """Return the authenticated user's profile dict from the session, or None."""
    return session.get("user_profile")
