"""
routes/crop_suitability_routes.py - Crop Suitability Analysis blueprint

Implements weather-based + soil pH-based crop suitability analysis.

Weather data is primarily sourced from OpenWeatherMap One Call API 3.0
(https://openweathermap.org/api/one-call-3) which provides 7-day daily
forecasts including temperature, humidity, rainfall, and wind speed.

If OpenWeather is unavailable (auth failure, rate limit, timeout, or any
error), the route falls back to the free Open-Meteo Forecast API
(https://api.open-meteo.com/v1/forecast) which requires no API key and
provides 7-day daily forecast data including temperature, humidity, wind
speed, and precipitation.

All weather suitability calculations are delegated to the centralized
services/weather_suitability_service.py which loads reference values
dynamically from TEMPERATURE_DATASET_optimal_temp_ranges_filled.csv.

Endpoints:
- GET  /crop-suitability                    - Input form page
- POST /crop-suitability/analyze            - Analyze suitability (POST form)
- GET  /api/crop-suitability/categories     - Get crop categories
- GET  /api/crop-suitability/crops/search   - Search crops by name
- GET  /api/crop-suitability/crops/category/<name> - Get crops by category
"""

import logging
import os
import pytz
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

from flask import Blueprint, current_app, jsonify, render_template, request, session

from auth.decorators import login_required
from services.crop_data_service import get_categories, get_crop_by_name, get_crops_by_category, search_crops
from services.crop_duration_service import calculate_growth_progress, get_crop_duration
from services.weather_aggregation_service import (
    aggregate_daily_weather,
    build_hourly_readings_for_suitability,
)
from services.weather_service import fetch_7day_forecast, geocode_location
from services.weather_suitability_service import analyse_suitability

logger = logging.getLogger(__name__)

crop_suitability_bp = Blueprint("crop_suitability", __name__, url_prefix="/crop-suitability")

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

IST = pytz.timezone("Asia/Kolkata")


def _geocode_village_openmeteo(state: str, district: str, village: str) -> Optional[Dict[str, Any]]:
    """Geocode a village location using Open-Meteo Geocoding API (no API key).

    Tries village + district + state, then district + state, then state.
    Used as a fallback when OpenWeather geocoding fails.
    """
    queries = [
        f"{village}, {district}, {state}, India",
        f"{district}, {state}, India",
        f"{state}, India",
    ]

    for query in queries:
        try:
            response = requests.get(
                OPEN_METEO_GEOCODING_URL,
                params={"name": query, "count": 1, "language": "en", "format": "json"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if results:
                r = results[0]
                return {
                    "lat": r.get("latitude"),
                    "lon": r.get("longitude"),
                    "name": r.get("name", village),
                    "state": r.get("admin1", state),
                    "country": r.get("country", "IN"),
                }
        except Exception as e:
            logger.debug("Open-Meteo geocoding attempt failed for %s: %s", query, e)
            continue

    return None


def _fetch_openmeteo_forecast(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetch 7-day daily forecast from Open-Meteo Forecast API (no API key).

    Requests daily temperature max/min, humidity, wind speed, precipitation,
    and weather code for 7 days. All timestamps in Asia/Kolkata.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "relative_humidity_2m_mean",
            "wind_speed_10m_max",
            "wind_speed_10m_mean",
            "precipitation_sum",
            "precipitation_probability_max",
            "weather_code",
        ],
        "timezone": "Asia/Kolkata",
        "forecast_days": 7,
    }
    try:
        response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Open-Meteo Forecast request failed: %s", e)
        return None


# Open-Meteo WMO weather code -> condition label mapping
WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _weather_code_to_condition(code: Any) -> str:
    """Map Open-Meteo WMO weather code to a human-readable condition."""
    try:
        return WEATHER_CODE_MAP.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def _normalize_openmeteo_daily(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize Open-Meteo daily forecast into the standard daily summary format.

    Maps Open-Meteo fields to the common schema used by the frontend:
    date, avg_temperature, min_temperature, max_temperature, avg_humidity,
    total_rainfall, avg_wind_speed, wind_direction, condition, description, pop.

    No values are fabricated; missing API fields are returned as None.
    """
    daily = data.get("daily", {}) or {}
    times = daily.get("time", []) or []
    if not times:
        return []

    temp_maxs = daily.get("temperature_2m_max", []) or []
    temp_mins = daily.get("temperature_2m_min", []) or []
    temp_means = daily.get("temperature_2m_mean", []) or []
    humidities = daily.get("relative_humidity_2m_mean", []) or []
    wind_maxs = daily.get("wind_speed_10m_max", []) or []
    wind_means = daily.get("wind_speed_10m_mean", []) or []
    rains = daily.get("precipitation_sum", []) or []
    pops = daily.get("precipitation_probability_max", []) or []
    codes = daily.get("weather_code", []) or []

    normalized: List[Dict[str, Any]] = []
    for i, date_str in enumerate(times):
        t_max = temp_maxs[i] if i < len(temp_maxs) else None
        t_min = temp_mins[i] if i < len(temp_mins) else None
        t_mean = temp_means[i] if i < len(temp_means) else None
        hum = humidities[i] if i < len(humidities) else None
        w_max = wind_maxs[i] if i < len(wind_maxs) else None
        w_mean = wind_means[i] if i < len(wind_means) else None
        rain = rains[i] if i < len(rains) else None
        pop = pops[i] if i < len(pops) else None
        code = codes[i] if i < len(codes) else None

        # Average temperature from available components
        temp_components = [v for v in [t_mean, t_min, t_max] if v is not None]
        avg_temp = (sum(temp_components) / len(temp_components)) if temp_components else None

        # Average wind speed from available components
        wind_components = [v for v in [w_mean, w_max] if v is not None]
        avg_wind = (sum(wind_components) / len(wind_components)) if wind_components else None

        condition = _weather_code_to_condition(code)

        normalized.append({
            "date": date_str,
            "condition": condition,
            "description": condition,
            "avg_temperature": avg_temp,
            "min_temperature": t_min,
            "max_temperature": t_max,
            "avg_humidity": hum,
            "total_rainfall": rain,
            "avg_wind_speed": avg_wind,
            "wind_direction": None,  # Open-Meteo daily doesn't provide wind direction
            "pop": pop / 100.0 if pop is not None else None,  # convert % to 0-1
            "source": "open-meteo",
        })

    return normalized


@crop_suitability_bp.route("/", methods=["GET", "POST"])
@login_required
def suitability_analysis():
    """Main crop suitability analysis page.

    GET: Show input form with crop selector and location fields.
    POST: Process form submission, analyze suitability, show results.
    """
    if request.method == "GET":
        categories = get_categories()
        return render_template(
            "crop_suitability_analysis.html",
            categories=categories,
            active_page="suitability",
        )

    # POST - analyze
    crop_name = request.form.get("crop", "").strip()
    state_id = request.form.get("state_id", "").strip()
    district_id = request.form.get("district_id", "").strip()
    tehsil_id = request.form.get("tehsil_id", "").strip()
    village_id = request.form.get("village_id", "").strip()
    state_name = request.form.get("state_name", "").strip()
    district_name = request.form.get("district_name", "").strip()
    tehsil_name = request.form.get("tehsil_name", "").strip()
    village_name = request.form.get("village_name", "").strip()
    soil_ph = request.form.get("soil_ph", "").strip()
    sowing_date = request.form.get("sowing_date", "").strip()

    # Validation
    errors: List[str] = []

    if not crop_name:
        errors.append("Please select a crop.")

    crop = get_crop_by_name(crop_name)
    if not crop:
        errors.append("Selected crop not found in database.")

    if not state_id:
        errors.append("Please select a state.")
    if not district_id:
        errors.append("Please select a district.")
    if not tehsil_id:
        errors.append("Please select a tehsil / subdistrict.")
    if not village_id:
        errors.append("Please select a village.")

    ph_value: Optional[float] = None
    if soil_ph:
        try:
            ph_value = float(soil_ph)
            if ph_value < 0 or ph_value > 14:
                errors.append("Please enter a valid soil pH value (0-14).")
                ph_value = None
        except ValueError:
            errors.append("Please enter a valid soil pH value.")
            ph_value = None

    if errors:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "validation_error",
                    "message": " ".join(errors),
                }
            ),
            400,
        )

    # Geocode the location using OpenWeatherMap Geocoding API
    location = geocode_location(state_name, district_name, village_name)
    forecast_source = "openweathermap"
    forecast_period: Dict[str, str] = {}
    location_name = f"{village_name or ''}, {district_name or ''}, {state_name or ''}".strip(", ")
    location_resolved: Dict[str, str] = {
        "state": state_name,
        "district": district_name,
        "village": village_name,
    }

    hourly_by_day: List[List[Dict[str, Any]]] = []
    dates: List[str] = []
    daily_summary: List[Dict[str, Any]] = []
    forecast: Optional[Dict[str, Any]] = None

    if location is None:
        # Try Open-Meteo geocoding as fallback
        logger.warning("OpenWeather geocoding failed for %s, %s, %s", village_name, district_name, state_name)
        location = _geocode_village_openmeteo(state_name, district_name, village_name)
        if location is None:
            logger.warning("Open-Meteo geocoding also failed for %s, %s, %s", village_name, district_name, state_name)
            dates = []
            hourly_by_day = []
            daily_summary = []
            forecast_period = {
                "start": "",
                "end": "",
                "source": "geocoding_failed",
            }
        else:
            forecast_source = "open-meteo"
            forecast_raw = _fetch_openmeteo_forecast(location["lat"], location["lon"])
            if forecast_raw is None:
                logger.warning("Open-Meteo forecast unavailable for %s, %s", location["lat"], location["lon"])
                dates = []
                hourly_by_day = []
                daily_summary = []
                forecast_period = {
                    "start": "",
                    "end": "",
                    "source": "forecast_unavailable",
                }
            else:
                daily_summary = _normalize_openmeteo_daily(forecast_raw)
                dates = [d["date"] for d in daily_summary if d.get("date")]
                hourly_by_day = build_hourly_readings_for_suitability(daily_summary)
                forecast_period = {
                    "start": dates[0] if dates else "",
                    "end": dates[-1] if dates else "",
                    "source": forecast_source,
                }
            location_name = location.get("name", village_name)
            location_resolved = {
                "state": location.get("state", state_name),
                "district": district_name,
                "village": village_name,
            }
    else:
        # Get 7-day forecast from OpenWeather One Call API 3.0
        forecast = fetch_7day_forecast(location["lat"], location["lon"])
        if forecast is None:
            # OpenWeather failed: fall back to Open-Meteo
            logger.warning(
                "OpenWeather forecast unavailable for %s, %s; falling back to Open-Meteo",
                location["lat"], location["lon"],
            )
            forecast_source = "open-meteo"
            forecast_raw = _fetch_openmeteo_forecast(location["lat"], location["lon"])
            if forecast_raw is None:
                logger.warning("Open-Meteo forecast also unavailable for %s, %s", location["lat"], location["lon"])
                dates = []
                hourly_by_day = []
                daily_summary = []
                forecast_period = {
                    "start": "",
                    "end": "",
                    "source": "forecast_unavailable",
                }
            else:
                daily_summary = _normalize_openmeteo_daily(forecast_raw)
                dates = [d["date"] for d in daily_summary if d.get("date")]
                hourly_by_day = build_hourly_readings_for_suitability(daily_summary)
                forecast_period = {
                    "start": dates[0] if dates else "",
                    "end": dates[-1] if dates else "",
                    "source": forecast_source,
                }
        else:
            forecast_source = "openweathermap"
            raw_daily = forecast.get("daily", [])
            daily_summary = aggregate_daily_weather(raw_daily)
            dates = [d["date"] for d in daily_summary if d.get("date")]
            hourly_by_day = build_hourly_readings_for_suitability(daily_summary)
            forecast_period = {
                "start": dates[0] if dates else "",
                "end": dates[-1] if dates else "",
                "source": forecast_source,
            }
        location_name = location.get("name", village_name)
        location_resolved = {
            "state": location.get("state", state_name),
            "district": district_name,
            "village": village_name,
        }

    # Run centralized suitability analysis
    result = analyse_suitability(crop_name, hourly_by_day, ph_value)

    if not result["success"]:
        return jsonify(result), 400

    # Crop season and duration information
    crop_duration = get_crop_duration(crop_name)
    growth_progress = calculate_growth_progress(crop_duration, sowing_date)

    # Build response data for frontend
    weather = result["weather_analysis"]
    ph = result["ph_analysis"]
    crop_info = result["crop"]

    # Map daily assessments with weather details (humidity, wind, rainfall)
    daily_assessments = weather.get("daily_assessments", [])
    enriched_daily: List[Dict[str, Any]] = []
    for i, assessment in enumerate(daily_assessments):
        weather_detail = daily_summary[i] if i < len(daily_summary) else {}
        enriched_daily.append({
            **assessment,
            "avg_temperature": weather_detail.get("avg_temperature"),
            "min_temperature": weather_detail.get("min_temperature"),
            "max_temperature": weather_detail.get("max_temperature"),
            "avg_humidity": weather_detail.get("avg_humidity"),
            "total_rainfall": weather_detail.get("total_rainfall"),
            "avg_wind_speed": weather_detail.get("avg_wind_speed"),
            "wind_direction": weather_detail.get("wind_direction"),
            "condition": weather_detail.get("condition", "Unknown"),
            "description": weather_detail.get("description", "Unknown"),
            "pop": weather_detail.get("pop"),
        })

    response_data = {
        "success": True,
        "crop": {
            "name": crop_info["name"],
            "category": crop.get("category", "Unknown"),
            "best_low_temp": crop_info["best_low_temp"],
            "best_high_temp": crop_info["best_high_temp"],
            "low_temp": crop_info["low_temp"],
            "max_temp": crop_info["max_temp"],
            "ph_min": crop_info["ph_min"],
            "ph_max": crop_info["ph_max"],
        },
        "crop_duration": crop_duration,
        "growth_progress": growth_progress,
        "sowing_date": sowing_date,
        "location": {
            "name": location_name,
            "state": location_resolved.get("state", ""),
            "district": location_resolved.get("district", ""),
            "tehsil": tehsil_name,
            "village": village_name,
        },
        "soil_ph": ph_value,
        "forecast_period": forecast_period,
        "weather_analysis": weather,
        "ph_analysis": {
            "farmer_ph": ph["farmer_ph"],
            "crop_min": ph["crop_min"],
            "crop_max": ph["crop_max"],
            "status": ph["status"],
            "message": ph["message"],
            "explanation": ph.get("explanation", ""),
            "difference": ph.get("difference"),
        },
        "daily_assessments": enriched_daily,
        "overall": {
            "status": weather["status"],
            "label": weather["label"],
            "score": weather["weekly_score"],
            "valid_days": weather["valid_days"],
            "total_days": weather["total_days"],
            "message": weather.get("explanation", ""),
        },
        "daily_summary": daily_summary,
    }

    return jsonify(response_data)


@crop_suitability_bp.route("/api/categories", methods=["GET"])
@login_required
def api_categories():
    """Get all crop categories."""
    try:
        categories = get_categories()
        return jsonify({"success": True, "data": categories})
    except Exception as e:
        logger.error("Error fetching categories: %s", e)
        return jsonify({"success": False, "error": "server_error", "message": str(e)}), 500


@crop_suitability_bp.route("/api/crops/search", methods=["GET"])
@login_required
def api_crop_search():
    """Search crops by name."""
    query = request.args.get("q", "")
    try:
        crops = search_crops(query, limit=50)
        return jsonify({"success": True, "data": crops})
    except Exception as e:
        logger.error("Error searching crops: %s", e)
        return jsonify({"success": False, "error": "server_error", "message": str(e)}), 500


@crop_suitability_bp.route("/api/crops/category/<path:category_name>", methods=["GET"])
@login_required
def api_crops_by_category(category_name: str):
    """Get crops by category."""
    try:
        crops = get_crops_by_category(category_name)
        return jsonify({"success": True, "data": crops})
    except Exception as e:
        logger.error("Error fetching crops by category: %s", e)
        return jsonify({"success": False, "error": "server_error", "message": str(e)}), 500
