"""
auth/services.py - Authentication services: OTP, password hashing, Twilio SMS, rate limiting
"""

import os
import re
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from collections import defaultdict

from werkzeug.security import generate_password_hash, check_password_hash

from data.db import get_db
from mysql.connector import Error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

DEV_MODE = os.environ.get("FLASK_ENV", "development") == "development"
DEV_OTP_LOGGING = os.environ.get("DEV_OTP_LOGGING", "true").lower() == "true"
OTP_DEBUG = os.environ.get("OTP_DEBUG", "true" if DEV_MODE else "false").lower() == "true"

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60

# Rate limiting: max attempts per mobile per window
RATE_LIMIT_MAX_ATTEMPTS = 10
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes

# In-memory rate limit trackers (simple, suitable for single-process dev)
_attempt_tracker: Dict[str, list[float]] = defaultdict(list)
_resend_tracker: Dict[str, float] = {}


def _now() -> datetime:
    """Return the current local time.

    MySQL TIMESTAMP columns are returned by the connector in the server's local
    time zone.  Comparing them with datetime.utcnow() (UTC) produced a negative
    elapsed time on IST servers, which surfaced as bogus cooldown messages such
    as "Please wait 19369 seconds".  Use local time everywhere so the
    subtraction is consistent with the values stored in / read from MySQL.
    """
    return datetime.now()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plain-text password using Werkzeug (PBKDF2:sha256)."""
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plain-text password against a stored hash."""
    return check_password_hash(password_hash, password)


# ---------------------------------------------------------------------------
# OTP helpers
# ---------------------------------------------------------------------------

def _generate_otp() -> str:
    """Generate a six-digit numeric OTP."""
    import random
    return f"{random.randint(0, 999999):06d}"


def _hash_otp(otp: str) -> str:
    """Hash an OTP using HMAC-SHA256 with a server-side pepper."""
    pepper = os.environ.get("OTP_PEPPER", "kisaan_suvidha_otp_pepper_2025")
    return hmac.new(pepper.encode(), otp.encode(), hashlib.sha256).hexdigest()


def _verify_otp_hash(otp: str, otp_hash: str) -> bool:
    """Verify an OTP against its hash using constant-time comparison."""
    expected = _hash_otp(otp)
    return hmac.compare_digest(expected, otp_hash)


# ---------------------------------------------------------------------------
# Twilio SMS
# ---------------------------------------------------------------------------

def _send_twilio_sms(to_number: str, message: str) -> bool:
    """Send an SMS via Twilio. Returns True on success."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        return False

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number,
        )
        return True
    except Exception as e:
        # Log but don't crash; dev mode will fall back to console OTP
        if DEV_MODE:
            print(f"[Twilio error] {e}")
        return False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _is_rate_limited(mobile: str) -> bool:
    """Check if a mobile has exceeded auth attempt rate limits."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    # Clean old entries
    _attempt_tracker[mobile] = [t for t in _attempt_tracker.get(mobile, []) if t > window_start]
    return len(_attempt_tracker.get(mobile, [])) >= RATE_LIMIT_MAX_ATTEMPTS


def _record_attempt(mobile: str) -> None:
    """Record an auth attempt for rate limiting."""
    _attempt_tracker[mobile].append(time.time())


def _can_resend(mobile: str) -> bool:
    """Check if enough time has passed since last OTP resend."""
    now = time.time()
    last = _resend_tracker.get(mobile, 0)
    return (now - last) >= OTP_RESEND_COOLDOWN_SECONDS


def _record_resend(mobile: str) -> None:
    """Record that an OTP was resent for a mobile."""
    _resend_tracker[mobile] = time.time()


# ---------------------------------------------------------------------------
# Database OTP operations
# ---------------------------------------------------------------------------

def _clean_expired_otps(mobile: str) -> None:
    """Delete expired OTP records for a mobile."""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM otp_codes WHERE mobile = %s AND expires_at < %s",
            (mobile, _now()),
        )
        conn.commit()
    except Error as e:
        print(f"[OTP cleanup error] {e}")
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


def store_otp(mobile: str, otp: str, purpose: str = "registration") -> None:
    """Store a hashed OTP in the database, invalidating previous OTPs."""
    otp_hash = _hash_otp(otp)
    expires_at = _now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        # Invalidate any previous unconsumed OTPs for this mobile/purpose
        cur.execute(
            "UPDATE otp_codes SET consumed_at = %s WHERE mobile = %s AND purpose = %s AND consumed_at IS NULL",
            (_now(), mobile, purpose),
        )
        cur.execute(
            "INSERT INTO otp_codes (mobile, otp_hash, purpose, expires_at) VALUES (%s, %s, %s, %s)",
            (mobile, otp_hash, purpose, expires_at),
        )
        conn.commit()
    except Error as e:
        raise RuntimeError(f"Failed to store OTP: {e}")
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


def verify_otp_from_db(mobile: str, otp: str, purpose: str = "registration") -> Tuple[bool, str]:
    """
    Verify an OTP against the database.
    Returns (success, message).
    Expired OTPs are reported explicitly (not silently deleted before the check).
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, otp_hash, attempts, max_attempts, expires_at, consumed_at
               FROM otp_codes
               WHERE mobile = %s AND purpose = %s AND consumed_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (mobile, purpose),
        )
        row = cur.fetchone()
        if not row:
            return False, "No valid OTP found. Please request a new code."

        # Check expiration explicitly (before attempting to verify the hash)
        expires_at = row["expires_at"]
        if _now() > expires_at:
            return False, "OTP has expired. Please request a new code."

        # Check max attempts
        if row["attempts"] >= row["max_attempts"]:
            return False, "Maximum verification attempts exceeded. Please request a new code."

        # Verify OTP hash
        if not _verify_otp_hash(otp, row["otp_hash"]):
            # Increment attempt counter
            cur.execute(
                "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = %s",
                (row["id"],),
            )
            conn.commit()
            remaining = row["max_attempts"] - row["attempts"]
            return False, f"Invalid OTP. {remaining} attempt(s) remaining."

        # Mark OTP as consumed
        cur.execute(
            "UPDATE otp_codes SET consumed_at = %s WHERE id = %s",
            (_now(), row["id"]),
        )
        conn.commit()
        return True, "OTP verified successfully."
    except Error as e:
        return False, f"Verification error: {e}"
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


# ---------------------------------------------------------------------------
# OTP send (Twilio + dev fallback)
# ---------------------------------------------------------------------------

def send_otp(mobile: str, purpose: str = "registration") -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
    """
    Generate, store, and send an OTP.
    Returns (success, message, dev_otp_or_none, meta_dict).
    meta_dict contains 'resend_in' (seconds until resend allowed) and
    'expires_in' (seconds until OTP expiry) so the frontend can render an
    accurate countdown driven by the backend.
    In development mode (OTP_DEBUG=true), the OTP is printed to the terminal.
    Never returns the OTP in production.
    """
    # Record this send attempt for rate limiting
    _record_attempt(mobile)

    # Rate limit check
    if _is_rate_limited(mobile):
        return False, "Too many attempts. Please try again later.", None, None

    # Resend cooldown check based on the most recent OTP record in the DB
    conn = None
    cur = None
    resend_in = 0
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """SELECT created_at FROM otp_codes
               WHERE mobile = %s AND purpose = %s
               ORDER BY created_at DESC LIMIT 1""",
            (mobile, purpose),
        )
        row = cur.fetchone()
        if row:
            last_sent = row[0]
            elapsed = (_now() - last_sent).total_seconds()
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                resend_in = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                return (
                    False,
                    f"Please wait {resend_in} second(s) before requesting a new code.",
                    None,
                    {"resend_in": resend_in, "expires_in": 0},
                )
    except Error:
        pass
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

    # Generate OTP
    otp = _generate_otp()

    # Store in DB (also sets created_at which drives the resend cooldown)
    try:
        store_otp(mobile, otp, purpose)
    except RuntimeError as e:
        return False, str(e), None, None

    # Send via Twilio or dev fallback
    message_body = f"Your Kisaan Suvidha verification code is {otp}. It expires in {OTP_EXPIRY_MINUTES} minutes."
    sent = _send_twilio_sms(mobile, message_body)

    dev_otp = None
    if DEV_MODE and OTP_DEBUG:
        dev_otp = otp
        print(f"\n{'='*60}")
        print(f"[DEVELOPMENT OTP] Mobile: {mobile}")
        print(f"[DEVELOPMENT OTP] Code: {otp}")
        print(f"[DEVELOPMENT OTP] Purpose: {purpose}")
        print(f"[DEVELOPMENT OTP] Expires in {OTP_EXPIRY_MINUTES} minutes")
        print(f"{'='*60}\n")

    if sent:
        _record_resend(mobile)
        return True, "Verification code sent via SMS.", dev_otp, {"resend_in": 0, "expires_in": OTP_EXPIRY_MINUTES * 60}
    elif DEV_MODE:
        # In dev mode, if Twilio is not configured, still allow via console OTP
        _record_resend(mobile)
        return True, "Verification code ready (development mode - see terminal).", dev_otp, {"resend_in": 0, "expires_in": OTP_EXPIRY_MINUTES * 60}
    else:
        return False, "Failed to send SMS. Please check Twilio configuration.", None, None


# ---------------------------------------------------------------------------
# User lookup
# ---------------------------------------------------------------------------

def get_user_by_mobile(mobile: str) -> Optional[Dict[str, Any]]:
    """Fetch a user by mobile number from the database."""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, full_name, mobile, password_hash, state_id, district_id,
                      tehsil_id, village_id, state_name, district_name, tehsil_name,
                      village_name, is_verified, created_at, updated_at
               FROM users WHERE mobile = %s""",
            (mobile,),
        )
        return cur.fetchone()
    except Error:
        return None
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


def create_user(
    full_name: str,
    mobile: str,
    password_hash: str,
    state_id: Optional[int] = None,
    district_id: Optional[int] = None,
    tehsil_id: Optional[int] = None,
    village_id: Optional[int] = None,
    state_name: Optional[str] = None,
    district_name: Optional[str] = None,
    tehsil_name: Optional[str] = None,
    village_name: Optional[str] = None,
) -> Optional[int]:
    """Create a new user and return the user ID, or None on failure."""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users
               (full_name, mobile, password_hash, state_id, district_id, tehsil_id,
                village_id, state_name, district_name, tehsil_name, village_name, is_verified)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)""",
            (
                full_name, mobile, password_hash,
                state_id, district_id, tehsil_id, village_id,
                state_name, district_name, tehsil_name, village_name,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Error:
        return None
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


def update_user_password(user_id: int, password_hash: str) -> bool:
    """Update a user's password hash."""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (password_hash, _now(), user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Error:
        return False
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a user by ID from the database."""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, full_name, mobile, password_hash, state_id, district_id,
                      tehsil_id, village_id, state_name, district_name, tehsil_name,
                      village_name, is_verified, created_at, updated_at
               FROM users WHERE id = %s""",
            (user_id,),
        )
        return cur.fetchone()
    except Error:
        return None
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass
