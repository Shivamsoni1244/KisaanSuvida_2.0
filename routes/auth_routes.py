"""
routes/auth_routes.py - Authentication endpoints
Real implementation: MySQL-backed users, Werkzeug password hashing, Twilio OTP,
secure session management, registration/login/password-reset flows.

Login is password-only (mobile + password). OTP is used ONLY for signup and
forgot-password verification.
"""

import os
import re
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, jsonify, flash, current_app
)
from werkzeug.security import check_password_hash

from auth.services import (
    send_otp, verify_otp_from_db, get_user_by_mobile, create_user,
    update_user_password, get_user_by_id, hash_password, verify_password,
    DEV_MODE, OTP_DEBUG, _record_attempt, _is_rate_limited, _clean_expired_otps,
)
from auth.decorators import guest_required, login_required
from data.db import get_db
from mysql.connector import Error

auth_bp = Blueprint("auth", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Indian mobile: optional +91 prefix, then 10 digits starting with 6-9.
MOBILE_REGEX = re.compile(r"^(\+91)?[6-9]\d{9}$")


def _normalize_mobile(mobile: str) -> str:
    """Normalize mobile number to +91XXXXXXXXXX format."""
    mobile = mobile.strip().replace(" ", "").replace("-", "")
    if not mobile.startswith("+"):
        if mobile.startswith("91") and len(mobile) == 12:
            mobile = "+" + mobile
        elif mobile.startswith("0") and len(mobile) == 11:
            mobile = "+91" + mobile[1:]
        elif len(mobile) == 10:
            mobile = "+91" + mobile
    return mobile


def _validate_mobile(mobile: str) -> bool:
    if not mobile:
        return False
    normalized = _normalize_mobile(mobile)
    return bool(MOBILE_REGEX.match(normalized))


def _is_production() -> bool:
    return os.environ.get("FLASK_ENV", "development") != "development"


def _user_to_session(user: dict) -> None:
    """Populate Flask session with authenticated user data and regenerate ID."""
    # Clear any existing session data to prevent session fixation.
    session.clear()
    session["user_id"] = user["id"]
    session["user_profile"] = {
        "id": user["id"],
        "name": user["full_name"],
        "mobile": user["mobile"],
        "state": user.get("state_name") or "",
        "district": user.get("district_name") or "",
        "tehsil": user.get("tehsil_name") or "",
        "village": user.get("village_name") or "",
        "state_id": user.get("state_id"),
        "district_id": user.get("district_id"),
        "tehsil_id": user.get("tehsil_id"),
        "village_id": user.get("village_id"),
        "role": "Farmer",
        "is_verified": bool(user["is_verified"]),
    }
    session["is_verified"] = bool(user["is_verified"])
    session.permanent = True


def _clear_auth_session() -> None:
    """Clear all auth-related session data."""
    keys = [
        "user_id", "user_profile", "is_verified",
        "pending_mobile", "pending_purpose", "pending_registration",
        "reset_authorized", "reset_user_id",
        "otp_sent_at",
    ]
    for key in keys:
        session.pop(key, None)


# ---------------------------------------------------------------------------
# Login  (password only — no OTP)
# ---------------------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
@guest_required
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    mobile = _normalize_mobile(request.form.get("mobile", ""))
    password = request.form.get("password", "")

    # --- Input validation ---
    if not mobile:
        flash("Please enter your mobile number.", "error")
        return render_template("auth/login.html"), 400
    if not _validate_mobile(mobile):
        flash("Please enter a valid Indian mobile number.", "error")
        return render_template("auth/login.html"), 400
    if not password:
        flash("Please enter your password.", "error")
        return render_template("auth/login.html"), 400

    # Rate-limit repeated login attempts
    _record_attempt(mobile)
    if _is_rate_limited(mobile):
        flash("Too many login attempts. Please try again later.", "error")
        return render_template("auth/login.html"), 429

    user = get_user_by_mobile(mobile)

    if not user:
        # Account-enumeration safe: in production use a generic message.
        if _is_production():
            flash("Invalid mobile number or password.", "error")
        else:
            flash("No account found with this mobile number.", "error")
        return render_template(
            "auth/login.html",
            error_type="unregistered",
        ), 401

    if not verify_password(password, user["password_hash"]):
        if _is_production():
            flash("Invalid mobile number or password.", "error")
        else:
            flash("Incorrect password. Please try again.", "error")
        return render_template(
            "auth/login.html",
            error_type="wrong_password",
        ), 401

    if not user["is_verified"]:
        flash("Your account is not verified. Please complete mobile verification first.", "error")
        return render_template("auth/login.html"), 403

    # Successful login: establish session (fixation-safe) and redirect to dashboard.
    _user_to_session(user)
    flash("Welcome back!", "success")
    next_url = request.args.get("next") or url_for("main.dashboard")
    return redirect(next_url)


# ---------------------------------------------------------------------------
# Register  (OTP verification required)
# ---------------------------------------------------------------------------

@auth_bp.route("/register", methods=["GET", "POST"])
@guest_required
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    # Collect form data
    full_name = (request.form.get("full_name") or "").strip()
    mobile = _normalize_mobile(request.form.get("mobile", ""))
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    # Location IDs
    state_id = request.form.get("state_id", "").strip()
    district_id = request.form.get("district_id", "").strip()
    tehsil_id = request.form.get("tehsil_id", "").strip()
    village_id = request.form.get("village_id", "").strip()

    # Location names (hidden fields populated by JS)
    state_name = (request.form.get("state_name") or "").strip()
    district_name = (request.form.get("district_name") or "").strip()
    tehsil_name = (request.form.get("tehsil_name") or "").strip()
    village_name = (request.form.get("village_name") or "").strip()

    # --- Validation ---
    errors = []

    if not full_name or len(full_name) < 2:
        errors.append("Please enter your full name (at least 2 characters).")

    if not _validate_mobile(mobile):
        errors.append("Please enter a valid Indian mobile number.")

    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters long.")

    if password != confirm_password:
        errors.append("Password and confirm password do not match.")

    # Location validation: all four are required
    try:
        sid = int(state_id) if state_id else None
        did = int(district_id) if district_id else None
        tid = int(tehsil_id) if tehsil_id else None
        vid = int(village_id) if village_id else None
    except ValueError:
        sid = did = tid = vid = None

    if not all([sid, did, tid, vid]):
        errors.append("Please select State, District, Tehsil and Village.")

    if not all([state_name, district_name, tehsil_name, village_name]):
        errors.append("Please select all location fields.")

    # Check duplicate mobile
    if _validate_mobile(mobile):
        existing = get_user_by_mobile(mobile)
        if existing:
            errors.append("This mobile number is already registered. Please log in instead.")

    if errors:
        for err in errors:
            flash(err, "error")
        return render_template("auth/register.html"), 400

    # Rate-limit signup attempts
    _record_attempt(mobile)
    if _is_rate_limited(mobile):
        flash("Too many signup attempts. Please try again later.", "error")
        return render_template("auth/register.html"), 429

    # Temporarily store registration data in session (not in DB yet)
    session["pending_registration"] = {
        "full_name": full_name,
        "mobile": mobile,
        "password_hash": hash_password(password),
        "state_id": sid,
        "district_id": did,
        "tehsil_id": tid,
        "village_id": vid,
        "state_name": state_name,
        "district_name": district_name,
        "tehsil_name": tehsil_name,
        "village_name": village_name,
    }
    session["pending_mobile"] = mobile
    session["pending_purpose"] = "registration"

    # Send OTP
    success, message, dev_otp, meta = send_otp(mobile, purpose="registration")
    if not success:
        flash(message, "error")
        return render_template("auth/register.html"), 429 if "wait" in message.lower() else 500

    session["otp_sent_at"] = datetime.now(timezone.utc).isoformat()

    if DEV_MODE and OTP_DEBUG and dev_otp:
        flash(f"Development OTP: {dev_otp}", "info")

    flash(message, "info")
    return redirect(url_for("auth.verify_otp"))


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------

@auth_bp.route("/verify-otp", methods=["GET", "POST"])
@guest_required
def verify_otp():
    mobile = session.get("pending_mobile", "")
    purpose = session.get("pending_purpose", "registration")

    if not mobile:
        flash("No verification session found. Please start again.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        # Collect OTP digits from either named fields or single input
        digits = []
        for i in range(1, 7):
            digits.append(request.form.get(f"digit{i}", "") or "")
        otp = "".join(digits)

        # Also support single OTP field
        if not otp:
            otp = (request.form.get("otp") or "").strip()

        if not otp or len(otp) != 6 or not otp.isdigit():
            flash("Please enter a valid 6-digit OTP.", "error")
            return render_template("auth/verify_otp.html", mobile=mobile, purpose=purpose), 400

        success, message = verify_otp_from_db(mobile, otp, purpose)
        if not success:
            flash(message, "error")
            return render_template("auth/verify_otp.html", mobile=mobile, purpose=purpose), 400

        # OTP verified - act based on purpose
        if purpose == "registration":
            reg_data = session.get("pending_registration")
            if not reg_data:
                flash("Registration data expired. Please register again.", "error")
                return redirect(url_for("auth.register"))

            user_id = create_user(
                full_name=reg_data["full_name"],
                mobile=reg_data["mobile"],
                password_hash=reg_data["password_hash"],
                state_id=reg_data["state_id"],
                district_id=reg_data["district_id"],
                tehsil_id=reg_data["tehsil_id"],
                village_id=reg_data["village_id"],
                state_name=reg_data["state_name"],
                district_name=reg_data["district_name"],
                tehsil_name=reg_data["tehsil_name"],
                village_name=reg_data["village_name"],
            )
            if not user_id:
                flash("Failed to create account. Please try again.", "error")
                return redirect(url_for("auth.register"))

            # Clear pending registration
            session.pop("pending_registration", None)
            session.pop("pending_mobile", None)
            session.pop("pending_purpose", None)
            session.pop("otp_sent_at", None)

            # Log the user in directly
            user = get_user_by_id(user_id)
            if user:
                _user_to_session(user)
            flash("Account created successfully. Welcome to Kisaan Suvidha!", "success")
            return redirect(url_for("main.dashboard"))

        elif purpose == "password_reset":
            user = get_user_by_mobile(mobile)
            if not user:
                flash("User not found.", "error")
                return redirect(url_for("auth.login"))

            # Store reset authorization in session (short-lived)
            session["reset_authorized"] = True
            session["reset_user_id"] = user["id"]
            session.pop("pending_mobile", None)
            session.pop("pending_purpose", None)
            session.pop("otp_sent_at", None)
            flash("OTP verified. Please set your new password.", "success")
            return redirect(url_for("auth.reset_password"))

    # Render the verify page with backend-driven countdown data
    otp_sent_at = session.get("otp_sent_at")
    resend_in = 0
    if otp_sent_at:
        try:
            sent = datetime.fromisoformat(otp_sent_at)
            elapsed = (datetime.now(timezone.utc) - sent).total_seconds()
            resend_in = max(0, int(60 - elapsed))
        except Exception:
            resend_in = 0

    return render_template(
        "auth/verify_otp.html",
        mobile=mobile,
        purpose=purpose,
        resend_in=resend_in,
        expires_in=5 * 60,
    )


# ---------------------------------------------------------------------------
# Resend OTP
# ---------------------------------------------------------------------------

@auth_bp.route("/api/auth/resend-otp", methods=["POST"])
@guest_required
def resend_otp():
    mobile = session.get("pending_mobile", "")
    purpose = session.get("pending_purpose", "registration")

    if not mobile:
        return jsonify({"success": False, "error": "no_session", "message": "No verification session found."}), 400

    success, message, dev_otp, meta = send_otp(mobile, purpose=purpose)
    if not success:
        return jsonify({"success": False, "error": "send_failed", "message": message, "meta": meta}), 429

    session["otp_sent_at"] = datetime.now(timezone.utc).isoformat()

    response = {"success": True, "message": message, "meta": meta or {}}
    if DEV_MODE and OTP_DEBUG and dev_otp:
        response["dev_otp"] = dev_otp  # Only in development

    return jsonify(response)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth_bp.route("/logout")
@login_required
def logout():
    user_id = session.get("user_id")
    _clear_auth_session()
    # Invalidate any pending OTPs for this user's mobile if known
    if user_id:
        user = get_user_by_id(user_id)
        if user and user.get("mobile"):
            _clean_expired_otps(user["mobile"])
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@guest_required
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    mobile = _normalize_mobile(request.form.get("mobile", ""))

    if not _validate_mobile(mobile):
        flash("Please enter a valid mobile number.", "error")
        return render_template("auth/forgot_password.html"), 400

    user = get_user_by_mobile(mobile)
    if not user:
        # Don't reveal whether the mobile exists
        flash("If this mobile is registered, a verification code has been sent.", "info")
        return render_template("auth/forgot_password.html"), 200

    # Rate-limit password-reset requests
    _record_attempt(mobile)
    if _is_rate_limited(mobile):
        flash("Too many attempts. Please try again later.", "error")
        return render_template("auth/forgot_password.html"), 429

    # Send OTP for password reset
    success, message, dev_otp, meta = send_otp(mobile, purpose="password_reset")
    if not success:
        flash(message, "error")
        return render_template("auth/forgot_password.html"), 429 if "wait" in message.lower() else 500

    session["pending_mobile"] = mobile
    session["pending_purpose"] = "password_reset"
    session["otp_sent_at"] = datetime.now(timezone.utc).isoformat()

    if DEV_MODE and OTP_DEBUG and dev_otp:
        flash(f"Development OTP: {dev_otp}", "info")

    flash(message, "info")
    return redirect(url_for("auth.verify_otp"))


# ---------------------------------------------------------------------------
# Reset Password
# ---------------------------------------------------------------------------

@auth_bp.route("/reset-password", methods=["GET", "POST"])
@guest_required
def reset_password():
    if not session.get("reset_authorized") or not session.get("reset_user_id"):
        flash("No password reset session found. Please start again.", "error")
        return redirect(url_for("auth.forgot_password"))

    user_id = session["reset_user_id"]

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("auth/reset_password.html"), 400

        if password != confirm_password:
            flash("Password and confirm password do not match.", "error")
            return render_template("auth/reset_password.html"), 400

        if update_user_password(user_id, hash_password(password)):
            # Invalidate all existing sessions for this user by clearing ours
            session.pop("reset_authorized", None)
            session.pop("reset_user_id", None)
            session.pop("user_id", None)
            session.pop("user_profile", None)
            session.pop("is_verified", None)
            # Invalidate any remaining unconsumed OTPs for this user
            user = get_user_by_id(user_id)
            if user and user.get("mobile"):
                _clean_expired_otps(user["mobile"])
            flash("Your password has been reset successfully. You can now log in.", "success")
            return redirect(url_for("auth.login"))
        else:
            flash("Failed to reset password. Please try again.", "error")
            return render_template("auth/reset_password.html"), 500

    return render_template("auth/reset_password.html")
