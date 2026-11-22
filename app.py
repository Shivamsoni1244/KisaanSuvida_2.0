"""
app.py - Main Flask Application Entry Point for Kisaan Suvidha 2.0
"""
from dotenv import load_dotenv
import os

# Load .env from the project root (next to app.py), overriding existing env vars
_load_dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_load_dotenv_path, override=True)

import secrets
from datetime import datetime

import pytz
from flask import Flask, session, redirect, url_for, render_template, request, jsonify

# Import blueprints
from routes.auth_routes import auth_bp
from routes.main_routes import main_bp
from routes.crop_routes import crop_bp
from routes.disease_routes import disease_bp
from routes.bot_routes import bot_bp
from routes.history_routes import history_bp
from routes.schemes_routes import schemes_bp
from routes.support_routes import support_bp
from routes.location_routes import location_bp
from routes.crop_suitability_routes import crop_suitability_bp


def _generate_csrf_token():
    """Generate (or reuse) a CSRF token stored in the session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def create_app():
    app = Flask(__name__)

    # Secret key for session signing
    app.secret_key = os.environ.get("SECRET_KEY", "kisaan_suvidha_secret_key_2025")

    # Session security configuration
    app.config["SESSION_PERMANENT"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7  # 7 days
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV", "development") != "development"
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "kisaan_session"

    # Configure upload limits
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(crop_bp)
    app.register_blueprint(disease_bp)
    app.register_blueprint(bot_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(schemes_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(location_bp)
    app.register_blueprint(crop_suitability_bp)

    IST = pytz.timezone("Asia/Kolkata")

    def _get_current_datetime_info() -> dict:
        """Return current Indian date, time, and greeting for template injection."""
        now = datetime.now(IST)
        hour = now.hour
        if 5 <= hour < 12:
            greeting = "Good Morning"
        elif 12 <= hour < 17:
            greeting = "Good Afternoon"
        elif 17 <= hour < 21:
            greeting = "Good Evening"
        else:
            greeting = "Good Night"
        return {
            "current_date": now.strftime("%d %b %Y"),
            "current_day": now.strftime("%A"),
            "current_time": now.strftime("%I:%M %p"),
            "current_greeting": greeting,
        }

    def _crop_image_url(crop_name: str) -> str:
        """Return the URL for a crop photograph, falling back to a sage placeholder."""
        mapping = {
            "Rice (Paddy)": "https://images.unsplash.com/photo-1613766777789-bd72b878030f?w=1200&q=80",
            "Wheat": "https://images.unsplash.com/photo-1515935790605-3226e0574ee2?w=1200&q=80",
            "Maize": "https://images.unsplash.com/photo-1563960674193-871d3e40a050?w=1200&q=80",
            "Cotton": "https://images.unsplash.com/photo-1625553477273-012a6c8a5e8e?w=1200&q=80",
            "Sugarcane": "https://images.unsplash.com/photo-1518636395263-2b73c77c1391?w=1200&q=80",
            "Gram (Chickpea)": "https://images.unsplash.com/photo-1592020848139-90137903337a?w=1200&q=80",
            "Potato": "https://images.unsplash.com/photo-1519835600718-25297b2575e5?w=1200&q=80",
            "Pearl millet": "https://images.unsplash.com/photo-1600891288140-57227e78ea1d?w=1200&q=80",
        }
        return mapping.get(crop_name, mapping["Rice (Paddy)"])

    @app.context_processor
    def inject_global_data():
        """Inject current user and CSRF token into templates."""
        user_profile = session.get("user_profile")
        is_authenticated = session.get("user_id") is not None
        datetime_info = _get_current_datetime_info()
        return {
            "current_user": user_profile,
            "is_authenticated": is_authenticated,
            "app_year": "2025",
            "csrf_token": _generate_csrf_token,
            "crop_image_url": _crop_image_url,
            **datetime_info,
        }

    @app.before_request
    def csrf_protect():
        """Require a valid CSRF token for HTML form submissions that change state.

        JSON API routes (/api/*) and AJAX JSON calls are exempt; they rely on
        session-based authentication and per-endpoint rate limiting instead.
        """
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            # Exempt JSON API routes and AJAX JSON endpoints
            if (
                request.path.startswith("/api/")
                or request.is_json
                or request.headers.get("Content-Type", "").startswith("application/json")
            ):
                return None
            token = session.get("csrf_token")
            request_token = request.form.get("csrf_token")
            if not token or not request_token or not secrets.compare_digest(token, request_token):
                return render_template("auth/login.html"), 403

    @app.route("/")
    def index():
        """Home page - accessible to guests and authenticated users."""
        if session.get("user_id"):
            return redirect(url_for("main.dashboard"))
        return render_template("home.html")

    @app.route("/suitability")
    def redirect_suitability():
        """Redirect old /suitability route to new crop-suitability module."""
        return redirect(url_for("crop_suitability.suitability_analysis"))

    return app


app = create_app()

if __name__ == "__main__":
    # Standard development server on port 5000
    app.run(host="127.0.0.1", port=5000, debug=True)