"""
services/crop_duration_service.py - Crop season, duration, and growth progress calculation service

Reads crop season and duration data from CROP_SEASON_ONLY.csv and provides:
- Season and duration lookup by crop name
- Growth progress calculation based on sowing date
- Growth stage determination (Establishment, Vegetative, Flowering, Fruiting, Maturity)
- Estimated stage start/end dates
- Estimated maturity/harvesting date

All calculations are estimates based on crop duration data. Actual growth may vary.
"""

import csv
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to the crop season and duration CSV
CROP_SEASON_DURATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "CROP_SEASON_ONLY.csv",
)

# In-memory cache
_crop_duration_data: List[Dict[str, Any]] = []
_loaded = False


def _normalize_name(name: str) -> str:
    """Normalize crop name for matching (case-insensitive, whitespace-normalized)."""
    if not name:
        return ""
    return " ".join(name.strip().lower().split())


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert to int, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> Optional[str]:
    """Safely convert to string, returning None on failure."""
    if value is None or value == "":
        return None
    return str(value).strip()


def _load_csv() -> None:
    """Load crop season and duration data from CSV into memory."""
    global _crop_duration_data, _loaded

    if _loaded:
        return

    if not os.path.exists(CROP_SEASON_DURATION_PATH):
        logger.error("Crop season duration CSV not found at %s", CROP_SEASON_DURATION_PATH)
        # Do not mark as loaded so a later call retries if the file appears.
        return

    try:
        with open(CROP_SEASON_DURATION_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                crop = {
                    "category": _safe_str(row.get("category")),
                    "crop_name": _safe_str(row.get("crop_name")),
                    "season": _safe_str(row.get("season")),
                    "total_duration_days": _safe_int(row.get("total_duration_days")),
                    "establishment_duration_days": _safe_int(row.get("establishment_duration_days")),
                    "vegetative_duration_days": _safe_int(row.get("vegetative_duration_days")),
                    "flowering_duration_days": _safe_int(row.get("flowering_duration_days")),
                    "fruiting_grain_filling_duration_days": _safe_int(row.get("fruiting_grain_filling_duration_days")),
                    "maturity_harvesting_duration_days": _safe_int(row.get("maturity_harvesting_duration_days")),
                }
                if crop["crop_name"]:
                    _crop_duration_data.append(crop)

        _loaded = True
        logger.info("Loaded %d crop duration records from %s", len(_crop_duration_data), CROP_SEASON_DURATION_PATH)

    except Exception as e:
        logger.error("Failed to load crop season duration CSV: %s", e)
        # Do not mark as loaded so a later call retries after a temporary failure.
        return


def get_crop_duration(crop_name: str) -> Optional[Dict[str, Any]]:
    """Get crop season and duration data by crop name (case-insensitive match).

    Args:
        crop_name: Name of the crop to look up.

    Returns:
        Crop duration dictionary or None if not found.
    """
    _load_csv()
    normalized = _normalize_name(crop_name)
    for crop in _crop_duration_data:
        if _normalize_name(crop["crop_name"]) == normalized:
            return crop
    return None


def calculate_growth_progress(
    crop_duration: Optional[Dict[str, Any]],
    sowing_date_str: Optional[str],
) -> Dict[str, Any]:
    """Calculate estimated crop growth progress based on sowing date.

    Args:
        crop_duration: Crop duration dictionary from get_crop_duration().
        sowing_date_str: Sowing date as YYYY-MM-DD string, or None.

    Returns:
        Dictionary with progress percentage, elapsed days, remaining days,
        total duration, current stage, stage dates, and maturity date.
        Contains an 'available' boolean indicating if calculation is possible.
    """
    result: Dict[str, Any] = {
        "available": False,
        "message": "",
    }

    if not crop_duration:
        result["message"] = "Crop duration data is not available."
        return result

    total_duration = crop_duration.get("total_duration_days")
    if not total_duration or total_duration <= 0:
        result["message"] = "Total crop duration data is unavailable."
        return result

    today = date.today()
    sowing_date: Optional[date] = None

    if sowing_date_str:
        try:
            sowing_date = datetime.strptime(sowing_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            result["message"] = "Invalid sowing date format."
            return result
    else:
        # No sowing date provided - show upcoming sowing status
        result["available"] = True
        result["message"] = "Please enter a sowing date to calculate growth progress."
        result["total_duration_days"] = total_duration
        result["status"] = "upcoming"
        result["stage"] = "Not yet sown"
        result["stage_description"] = "Crop has not been sown yet. Enter the sowing date to track estimated growth progress."
        return result

    # Calculate elapsed and remaining days
    elapsed_days = (today - sowing_date).days
    remaining_days = total_duration - elapsed_days

    if elapsed_days < 0:
        # Future sowing date
        result["available"] = True
        result["total_duration_days"] = total_duration
        result["sowing_date"] = sowing_date_str
        result["status"] = "upcoming"
        result["stage"] = "Not yet sown"
        result["stage_description"] = f"Sowing date is {sowing_date_str}. Crop will be sown in {-elapsed_days} day(s)."
        result["elapsed_days"] = 0
        result["remaining_days"] = total_duration
        result["progress_percentage"] = 0.0
        result["expected_maturity_date"] = (sowing_date + timedelta(days=total_duration)).isoformat()
        result["stage_dates"] = _calculate_stage_dates(sowing_date, crop_duration)
        return result

    if elapsed_days >= total_duration:
        # Past maturity
        result["available"] = True
        result["total_duration_days"] = total_duration
        result["sowing_date"] = sowing_date_str
        result["status"] = "matured"
        result["stage"] = "Harvested / Matured"
        result["stage_description"] = f"The crop has completed its estimated {total_duration}-day cycle and should be ready for harvest."
        result["elapsed_days"] = total_duration
        result["remaining_days"] = 0
        result["progress_percentage"] = 100.0
        result["expected_maturity_date"] = (sowing_date + timedelta(days=total_duration)).isoformat()
        result["stage_dates"] = _calculate_stage_dates(sowing_date, crop_duration)
        return result

    # Normal calculation
    progress = (elapsed_days / total_duration) * 100
    progress = max(0.0, min(100.0, round(progress, 1)))
    remaining_days = max(0, remaining_days)

    # Determine current stage
    stage_info = _determine_stage(elapsed_days, crop_duration, sowing_date)

    result["available"] = True
    result["total_duration_days"] = total_duration
    result["sowing_date"] = sowing_date_str
    result["status"] = "growing"
    result["elapsed_days"] = elapsed_days
    result["remaining_days"] = remaining_days
    result["progress_percentage"] = progress
    result["stage"] = stage_info["stage"]
    result["stage_description"] = stage_info["description"]
    result["expected_maturity_date"] = (sowing_date + timedelta(days=total_duration)).isoformat()
    result["stage_dates"] = _calculate_stage_dates(sowing_date, crop_duration)

    return result


def _determine_stage(
    elapsed_days: int,
    crop_duration: Dict[str, Any],
    sowing_date: date,
) -> Dict[str, str]:
    """Determine the current growth stage based on elapsed days.

    Args:
        elapsed_days: Number of days since sowing.
        crop_duration: Crop duration dictionary.
        sowing_date: Sowing date.

    Returns:
        Dictionary with stage name and description.
    """
    establishment = crop_duration.get("establishment_duration_days") or 0
    vegetative = crop_duration.get("vegetative_duration_days") or 0
    flowering = crop_duration.get("flowering_duration_days") or 0
    fruiting = crop_duration.get("fruiting_grain_filling_duration_days") or 0
    maturity = crop_duration.get("maturity_harvesting_duration_days") or 0

    cumulative_est = establishment
    cumulative_veg = cumulative_est + vegetative
    cumulative_flow = cumulative_veg + flowering
    cumulative_fruit = cumulative_flow + fruiting

    if elapsed_days < cumulative_est:
        return {
            "stage": "Establishment",
            "description": f"Crop is in the establishment phase (day {elapsed_days + 1} of ~{cumulative_est}).",
        }
    elif elapsed_days < cumulative_veg:
        days_in_stage = elapsed_days - cumulative_est + 1
        return {
            "stage": "Vegetative Growth",
            "description": f"Crop is in the vegetative growth phase (day {days_in_stage} of ~{vegetative}).",
        }
    elif elapsed_days < cumulative_flow:
        days_in_stage = elapsed_days - cumulative_veg + 1
        return {
            "stage": "Flowering",
            "description": f"Crop is in the flowering phase (day {days_in_stage} of ~{flowering}).",
        }
    elif elapsed_days < cumulative_fruit:
        days_in_stage = elapsed_days - cumulative_flow + 1
        return {
            "stage": "Fruiting / Grain Filling",
            "description": f"Crop is in the fruiting/grain-filling phase (day {days_in_stage} of ~{fruiting}).",
        }
    else:
        days_in_stage = elapsed_days - cumulative_fruit + 1
        return {
            "stage": "Maturity / Harvesting",
            "description": f"Crop is in the maturity/harvesting phase (day {days_in_stage} of ~{maturity}).",
        }


def _calculate_stage_dates(
    sowing_date: date,
    crop_duration: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Calculate estimated start and end dates for each growth stage.

    Args:
        sowing_date: Sowing date.
        crop_duration: Crop duration dictionary.

    Returns:
        List of stage dictionaries with name, duration, start_date, end_date.
    """
    establishment = crop_duration.get("establishment_duration_days") or 0
    vegetative = crop_duration.get("vegetative_duration_days") or 0
    flowering = crop_duration.get("flowering_duration_days") or 0
    fruiting = crop_duration.get("fruiting_grain_filling_duration_days") or 0
    maturity = crop_duration.get("maturity_harvesting_duration_days") or 0

    stages = []
    current_date = sowing_date

    stage_defs = [
        ("Establishment", establishment),
        ("Vegetative Growth", vegetative),
        ("Flowering", flowering),
        ("Fruiting / Grain Filling", fruiting),
        ("Maturity / Harvesting", maturity),
    ]

    for stage_name, duration in stage_defs:
        if not duration or duration <= 0:
            continue
        end_date = current_date + timedelta(days=duration - 1)
        stages.append({
            "name": stage_name,
            "duration_days": duration,
            "start_date": current_date.isoformat(),
            "end_date": end_date.isoformat(),
        })
        current_date = end_date + timedelta(days=1)

    return stages


# Convenience function for the route
def get_crop_season_info(crop_name: str) -> Optional[Dict[str, Any]]:
    """Get simplified season info for a crop."""
    return get_crop_duration(crop_name)
