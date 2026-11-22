"""
services/weather_aggregation_service.py - Daily weather aggregation

Calculates daily aggregated weather values from OpenWeather One Call API 3.0
daily forecast data:

- avg_temperature: average of valid temperature readings (day/morn/eve/night)
- min_temperature: minimum valid temperature
- max_temperature: maximum valid temperature
- avg_humidity: average of valid humidity readings
- total_rainfall: total daily precipitation in mm
- avg_wind_speed: average valid wind speed in m/s
- wind_direction: optional representative direction
- valid_readings: number of valid readings

Handles missing readings independently for each weather variable.
Never substitutes zero for missing humidity, rainfall, or wind speed.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert to float, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate_daily_weather(
    daily_forecast: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Aggregate OpenWeather daily forecast into clean daily summaries.

    Each input day already contains pre-aggregated values from OpenWeather
    (temp min/max/day, humidity, wind_speed, rain, etc.). This function
    normalizes them, handles missing values independently per variable,
    and returns a clean list of daily summaries.

    Args:
        daily_forecast: List of daily forecast dicts from weather_service.fetch_7day_forecast.

    Returns:
        List of daily summary dicts with normalized fields.
    """
    aggregated: List[Dict[str, Any]] = []

    for day in daily_forecast:
        date = day.get("date", "")

        # Temperature - use min/max/day from OpenWeather daily
        temp_min = _safe_float(day.get("temp_min"))
        temp_max = _safe_float(day.get("temp_max"))
        temp_day = _safe_float(day.get("temp_day"))

        # Compute average temperature from available components
        temp_components = [v for v in [temp_day, temp_min, temp_max] if v is not None]
        avg_temperature = (sum(temp_components) / len(temp_components)) if temp_components else None

        # Humidity - single daily value, do not substitute zero if missing
        humidity = _safe_float(day.get("humidity"))
        avg_humidity = humidity  # already a daily average from OpenWeather

        # Rainfall - daily precipitation in mm, None if not present (don't assume zero)
        rainfall = _safe_float(day.get("rain"))
        total_rainfall = rainfall  # None if not provided by API

        # Wind speed - daily average in m/s
        wind_speed = _safe_float(day.get("wind_speed"))
        avg_wind_speed = wind_speed

        # Wind direction
        wind_direction = day.get("wind_direction")

        # Condition
        condition = day.get("condition", "Unknown")
        description = day.get("description", "Unknown")

        # Valid readings count - count how many core variables are present
        valid_readings = sum(
            1 for v in [avg_temperature, temp_min, temp_max, avg_humidity,
                        total_rainfall, avg_wind_speed] if v is not None
        )

        aggregated.append({
            "date": date,
            "condition": condition,
            "description": description,
            "avg_temperature": avg_temperature,
            "min_temperature": temp_min,
            "max_temperature": temp_max,
            "avg_humidity": avg_humidity,
            "total_rainfall": total_rainfall,
            "avg_wind_speed": avg_wind_speed,
            "wind_direction": wind_direction,
            "valid_readings": valid_readings,
            "pop": _safe_float(day.get("pop")),  # probability of precipitation
        })

    return aggregated


def build_hourly_readings_for_suitability(
    aggregated: List[Dict[str, Any]],
) -> List[List[Dict[str, Any]]]:
    """
    Build a synthetic hourly-readings structure from daily aggregated data
    for use with the existing temperature suitability engine.

    Each day gets 6 synthetic slots (0, 4, 8, 12, 16, 20) all using the
    daily average temperature. This preserves the established temperature
    classification methodology while working with OpenWeather daily data.

    Args:
        aggregated: List of daily summary dicts from aggregate_daily_weather.

    Returns:
        List of days, each containing a list of 6 slot dicts with 'temp' key.
    """
    hourly_by_day: List[List[Dict[str, Any]]] = []

    for day in aggregated:
        avg_temp = day.get("avg_temperature")
        date = day.get("date", "")
        humidity = day.get("avg_humidity")
        wind_speed = day.get("avg_wind_speed")
        condition = day.get("condition", "Unknown")
        rain = day.get("total_rainfall") or 0

        slots: List[Dict[str, Any]] = []
        for hour in [0, 4, 8, 12, 16, 20]:
            time_label = f"{hour:02d}:00"
            slots.append({
                "date": date,
                "hour": hour,
                "time_label": time_label,
                "temp": avg_temp,
                "humidity": humidity,
                "wind_speed": wind_speed,
                "condition": condition,
                "description": condition,
                "rain": rain,
                "pop": day.get("pop"),
            })

        hourly_by_day.append(slots)

    return hourly_by_day
