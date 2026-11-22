"""
routes/main_routes.py - Dashboard, Profile settings, and embed demo
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from auth.decorators import login_required
from data.db import get_db
from mysql.connector import Error
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

main_bp = Blueprint("main", __name__)


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


def get_automatic_season(state: str, district: str) -> str:
    """
    Automatically determine the current agricultural season based on date and location.
    Uses Indian agricultural seasonal calendars:
    - Kharif: June-October (monsoon crops)
    - Rabi: November-March (winter crops)
    - Zaid: April-May (summer crops)
    """
    now = datetime.now(IST)
    month = now.month

    if month in (6, 7, 8, 9, 10):
        return "Kharif"
    elif month in (11, 12, 1, 2, 3):
        return "Rabi"
    else:
        return "Zaid"


def get_greeting() -> str:
    """Return greeting based on Asia/Kolkata local time."""
    now = datetime.now(IST)
    hour = now.hour

    if 5 <= hour < 12:
        return "Good Morning"
    elif 12 <= hour < 17:
        return "Good Afternoon"
    elif 17 <= hour < 21:
        return "Good Evening"
    else:
        return "Good Night"


def get_current_datetime_info() -> dict:
    """Return current Indian date, time, and greeting."""
    now = datetime.now(IST)
    return {
        "date": now.strftime("%d %b %Y"),
        "day": now.strftime("%A"),
        "time": now.strftime("%I:%M %p"),
        "greeting": get_greeting(),
    }


def resolve_location_ids(form):
    """Resolve location IDs submitted by the profile form into (id, name) pairs.
    Missing/invalid ids yield None so existing session values are preserved.
    """
    fields = [('state', 'states'), ('district', 'districts'),
              ('tehsil', 'tehsils'), ('village', 'villages')]
    out = {}
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        for field, table in fields:
            raw = (form.get(f'{field}_id') or '').strip()
            out[f'{field}_id'] = None
            out[f'{field}_name'] = None
            if not raw:
                continue
            try:
                lid = int(raw)
            except ValueError:
                continue
            cur.execute(
                f'SELECT name FROM {table} WHERE id = %s AND is_active = 1',
                (lid,),
            )
            row = cur.fetchone()
            if row is None:
                continue
            out[f'{field}_id'] = lid
            out[f'{field}_name'] = row[0]
        return out
    except Error:
        return out
    finally:
        if cur is not None:
            try: cur.close()
            except Exception: pass
        if conn is not None:
            try: conn.close()
            except Exception: pass


@main_bp.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user() or {}

    # Get current datetime info
    datetime_info = get_current_datetime_info()

    # Determine automatic season
    auto_season = get_automatic_season(
        user.get("state", "Punjab"),
        user.get("district", "Ludhiana"),
    )

    # Fetch real-time weather
    from services.weather_engine import get_current_weather, format_weather_for_display
    weather = get_current_weather(
        user.get("state", "Punjab"),
        user.get("district", "Ludhiana"),
    )
    weather_display = format_weather_for_display(weather)

    # Generate dynamic farming message based on weather
    farming_message = _generate_farming_message(weather_display, auto_season, user.get("district", ""))

    return render_template(
        "dashboard.html",
        user=user,
        active_page="dashboard",
        datetime_info=datetime_info,
        auto_season=auto_season,
        weather=weather_display,
        farming_message=farming_message,
    )


def _generate_farming_message(weather: dict, season: str, district: str) -> str:
    """
    Generate dynamic farming message based on current weather and season.
    Never recommends a specific crop - only weather-based guidance.
    """
    condition = (weather.get("condition") or "").lower()
    temperature = weather.get("temperature")
    humidity = weather.get("humidity")
    rainfall = weather.get("rainfall_1h") or weather.get("rainfall_3h")

    messages = []

    # Temperature-based advice
    if temperature is not None:
        if temperature > 35:
            messages.append(f"Heat alert: {temperature}°C. Avoid midday field work and ensure adequate irrigation.")
        elif temperature < 15:
            messages.append(f"Cool conditions: {temperature}°C. Protect crops from cold stress.")
        else:
            messages.append(f"Temperature {temperature}°C is suitable for field activities.")

    # Rainfall advice
    if rainfall and rainfall > 0:
        messages.append(f"Recent rainfall: {rainfall} mm. Monitor soil moisture and avoid over-irrigation.")
    elif rainfall == 0:
        messages.append("No recent rainfall. Plan irrigation based on crop needs.")

    # Humidity advice
    if humidity is not None:
        if humidity > 80:
            messages.append(f"High humidity ({humidity}%). Watch for fungal diseases.")
        elif humidity < 40:
            messages.append(f"Low humidity ({humidity}%). Increase irrigation frequency.")

    # Condition-based advice
    if "rain" in condition:
        messages.append("Rainy conditions expected. Delay spraying and field operations.")
    elif "clear" in condition or "sunny" in condition:
        messages.append("Clear skies. Good time for field work and harvesting.")
    elif "cloud" in condition:
        messages.append("Cloudy conditions. Monitor for disease development.")

    if not messages:
        messages.append("Current weather is suitable for general farm activities.")

    return ". ".join(messages) + "."


@main_bp.route("/profile", methods=["GET", "POST"])
def profile():
    user = get_current_user()
    if not user:
        flash("Please log in to access your profile.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        # Basic profile fields
        user["name"] = request.form.get("name", user.get("name"))
        user["mobile"] = request.form.get("mobile", user.get("mobile"))
        user["farm_size"] = request.form.get("farm_size", user.get("farm_size"))
        user["soil_type"] = request.form.get("soil_type", user.get("soil_type"))
        user["irrigation"] = request.form.get("irrigation", user.get("irrigation"))
        user["preferred_language"] = request.form.get("preferred_language", user.get("preferred_language"))
        # Location: persist both IDs and resolved LGD names.
        location = resolve_location_ids(request.form)
        for field in ("state", "district", "tehsil", "village"):
            lid = location.get(f"{field}_id")
            if lid is not None:
                user[f"{field}_id"] = lid
                user[f"{field}_name"] = location.get(f"{field}_name")

        session["user_profile"] = user
        session.modified = True
        flash("Your farm profile details have been successfully saved.", "success")
        return redirect(url_for("main.profile"))

    return render_template(
        "profile.html",
        user=user,
        active_page="profile"
    )


@main_bp.route("/embed-demo")
def embed_demo():
    """Showcases how KisaanBot can be embedded as a widget on any third-party agricultural website."""
    return render_template("embed_demo.html")
