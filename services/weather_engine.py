"""
services/weather_engine.py - Weather Engine with OpenWeatherMap Integration

Provides real-time weather data and forecasts for Indian farm locations.
Replaces the previous hardcoded SAMPLE_FORECAST with live API data.

Implements:
- Current weather retrieval via OpenWeatherMap Current Weather API
- Geocoding via OpenWeatherMap Geocoding API
- Timeout, connection error, and rate-limit handling
- Response validation
- Caching to avoid unnecessary API calls
- Graceful fallback when weather service is unavailable
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Caches
_weather_cache = TTLCache(maxsize=100, ttl=600)  # 10 minutes
_geocode_cache = TTLCache(maxsize=100, ttl=86400)  # 24 hours


def _get_openweather_config() -> Dict[str, Optional[str]]:
    """Retrieve OpenWeatherMap API configuration from environment variables."""
    return {
        "api_key": os.environ.get("OPENWEATHER_API_KEY"),
        "base_url": "https://api.openweathermap.org/data/2.5",
    }


def _geocode_location(
    state: str,
    district: str,
    api_key: str,
) -> Optional[Dict[str, float]]:
    """
    Geocode a location using OpenWeatherMap Geocoding API.

    Tries multiple location formats to find coordinates.

    Args:
        state: Indian state name
        district: Indian district name
        api_key: OpenWeatherMap API key

    Returns:
        Dictionary with lat, lon or None
    """
    # Check cache first
    cache_key = f"{state}:{district}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    queries = [
        f"{district}, {state}, IN",
        f"{state}, IN",
        f"{district}, IN",
    ]

    for query in queries:
        try:
            response = requests.get(
                "https://api.openweathermap.org/geo/1.0/direct",
                params={
                    "q": query,
                    "limit": 1,
                    "appid": api_key,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 0:
                result = {
                    "lat": data[0]["lat"],
                    "lon": data[0]["lon"],
                    "name": data[0].get("name", district),
                    "state": data[0].get("state", state),
                    "country": data[0].get("country", "IN"),
                }
                _geocode_cache[cache_key] = result
                return result
        except Exception as e:
            logger.debug("Geocoding attempt failed for %s: %s", query, e)
            continue

    logger.warning("Could not geocode location: %s, %s", state, district)
    return None


def get_current_weather(
    state: str,
    district: str,
) -> Dict[str, Any]:
    """
    Retrieve current weather for a farm location using OpenWeatherMap API.

    Args:
        state: Indian state name
        district: Indian district name

    Returns:
        Weather dictionary with current conditions.
        Returns fallback data with 'source': 'fallback' if API unavailable.
    """
    config = _get_openweather_config()
    api_key = config["api_key"]

    # Check cache
    cache_key = f"weather:{state}:{district}"
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]

    result: Dict[str, Any]

    if not api_key or api_key == "your_openweather_api_key_here":
        logger.warning("OpenWeatherMap API key not configured")
        result = _fallback_weather(state, district, reason="api_key_not_configured")
        _weather_cache[cache_key] = result
        return result

    # Geocode the location
    location = _geocode_location(state, district, api_key)
    if location is None:
        logger.warning("Could not geocode location: %s, %s", state, district)
        result = _fallback_weather(state, district, reason="geocoding_failed")
        _weather_cache[cache_key] = result
        return result

    lat = location["lat"]
    lon = location["lon"]

    try:
        response = requests.get(
            f"{config['base_url']}/weather",
            params={
                "lat": lat,
                "lon": lon,
                "appid": api_key,
                "units": "metric",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        result = {
            "source": "openweathermap",
            "location": {
                "state": state,
                "district": district,
                "resolved_name": location.get("name", district),
                "resolved_state": location.get("state", state),
                "lat": lat,
                "lon": lon,
            },
            "temperature": round(data.get("main", {}).get("temp", 0), 1),
            "feels_like": round(data.get("main", {}).get("feels_like", 0), 1),
            "humidity": data.get("main", {}).get("humidity", 0),
            "pressure": data.get("main", {}).get("pressure", 0),
            "wind_speed": data.get("wind", {}).get("speed", 0),
            "wind_deg": data.get("wind", {}).get("deg", 0),
            "description": data.get("weather", [{}])[0].get("description", "Unknown"),
            "condition": data.get("weather", [{}])[0].get("main", "Unknown"),
            "cloud_coverage": data.get("clouds", {}).get("all", 0),
            "rainfall_1h": data.get("rain", {}).get("1h", 0),
            "rainfall_3h": data.get("rain", {}).get("3h", 0),
            "sunrise": data.get("sys", {}).get("sunrise", 0),
            "sunset": data.get("sys", {}).get("sunset", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }

        _weather_cache[cache_key] = result
        return result

    except requests.exceptions.Timeout:
        logger.error("OpenWeatherMap API request timed out")
        result = _fallback_weather(state, district, reason="timeout")
    except requests.exceptions.ConnectionError:
        logger.error("OpenWeatherMap API connection error")
        result = _fallback_weather(state, district, reason="connection_error")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.error("OpenWeatherMap API rate limit exceeded")
            result = _fallback_weather(state, district, reason="rate_limit")
        elif e.response.status_code == 401:
            logger.error("OpenWeatherMap API authentication failed")
            result = _fallback_weather(state, district, reason="auth_failed")
        else:
            logger.error("OpenWeatherMap API HTTP error: %s", e)
            result = _fallback_weather(state, district, reason=f"http_error_{e.response.status_code}")
    except Exception as e:
        logger.error("Unexpected error fetching weather: %s", e)
        result = _fallback_weather(state, district, reason="unexpected_error")

    _weather_cache[cache_key] = result
    return result


def _fallback_weather(
    state: str,
    district: str,
    reason: str = "service_unavailable",
) -> Dict[str, Any]:
    """
    Return fallback weather data when OpenWeatherMap is unavailable.

    NEVER presents this as real weather data. Clearly marked as fallback.

    Args:
        state: Indian state name
        district: Indian district name
        reason: Reason for fallback

    Returns:
        Fallback weather dictionary
    """
    return {
        "source": "fallback",
        "location": {
            "state": state,
            "district": district,
            "resolved_name": district,
            "resolved_state": state,
            "lat": None,
            "lon": None,
        },
        "temperature": None,
        "feels_like": None,
        "humidity": None,
        "pressure": None,
        "wind_speed": None,
        "wind_deg": None,
        "description": "Weather data unavailable",
        "condition": "Unknown",
        "cloud_coverage": None,
        "rainfall_1h": None,
        "rainfall_3h": None,
        "timestamp": None,
        "error_reason": reason,
        "message": (
            "Real-time weather data is unavailable. "
            "Please configure OpenWeatherMap API key or check your internet connection."
        ),
    }


def format_weather_for_display(weather: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format weather data for template display.

    Handles None values gracefully and provides display-ready strings.

    Args:
        weather: Weather dictionary from get_current_weather

    Returns:
        Display-ready weather dictionary
    """
    temp = weather.get("temperature")
    humidity = weather.get("humidity")
    description = weather.get("description", "Unknown")
    condition = weather.get("condition", "Unknown")
    rainfall = weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0
    wind_speed = weather.get("wind_speed")

    return {
        "source": weather.get("source", "unknown"),
        "temperature_display": f"{temp}°C" if temp is not None else "N/A",
        "humidity_display": f"{humidity}%" if humidity is not None else "N/A",
        "description": description,
        "condition": condition,
        "rainfall_display": f"{rainfall} mm" if rainfall is not None and rainfall > 0 else "N/A",
        "wind_speed_display": f"{wind_speed} m/s" if wind_speed is not None else "N/A",
        "feels_like_display": f"{weather.get('feels_like')}°C" if weather.get("feels_like") is not None else "N/A",
        "location": weather.get("location", {}),
        "error_reason": weather.get("error_reason"),
        "is_real_time": weather.get("source") == "openweathermap",
    }
