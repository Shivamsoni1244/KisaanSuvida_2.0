"""
services/weather_suitability_service.py - Centralized weather suitability calculation service

Single source of truth for all weather-based crop suitability calculations:

- Temperature classification per hourly reading (GOOD / SUSTAINABLE / MARGINAL / BAD / UNKNOWN)
- Daily aggregation (average of hourly scores)
- Weekly aggregation (sum of daily scores, capped at 100)
- Soil pH suitability analysis (GOOD / MARGINAL / BAD / UNKNOWN)
- Consistent API response contract for frontend consumption

All reference values (temperature and pH ranges) are loaded dynamically from
TEMPERATURE_DATASET_optimal_temp_ranges_filled.csv via crop_data_service.
No crop-specific values are hardcoded.
"""

import logging
from typing import Any, Dict, List, Optional

from services.crop_data_service import get_crop_by_name

logger = logging.getLogger(__name__)

# Score contributions per classification
SCORE_GOOD = 100.0 / 7.0
SCORE_SUSTAINABLE = 10.0
SCORE_MARGINAL = 6.0
SCORE_BAD = 0.0

# pH marginal threshold (units outside recommended range)
PH_MARGINAL_THRESHOLD = 0.5

# Temperature marginal threshold (degrees outside sustainable limits)
TEMP_MARGINAL_THRESHOLD = 2.0

# Overall status thresholds
STATUS_FAVOURABLE = 80.0
STATUS_MODERATE = 60.0
STATUS_MARGINAL = 40.0


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert to float, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Temperature classification (single hourly reading)
# ---------------------------------------------------------------------------
def classify_temperature(
    temp: Optional[float],
    crop: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify a single hourly temperature reading against crop reference ranges.

    Classification rules:
      GOOD:    best_low_temp <= temp <= best_high_temp  (score 100/7)
      SUSTAINABLE: low_temp <= temp < best_low_temp
                   OR best_high_temp < temp <= max_temp  (score 10)
      MARGINAL:  1-2°C above max_temp, or 1-2°C below low_temp  (score 6)
      BAD:       > 2°C above max_temp, or > 2°C below low_temp  (score 0)
      UNKNOWN:   temp is None or reference values unavailable

    Boundary conditions are implemented without overlapping categories.

    Args:
        temp: Hourly temperature reading (Celsius), or None if missing.
        crop: Crop dictionary with best_low_temp, best_high_temp, low_temp, max_temp.

    Returns:
        Dict with classification, score, and explanation.
    """
    best_low = _safe_float(crop.get("best_low_temp"))
    best_high = _safe_float(crop.get("best_high_temp"))
    low = _safe_float(crop.get("low_temp"))
    max_t = _safe_float(crop.get("max_temp"))

    # Missing reading -> UNKNOWN
    if temp is None:
        return {
            "classification": "UNKNOWN",
            "score": None,
            "temperature": None,
            "explanation": "No temperature reading available.",
        }

    # Missing or invalid reference values -> UNKNOWN
    if best_low is None or best_high is None or low is None or max_t is None:
        return {
            "classification": "UNKNOWN",
            "score": None,
            "temperature": temp,
            "explanation": "Crop temperature reference data is unavailable.",
        }

    # GOOD: inside optimal range (inclusive boundaries)
    if best_low <= temp <= best_high:
        return {
            "classification": "GOOD",
            "score": SCORE_GOOD,
            "temperature": temp,
            "explanation": (
                f"Temperature {temp}°C is within the optimal range "
                f"({best_low}–{best_high}°C)."
            ),
        }

    # SUSTAINABLE: inside sustainable range but outside optimal range
    if low <= temp < best_low:
        return {
            "classification": "SUSTAINABLE",
            "score": SCORE_SUSTAINABLE,
            "temperature": temp,
            "explanation": (
                f"Temperature {temp}°C is within sustainable limits "
                f"({low}–{best_low}°C) but outside the optimal range."
            ),
        }
    if best_high < temp <= max_t:
        return {
            "classification": "SUSTAINABLE",
            "score": SCORE_SUSTAINABLE,
            "temperature": temp,
            "explanation": (
                f"Temperature {temp}°C is within sustainable limits "
                f"({best_high}–{max_t}°C) but outside the optimal range."
            ),
        }

    # MARGINAL: 1–2°C outside sustainable limits
    if max_t < temp <= max_t + TEMP_MARGINAL_THRESHOLD:
        diff = temp - max_t
        return {
            "classification": "MARGINAL",
            "score": SCORE_MARGINAL,
            "temperature": temp,
            "explanation": (
                f"Temperature {temp}°C is {diff:.1f}°C above the maximum sustainable "
                f"limit ({max_t}°C)."
            ),
        }
    if low - TEMP_MARGINAL_THRESHOLD <= temp < low:
        diff = low - temp
        return {
            "classification": "MARGINAL",
            "score": SCORE_MARGINAL,
            "temperature": temp,
            "explanation": (
                f"Temperature {temp}°C is {diff:.1f}°C below the minimum sustainable "
                f"limit ({low}°C)."
            ),
        }

    # BAD: more than 2°C outside sustainable limits
    return {
        "classification": "BAD",
        "score": SCORE_BAD,
        "temperature": temp,
        "explanation": (
            f"Temperature {temp}°C is more than {TEMP_MARGINAL_THRESHOLD}°C outside "
            f"the sustainable limits ({low}–{max_t}°C)."
        ),
    }


# ---------------------------------------------------------------------------
# Soil pH classification
# ---------------------------------------------------------------------------
def classify_ph(
    farmer_ph: Optional[float],
    crop: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify farmer's soil pH against crop reference pH range.

    Classification:
      GOOD:    ph_min <= ph <= ph_max
      MARGINAL: ph_min - 0.5 <= ph < ph_min OR ph_max < ph <= ph_max + 0.5
      BAD:     ph < ph_min - 0.5 OR ph > ph_max + 0.5
      UNKNOWN: pH not supplied or reference values unavailable

    Args:
        farmer_ph: Farmer's measured soil pH (0–14), or None if not supplied.
        crop: Crop dictionary with ph_min, ph_max.

    Returns:
        Dict with status, crop_min, crop_max, farmer_ph, difference, message.
    """
    ph_min = _safe_float(crop.get("ph_min"))
    ph_max = _safe_float(crop.get("ph_max"))

    # Missing farmer pH -> UNKNOWN
    if farmer_ph is None:
        return {
            "status": "UNKNOWN",
            "farmer_ph": None,
            "crop_min": ph_min,
            "crop_max": ph_max,
            "difference": None,
            "message": "Soil pH was not provided. pH suitability cannot be assessed.",
            "explanation": "Please enter your soil pH value for pH suitability analysis.",
        }

    # Missing or invalid reference values -> UNKNOWN
    if ph_min is None or ph_max is None:
        return {
            "status": "UNKNOWN",
            "farmer_ph": farmer_ph,
            "crop_min": ph_min,
            "crop_max": ph_max,
            "difference": None,
            "message": "Crop pH reference data is unavailable.",
            "explanation": "Cannot assess pH suitability without crop reference data.",
        }

    # Validate farmer pH is in physical range
    if farmer_ph < 0 or farmer_ph > 14:
        return {
            "status": "UNKNOWN",
            "farmer_ph": farmer_ph,
            "crop_min": ph_min,
            "crop_max": ph_max,
            "difference": None,
            "message": f"Soil pH {farmer_ph} is outside the physically accepted range (0–14).",
            "explanation": "Please enter a valid soil pH value between 0 and 14.",
        }

    # GOOD: within recommended range
    if ph_min <= farmer_ph <= ph_max:
        return {
            "status": "GOOD",
            "farmer_ph": farmer_ph,
            "crop_min": ph_min,
            "crop_max": ph_max,
            "difference": 0.0,
            "message": f"Soil pH {farmer_ph} is within the recommended range ({ph_min}–{ph_max}).",
            "explanation": (
                f"Your soil pH ({farmer_ph}) fits the crop's preferred range "
                f"({ph_min}–{ph_max})."
            ),
        }

    # Calculate distance from range
    if farmer_ph < ph_min:
        difference = ph_min - farmer_ph
    else:
        difference = farmer_ph - ph_max

    # MARGINAL: within 0.5 pH units outside range
    if difference <= PH_MARGINAL_THRESHOLD:
        direction = "below" if farmer_ph < ph_min else "above"
        return {
            "status": "MARGINAL",
            "farmer_ph": farmer_ph,
            "crop_min": ph_min,
            "crop_max": ph_max,
            "difference": round(difference, 2),
            "message": (
                f"Soil pH {farmer_ph} is {difference:.1f} pH units {direction} the "
                f"recommended range ({ph_min}–{ph_max})."
            ),
            "explanation": (
                f"Your soil pH ({farmer_ph}) is close to the edge of the supported range. "
                f"Consider soil amendment if possible."
            ),
        }

    # BAD: more than 0.5 pH units outside range
    direction = "below" if farmer_ph < ph_min else "above"
    return {
        "status": "BAD",
        "farmer_ph": farmer_ph,
        "crop_min": ph_min,
        "crop_max": ph_max,
        "difference": round(difference, 2),
        "message": (
            f"Soil pH {farmer_ph} is {difference:.1f} pH units {direction} the "
            f"recommended range ({ph_min}–{ph_max})."
        ),
        "explanation": (
            f"Your soil pH ({farmer_ph}) is substantially outside the crop's "
            f"recommended range ({ph_min}–{ph_max}). Soil amendment is recommended."
        ),
    }


# ---------------------------------------------------------------------------
# Daily temperature analysis
# ---------------------------------------------------------------------------
def analyse_daily(
    day_readings: List[Dict[str, Any]],
    crop: Dict[str, Any],
) -> Dict[str, Any]:
    """Analyse temperature suitability for a single day.

    Classifies each available hourly reading and computes the daily score as
    the average of the available hourly classification scores.

    A day with no valid temperature readings is marked UNKNOWN and excluded
    from the weekly score.

    Args:
        day_readings: List of hourly reading dicts (each with optional 'temp' key).
        crop: Crop dictionary with temperature reference values.

    Returns:
        Dict with daily assessment including classification counts and score.
    """
    classifications = {"GOOD": 0, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 0}
    slot_assessments: List[Dict[str, Any]] = []
    scores: List[float] = []

    for reading in day_readings:
        temp = _safe_float(reading.get("temp"))
        result = classify_temperature(temp, crop)
        classification = result["classification"]
        classifications[classification] += 1

        slot_assessments.append({
            "time": reading.get("time_label", "Unknown"),
            "hour": reading.get("hour"),
            "temperature": temp,
            "classification": classification,
            "score": result["score"],
            "explanation": result["explanation"],
        })

        if result["score"] is not None:
            scores.append(result["score"])

    valid_count = classifications["GOOD"] + classifications["SUSTAINABLE"] + classifications["MARGINAL"] + classifications["BAD"]

    if valid_count == 0:
        # No valid readings -> UNKNOWN day, excluded from weekly score
        return {
            "date": day_readings[0].get("date", "") if day_readings else "",
            "status": "UNKNOWN",
            "label": "No Data",
            "score": None,
            "classifications": classifications,
            "valid_readings": 0,
            "total_readings": len(day_readings),
            "slots": slot_assessments,
            "explanation": "No valid temperature readings for this day.",
        }

    daily_score = sum(scores) / len(scores)

    # Determine day-level label
    if classifications["BAD"] > 0:
        day_status = "BAD"
        day_label = "Unfavourable"
    elif classifications["MARGINAL"] > 0:
        day_status = "MARGINAL"
        day_label = "Marginal"
    elif classifications["SUSTAINABLE"] > 0:
        day_status = "SUSTAINABLE"
        day_label = "Sustainable"
    else:
        day_status = "GOOD"
        day_label = "Good"

    return {
        "date": day_readings[0].get("date", "") if day_readings else "",
        "status": day_status,
        "label": day_label,
        "score": round(daily_score, 2),
        "classifications": classifications,
        "valid_readings": valid_count,
        "total_readings": len(day_readings),
        "slots": slot_assessments,
        "explanation": (
            f"{classifications['GOOD']} good, {classifications['SUSTAINABLE']} sustainable, "
            f"{classifications['MARGINAL']} marginal, {classifications['BAD']} bad reading(s)."
        ),
    }


# ---------------------------------------------------------------------------
# Weekly aggregation
# ---------------------------------------------------------------------------
def analyse_weekly(
    daily_assessments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate daily assessments into a weekly weather suitability score.

    weekly_score = sum of daily scores for valid days only, capped at 100.
    UNKNOWN days are excluded from the score.

    Args:
        daily_assessments: List of daily assessment dicts from analyse_daily().

    Returns:
        Dict with weekly score, status, counts, and data availability info.
    """
    day_status_counts = {"GOOD": 0, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 0}
    valid_days = 0
    daily_scores: List[float] = []
    daily_details: List[Dict[str, Any]] = []

    for day in daily_assessments:
        day_status = (day.get("status", "UNKNOWN") or "UNKNOWN").upper()
        day_status_counts[day_status] += 1

        if day_status != "UNKNOWN" and day.get("score") is not None:
            valid_days += 1
            daily_scores.append(day["score"])

        daily_details.append({
            "date": day.get("date", ""),
            "status": day.get("status", "UNKNOWN"),
            "label": day.get("label", "Unknown"),
            "score": day.get("score"),
            "valid_readings": day.get("valid_readings", 0),
            "total_readings": day.get("total_readings", 0),
            "classifications": day.get("classifications", {}),
            "slots": day.get("slots", []),
        })

    if valid_days == 0:
        weekly_score = None
        status = "INSUFFICIENT_DATA"
        label = "Insufficient Data"
        explanation = "No valid weather data available for any day. Cannot determine suitability."
    else:
        raw_score = sum(daily_scores)
        weekly_score = min(round(raw_score, 2), 100.0)

        if weekly_score >= STATUS_FAVOURABLE:
            status = "FAVOURABLE"
            label = "Favourable"
        elif weekly_score >= STATUS_MODERATE:
            status = "MODERATE"
            label = "Moderately Favourable"
        elif weekly_score >= STATUS_MARGINAL:
            status = "MARGINAL"
            label = "Marginal"
        else:
            status = "UNFAVOURABLE"
            label = "Unfavourable"

        good_days = day_status_counts["GOOD"]
        sustainable_days = day_status_counts["SUSTAINABLE"]
        marginal_days = day_status_counts["MARGINAL"]
        bad_days = day_status_counts["BAD"]
        unknown_days = day_status_counts["UNKNOWN"]

        explanation = (
            f"Weekly score {weekly_score}/100 based on {valid_days} valid day(s): "
            f"{good_days} good, {sustainable_days} sustainable, "
            f"{marginal_days} marginal, {bad_days} bad, {unknown_days} unknown day(s)."
        )

    return {
        "weekly_score": weekly_score,
        "status": status,
        "label": label,
        "valid_days": valid_days,
        "total_days": len(daily_assessments),
        "classification_counts": {
            "good": day_status_counts["GOOD"],
            "sustainable": day_status_counts["SUSTAINABLE"],
            "marginal": day_status_counts["MARGINAL"],
            "bad": day_status_counts["BAD"],
            "unknown": day_status_counts["UNKNOWN"],
        },
        "daily_assessments": daily_details,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Main suitability analysis
# ---------------------------------------------------------------------------
def analyse_suitability(
    crop_name: str,
    hourly_readings_by_day: List[List[Dict[str, Any]]],
    farmer_ph: Optional[float],
) -> Dict[str, Any]:
    """Run the complete weather suitability analysis for a crop.

    This is the central entry point. It loads crop reference data from the CSV
    dataset, classifies every hourly temperature reading, aggregates daily and
    weekly scores, and performs soil pH analysis.

    Args:
        crop_name: Name of the crop to analyse.
        hourly_readings_by_day: List of days, each containing a list of hourly
            reading dicts with at least a 'temp' key.
        farmer_ph: Farmer's measured soil pH (0–14), or None if not supplied.

    Returns:
        Dict with the full API response contract:
        {
            "success": bool,
            "crop": {...},
            "weather_analysis": {...},
            "ph_analysis": {...},
            "error": str (only on failure)
        }
    """
    # Load crop reference data from CSV
    crop = get_crop_by_name(crop_name)
    if not crop:
        return {
            "success": False,
            "error": "crop_not_found",
            "message": f"Crop '{crop_name}' not found in the reference dataset.",
        }

    # Validate crop reference values
    required_fields = ["best_low_temp", "best_high_temp", "low_temp", "max_temp", "ph_min", "ph_max"]
    missing_fields = [f for f in required_fields if _safe_float(crop.get(f)) is None]
    if missing_fields:
        return {
            "success": False,
            "error": "invalid_crop_data",
            "message": f"Crop '{crop_name}' has missing or invalid reference values: {', '.join(missing_fields)}.",
        }

    crop_info = {
        "name": crop.get("crop_name", crop_name),
        "best_low_temp": _safe_float(crop.get("best_low_temp")),
        "best_high_temp": _safe_float(crop.get("best_high_temp")),
        "low_temp": _safe_float(crop.get("low_temp")),
        "max_temp": _safe_float(crop.get("max_temp")),
        "ph_min": _safe_float(crop.get("ph_min")),
        "ph_max": _safe_float(crop.get("ph_max")),
    }

    # Daily temperature analysis
    daily_assessments = []
    for day_readings in hourly_readings_by_day:
        daily_assessments.append(analyse_daily(day_readings, crop_info))

    # Weekly aggregation
    weather_analysis = analyse_weekly(daily_assessments)

    # pH analysis
    ph_analysis = classify_ph(farmer_ph, crop_info)

    return {
        "success": True,
        "crop": crop_info,
        "weather_analysis": weather_analysis,
        "ph_analysis": ph_analysis,
    }
