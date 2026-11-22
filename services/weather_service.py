"""
services/weather_service.py - OpenWeather One Call API 3.0 integration

Fetches and normalizes 7-day weather forecast data for Indian farm locations.
Uses OpenWeatherMap One Call API 3.0 which provides daily forecasts including
temperature, humidity, rainfall, wind speed, and wind direction.

API key is read from the OPENWEATHER_API_KEY environment variable (.env).
Never exposes the API key to frontend JavaScript.

Implements:
- Geocoding via OpenWeatherMap Geocoding API
- 7-day daily forecast via One Call API 3.0
- Timeout, connection error, HTTP status validation
- Caching (TTL) to avoid unnecessary repeated API requests
- Graceful fallback when the weather service is unavailable
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Caches
_weather_cache = TTLCache(maxsize=100, ttl=600)   # 10 minutes
_geocode_cache = TTLCache(maxsize=100, ttl=86400)  # 24 hours

OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/3.0"
OPENWEATHER_GEO_URL = "https://api.openweathermap.org/geo/1.0"

# Wind direction categories (16-point compass)
WIND_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _get_openweather_config() -> Dict[str, Optional[str]]:
    """Retrieve OpenWeatherMap API configuration from environment variables."""
    return {
        "api_key": os.environ.get("OPENWEATHER_API_KEY"),
        "base_url": OPENWEATHER_BASE_URL,
    }


def _wind_direction(degrees: Optional[float]) -> Optional[str]:
    """Convert wind degrees to a 16-point compass direction."""
    if degrees is None:
        return None
    try:
        idx = int((float(degrees) + 11.25) / 22.5) % 16
        return WIND_DIRECTIONS[idx]
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert to float, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert to int, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def geocode_location(
    state: str,
    district: str,
    village: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Geocode a location using OpenWeatherMap Geocoding API.

    Tries village + district + state, then district + state, then state alone.

    Args:
        state: Indian state name
        district: Indian district name
        village: Optional village name

    Returns:
        Dictionary with lat, lon, name, state, country or None on failure.
    """
    config = _get_openweather_config()
    api_key = config["api_key"]

    if not api_key or api_key == "your_openweather_api_key_here":
        logger.warning("OpenWeatherMap API key not configured")
        return None

    queries: List[str] = []
    if village:
        queries.append(f"{village}, {district}, {state}, IN")
    queries.append(f"{district}, {state}, IN")
    queries.append(f"{state}, IN")

    for query in queries:
        cache_key = f"geo:{query}"
        if cache_key in _geocode_cache:
            return _geocode_cache[cache_key]

        try:
            response = requests.get(
                f"{OPENWEATHER_GEO_URL}/direct",
                params={"q": query, "limit": 1, "appid": api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 0:
                result = {
                    "lat": data[0].get("lat"),
                    "lon": data[0].get("lon"),
                    "name": data[0].get("name", village or district),
                    "state": data[0].get("state", state),
                    "country": data[0].get("country", "IN"),
                }
                _geocode_cache[cache_key] = result
                return result
        except Exception as e:
            logger.debug("Geocoding attempt failed for %s: %s", query, e)
            continue

    logger.warning("Could not geocode location: %s, %s, %s", village, district, state)
    return None


def fetch_7day_forecast(
    lat: float,
    lon: float,
) -> Optional[Dict[str, Any]]:
    """
    Fetch 7-day daily forecast from OpenWeather One Call API 3.0.

    Returns daily data including temperature, humidity, rainfall, wind speed,
    wind direction, and precipitation probability for each of the next 7 days.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Normalized forecast dictionary or None on failure.
    """
    config = _get_openweather_config()
    api_key = config["api_key"]

    if not api_key or api_key == "your_openweather_api_key_here":
        logger.warning("OpenWeatherMap API key not configured")
        return None

    cache_key = f"weather:{lat}:{lon}"
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]

    try:
        response = requests.get(
            f"{config['base_url']}/onecall",
            params={
                "lat": lat,
                "lon": lon,
                "exclude": "current,minutely,hourly,alerts",
                "units": "metric",
                "appid": api_key,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        daily_raw = data.get("daily", []) or []
        if not daily_raw:
            logger.error("OpenWeather One Call API returned no daily data")
            return None

        daily_forecast: List[Dict[str, Any]] = []
        for day in daily_raw[:7]:
            dt = _safe_int(day.get("dt"))
            date_str = ""
            if dt:
                try:
                    date_str = datetime.fromtimestamp(dt, tz=timezone.utc).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    date_str = ""

            temp = day.get("temp", {}) or {}
            feels_like = day.get("feels_like", {}) or {}
            weather_list = day.get("weather", []) or []
            weather_main = weather_list[0].get("main", "Unknown") if weather_list else "Unknown"
            weather_desc = weather_list[0].get("description", "Unknown") if weather_list else "Unknown"

            daily_forecast.append({
                "date": date_str,
                "dt": dt,
                "temp_min": _safe_float(temp.get("min")),
                "temp_max": _safe_float(temp.get("max")),
                "temp_day": _safe_float(temp.get("day")),
                "temp_night": _safe_float(temp.get("night")),
                "temp_morn": _safe_float(temp.get("morn")),
                "temp_eve": _safe_float(temp.get("eve")),
                "feels_like_day": _safe_float(feels_like.get("day")),
                "humidity": _safe_int(day.get("humidity")),
                "pressure": _safe_int(day.get("pressure")),
                "dew_point": _safe_float(day.get("dew_point")),
                "wind_speed": _safe_float(day.get("wind_speed")),
                "wind_deg": _safe_float(day.get("wind_deg")),
                "wind_direction": _wind_direction(_safe_float(day.get("wind_deg"))),
                "wind_gust": _safe_float(day.get("wind_gust")),
                "clouds": _safe_int(day.get("clouds")),
                "pop": _safe_float(day.get("pop")),  # probability of precipitation 0-1
                "rain": _safe_float(day.get("rain")),  # mm
                "snow": _safe_float(day.get("snow")),
                "uvi": _safe_float(day.get("uvi")),
                "condition": weather_main,
                "description": weather_desc,
                "sunrise": _safe_int(day.get("sunrise")),
                "sunset": _safe_int(day.get("sunset")),
            })

        result = {
            "lat": lat,
            "lon": lon,
            "timezone": data.get("timezone", "UTC"),
            "daily": daily_forecast,
            "source": "openweathermap",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        _weather_cache[cache_key] = result
        return result

    except requests.exceptions.Timeout:
        logger.error("OpenWeather One Call API request timed out")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("OpenWeather One Call API connection error")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("OpenWeatherMap API authentication failed")
        elif e.response.status_code == 429:
            logger.error("OpenWeatherMap API rate limit exceeded")
        else:
            logger.error("OpenWeatherMap API HTTP error: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error fetching weather: %s", e)
        return None
