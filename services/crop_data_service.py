"""
services/crop_data_service.py - Crop data loading and search for Crop Suitability Analysis

Primary crop list is loaded from CROP_SEASON_ONLY.csv (160 crop records with
category and crop_name). Temperature/pH reference values are enriched from
TEMPERATURE_DATASET_optimal_temp_ranges_filled.csv, matched by normalized crop name.

Provides:
- Load all crops
- Get categories
- Get crops by category
- Search crops by name (partial match, case-insensitive)
- Get single crop by name
"""

import csv
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to the primary crop list CSV (category + crop_name for all crops)
CROP_SEASON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "CROP_SEASON_ONLY.csv",
)

# Path to the temperature reference dataset CSV (ph/temp reference values only)
TEMPERATURE_DATASET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "TEMPERATURE_DATASET_optimal_temp_ranges_filled.csv",
)

# In-memory cache of loaded crop data
_crops: List[Dict[str, Any]] = []
_categories: List[str] = []
_loaded = False


def _normalize_name(name: str) -> str:
    """Normalize a crop name for matching (case-insensitive, whitespace-collapsed)."""
    if not name:
        return ""
    return " ".join(str(name).strip().lower().split())


def _parse_float(value: Any) -> Optional[float]:
    """Parse a float value, returning None for empty or invalid strings."""
    if value is None:
        return None
    try:
        v = float(str(value).strip())
        return v
    except (TypeError, ValueError):
        return None


def _load_csv() -> None:
    """Load crop data from CROP_SEASON_ONLY.csv, enriched with temperature reference values."""
    global _crops, _categories, _loaded

    if _loaded and _crops:
        return  # Already loaded successfully

    # 1. Load primary crop list from CROP_SEASON_ONLY.csv
    primary: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(CROP_SEASON_PATH):
        logger.error("Crop season CSV not found at %s", CROP_SEASON_PATH)
    else:
        try:
            with open(CROP_SEASON_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("crop_name", "").strip()
                    if not name:
                        continue
                    norm = _normalize_name(name)
                    primary[norm] = {
                        "category": row.get("category", "").strip(),
                        "crop_name": name,
                    }
            logger.info("Loaded %d primary crop records from %s", len(primary), CROP_SEASON_PATH)
        except Exception as e:
            logger.error("Failed to load crop season CSV: %s", e)

    # 2. Load temperature reference dataset as lookup keyed by normalized crop name
    reference: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(TEMPERATURE_DATASET_PATH):
        logger.error("Temperature dataset CSV not found at %s", TEMPERATURE_DATASET_PATH)
    else:
        try:
            with open(TEMPERATURE_DATASET_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("crop_name", "").strip()
                    if not name:
                        continue
                    norm = _normalize_name(name)
                    reference[norm] = {
                        "ph_min": _parse_float(row.get("ph_min")),
                        "ph_max": _parse_float(row.get("ph_max")),
                        "low_temp": _parse_float(row.get("low_temp")),
                        "max_temp": _parse_float(row.get("max_temp")),
                        "best_low_temp": _parse_float(row.get("best_low_temp")),
                        "best_high_temp": _parse_float(row.get("best_high_temp")),
                    }
            logger.info("Loaded %d temperature reference records from %s", len(reference), TEMPERATURE_DATASET_PATH)
        except Exception as e:
            logger.error("Failed to load temperature dataset: %s", e)

    # 3. Merge primary list with reference values by normalized crop name.
    # Missing reference values do not prevent a crop from appearing.
    merged: List[Dict[str, Any]] = []
    for norm, base in primary.items():
        crop = dict(base)
        ref = reference.get(norm, {})
        crop.update({
            "ph_min": ref.get("ph_min"),
            "ph_max": ref.get("ph_max"),
            "low_temp": ref.get("low_temp"),
            "max_temp": ref.get("max_temp"),
            "best_low_temp": ref.get("best_low_temp"),
            "best_high_temp": ref.get("best_high_temp"),
        })
        merged.append(crop)

    # Sort by crop_name for stable ordering
    merged.sort(key=lambda c: c["crop_name"].lower())

    # Build unique sorted category list
    categories = sorted(set(c["category"] for c in merged if c["category"]))

    _crops = merged
    _categories = categories
    _loaded = True

    logger.info(
        "Loaded %d crops across %d categories from %s (temperature ref: %s records)",
        len(_crops), len(_categories), CROP_SEASON_PATH, len(reference),
    )


def get_all_crops() -> List[Dict[str, Any]]:
    """Return all loaded crops."""
    _load_csv()
    return list(_crops)


def get_categories() -> List[str]:
    """Return sorted list of unique crop categories."""
    _load_csv()
    return list(_categories)


def get_crops_by_category(category: str) -> List[Dict[str, Any]]:
    """Return crops filtered by category name."""
    _load_csv()
    return [c for c in _crops if c["category"] == category]


def search_crops(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Search crops by name (partial, case-insensitive).

    Args:
        query: Search string
        limit: Maximum results to return

    Returns:
        List of crop dictionaries matching the query
    """
    _load_csv()
    q = query.strip().lower()
    q_norm = _normalize_name(q)
    results = [
        c for c in _crops
        if q in c["crop_name"].lower() or q_norm in _normalize_name(c["crop_name"])
    ]
    return results[:limit]


def get_crop_by_name(crop_name: str) -> Optional[Dict[str, Any]]:
    """Get a single crop by exact name (case-insensitive, whitespace-normalized)."""
    _load_csv()
    target = _normalize_name(crop_name)
    for c in _crops:
        if _normalize_name(c["crop_name"]) == target:
            return c
    return None
