"""
services/suitability_engine.py - Agricultural Crop Recommendation Engine

Provides deterministic, rule-based crop suitability calculations using:
- ML crop predictions from crop_engine.py (optional)
- Real-time weather data from weather_engine.py
- Farmer's farm profile data
- Crop database (crop_service.py)

All calculations are deterministic and traceable. No ML model is used for
the final suitability score - only for initial crop ranking.

Scoring weights (configurable):
- Soil compatibility: 20%
- Temperature suitability: 20%
- Rainfall suitability: 15%
- Season suitability: 15%
- Regional compatibility: 10%
- Irrigation suitability: 10%
- Humidity suitability: 5%
- Wind suitability: 5%

Total: 100%
"""

import logging
from typing import Any, Dict, List, Optional

from services.crop_service import (
    get_crop_by_id,
    get_crop_regional_suitability,
    save_recommendation_history as insert_crop_recommendation_history,
    get_crop_recommendation_history,
)
from services.weather_engine import (
    get_current_weather,
)

logger = logging.getLogger(__name__)

# Configurable weights for suitability calculation
SUITABILITY_WEIGHTS = {
    "soil": 0.20,
    "temperature": 0.20,
    "rainfall": 0.15,
    "season": 0.15,
    "region": 0.10,
    "irrigation": 0.10,
    "humidity": 0.05,
    "wind": 0.05,
}

# Crop season mapping for seasonal compatibility
SEASON_MONTHS = {
    "Kharif": [6, 7, 8, 9, 10],  # June-October (monsoon crops)
    "Rabi": [11, 12, 1, 2, 3],   # November-March (winter crops)
    "Zaid": [3, 4, 5],           # April-May (summer crops)
    "Perennial": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # Year-round
}


def _range_score(val: float, low: float, high: float) -> float:
    """
    Calculate a 0-100 score for how well a value fits within an optimal range.
    
    Returns 100 if within range, decreasing linearly outside the range.
    Never goes below 0.
    """
    if low <= val <= high:
        return 100.0
    diff = min(abs(val - low), abs(val - high))
    span = max(1.0, high - low)
    penalty = (diff / span) * 50  # Up to 50 point penalty outside range
    return max(0.0, 100.0 - penalty)


def _season_match_score(season: str, crop_seasons: List[str]) -> float:
    """
    Calculate season compatibility score (0-100).
    
    Returns 100 for exact match, 60 for adjacent season compatibility,
    30 for no match.
    """
    if season in crop_seasons:
        return 100.0
    # Adjacent season mapping for partial compatibility
    adjacent = {
        "Kharif": ["Rabi", "Zaid"],
        "Rabi": ["Kharif", "Zaid"],
        "Zaid": ["Kharif", "Rabi"],
    }
    for cs in crop_seasons:
        if cs in adjacent.get(season, []):
            return 60.0
    return 30.0


def _irrigation_match_score(crop_water_req: str, farmer_irrigation: str) -> float:
    """
    Calculate irrigation compatibility score (0-100).
    
    Matches crop water requirement with farmer's irrigation availability.
    """
    if crop_water_req == "High":
        if "Rainfed" in farmer_irrigation:
            return 40.0  # High water crop with rainfed = poor match
        return 95.0  # Canal/Borewell/Drip = good match
    elif crop_water_req == "Medium":
        if "Rainfed" in farmer_irrigation:
            return 70.0  # Medium water crop with rainfed = moderate match
        return 90.0
    else:  # Low
        if "Rainfed" in farmer_irrigation:
            return 95.0  # Low water crop with rainfed = excellent match
        return 90.0


def _regional_match_score(state: str, crop_states: List[str]) -> float:
    """
    Calculate regional compatibility score (0-100).
    
    Returns 100 if state is in crop's known states, 70 otherwise.
    No hardcoded Punjab bias - every state is treated equally.
    """
    if state in crop_states:
        return 100.0
    return 70.0


def calculate_suitability(
    state: str,
    district: str,
    season: str,
    soil_type: str,
    n: float,
    p: float,
    k: float,
    ph: float,
    irrigation: str,
    crop_data: Dict[str, Any],
    weather_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calculate hybrid suitability for a single crop based on farm parameters.
    
    Args:
        state: Farmer's state
        district: Farmer's district
        season: Agricultural season
        soil_type: Soil type
        n: Nitrogen value
        p: Phosphorus value
        k: Potassium value
        ph: Soil pH
        irrigation: Irrigation availability
        crop_data: Crop database record
        weather_data: Weather data dictionary
        
    Returns:
        Dictionary with component scores and overall hybrid score
    """
    scored_crops = []
    
    # Build farm context for regional match
    farm_context = {
        "state": state,
        "district": district,
        "season": season,
        "soil_type": soil_type,
        "n": n,
        "p": p,
        "k": k,
        "ph": ph,
        "irrigation": irrigation,
    }
    
    # Get weather data if not provided
    if not weather_data:
        weather_data = get_current_weather(state, district)
    
    # Calculate scores for each crop
    scored_crops = []
    
    for crop_data in crops:
        scored_crop = _calculate_single_crop_suitability(
            crop_data=crop_data,
            farm_context=farm_context,
            weather_data=weather_data,
        )
        scored_crops.append(scored_crop)
    
    # Sort by hybrid suitability descending, then by ml_probability as tiebreaker
    scored_crops.sort(key=lambda x: (x.get("hybrid_suitability", 0), x.get("ml_probability", 0)), reverse=True)
    
    top_crop = scored_crops[0] if scored_crops else None
    alternatives = scored_crops[1:3] if len(scored_crops) > 1 else []
    
    return {
        "top_crop": top_crop,
        "alternatives": alternatives,
        "all_ranked": scored_crops,
        "farm_context": {
            "state": state,
            "district": district,
            "season": season,
            "soil_type": soil_type,
            "n": n,
            "p": p,
            "k": k,
            "ph": ph,
            "irrigation": irrigation,
        }
    }


def _calculate_single_crop_suitability(
    crop_data: Dict[str, Any],
    farm_context: Dict[str, Any],
    weather_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calculate suitability score for a single crop.
    
    Args:
        crop_data: Crop database record
        farm_context: Farmer's farm context
        weather_data: Weather data dictionary
        
    Returns:
        Dictionary with compatibility scores and overall hybrid score
    """
    crop_name = crop_data.get("name", "Unknown")
    
    # 1. Season match (25% weight)
    season = farm_context.get("season", "")
    crop_seasons = crop_data.get("season", [])
    if isinstance(crop_seasons, str):
        crop_seasons = [crop_seasons]
    season_match = _season_match_score(season, crop_seasons)
    
    # 2. Soil type match (25% weight)
    crop_soils = crop_data.get("soils", [])
    if isinstance(crop_soils, str):
        crop_soils = [crop_soils]
    soil_match = 100.0 if farm_context.get("soil_type") in crop_soils else 60.0
    
    # 3. Nutrient proximity score (25% weight)
    n_score = _range_score(
        farm_context.get("n", 0),
        crop_data.get("n_range_min", 0),
        crop_data.get("n_range_max", 200),
    )
    p_score = _range_score(
        farm_context.get("p", 0),
        crop_data.get("p_range_min", 0),
        crop_data.get("p_range_max", 200),
    )
    k_score = _range_score(
        farm_context.get("k", 0),
        crop_data.get("k_range_min", 0),
        crop_data.get("k_range_max", 200),
    )
    ph_score = _range_score(
        farm_context.get("ph", 0),
        crop_data.get("ph_range_min", 5.0),
        crop_data.get("ph_range_max", 8.0),
    )
    nutrient_score = (n_score * 0.35 + p_score * 0.25 + k_score * 0.20 + ph_score * 0.20)
    
    # 4. Irrigation match (10% weight)
    irr_score = _irrigation_match_score(
        crop_data.get("water_req", "Medium"),
        farm_context.get("irrigation", "Canal irrigation"),
    )
    
    # 5. Regional compatibility (10% weight)
    region_match = _regional_match_score(
        farm_context.get("state", ""),
        crop_data.get("soils", []),
    )
    
    # Calculate composite score
    hybrid_score = int(round(
        season_match * 0.15 +
        soil_match * 0.20 +
        nutrient_score * 0.25 +
        irr_score * 0.10 +
        region_match * 0.10
    ))
    
    # Get weather-based scores
    weather_data_dict = weather_data or {}
    weather_score = _calculate_weather_score(
        crop_data=crop_data,
        weather_data=weather_data,
    )
    
    # Combine hybrid score with weather score
    # Weather gets 25% weight in final calculation
    composite_score = int(round(
        hybrid_score * 0.75 +
        weather_score * 0.25
    ))
    composite_score = max(0, min(100, composite_score))
    
    # Confidence level based on score
    if composite_score >= 85:
        confidence = "High"
    elif composite_score >= 70:
        confidence = "Moderate"
    else:
        confidence = "Low"
    
    return {
        "name": crop_data.get("name", "Unknown"),
        "hindi_name": crop_data.get("hindi_name", ""),
        "ml_probability": crop_data.get("ml_probability", hybrid_score),
        "hybrid_suitability": hybrid_score,
        "confidence": confidence,
        "soil_compatibility": int(round(soil_match)),
        "seasonal_compatibility": int(round(season_match)),
        "regional_compatibility": int(round(region_match)),
        "nutrient_compatibility": int(round(nutrient_score)),
        "irrigation_compatibility": int(round(irr_score)),
        "weather_compatibility": int(round(weather_score)),
        "water_req": crop_data.get("water_req", "Medium"),
        "description": crop_data.get("description", ""),
        "weather_summary": crop_data.get("weather_summary", ""),
        "irrigation_advice": crop_data.get("irrigation_advice", ""),
        "soil_desc": crop_data.get("soil_desc", ""),
        "season_desc": crop_data.get("season_desc", ""),
        "region_desc": crop_data.get("region_desc", ""),
        # Score breakdown for transparency
        "score_breakdown": {
            "season": int(round(season_match)),
            "soil": int(round(soil_match)),
            "nutrients": int(round(nutrient_score)),
            "irrigation": int(round(irr_score)),
            "region": int(round(region_match)),
            "weather": int(round(weather_score)),
        },
    }


def _calculate_weather_score(
    crop_data: Dict[str, Any],
    weather_data: Dict[str, Any],
) -> float:
    """
    Calculate weather compatibility score (0-100).
    
    Compares weather forecast with crop requirements.
    """
    weather_match_score = 100.0
    
    # Temperature compatibility
    crop_temp_min = crop_data.get("temp_min")
    crop_temp_max = crop_data.get("temp_max")
    forecast_temp = weather_data.get("temperature", 0) or 0
    
    if crop_temp_min is not None and crop_temp_max is not None:
        temp_score = _range_score(
            float(forecast_temp),
            float(crop_temp_min),
            float(crop_temp_max),
        )
    else:
        temp_score = 70.0  # Default moderate score
    
    # Humidity compatibility
    crop_humidity_min = crop_data.get("humidity_min")
    crop_humidity_max = crop_data.get("humidity_max")
    forecast_humidity = weather_data.get("humidity", 0) or 0
    
    if crop_humidity_min is not None and crop_humidity_max is not None:
        humidity_score = _range_score(
            float(forecast_humidity),
            float(crop_humidity_min),
            float(crop_humidity_max),
        )
    else:
        humidity_score = 70.0  # Default moderate score
    
    # Rainfall compatibility
    crop_water_req = crop_data.get("water_req", "Medium")
    forecast_rainfall = weather_data.get("rainfall_1h") or weather_data.get("rainfall_3h") or 0
    forecast_rainfall = float(forecast_rainfall) if forecast_rainfall else 0
    
    irrigation_score = _irrigation_match_score(
        crop_water_req,
        farm_context.get("irrigation", "Canal irrigation"),
    )
    
    # Wind compatibility
    crop_wind_tolerance = crop_data.get("wind_tolerance", "Medium")
    forecast_wind_speed = weather_data.get("wind_speed", 0) or 0
    
    wind_score = _calculate_wind_score(
        crop_water_req=crop_data.get("water_req", "Medium"),
        wind_tolerance=crop_wind_tolerance,
        wind_speed=float(forecast_wind_speed),
    )
    
    # Calculate overall weather score
    weather_score = (
        temp_score * 0.4 +
        humidity_score * 0.2 +
        rainfall_score * 0.2 +
        wind_score * 0.2
    )
    
    return weather_score


def _calculate_wind_score(
    crop_water_req: str,
    wind_tolerance: str,
    wind_speed: float,
) -> float:
    """
    Calculate wind compatibility score.
    
    High wind can damage crops, especially tall crops like sugarcane, cotton, etc.
    """
    # Wind tolerance from crop data
    wind_tolerance_map = {
        "Low": 5,    # Very sensitive to wind
        "Medium": 15, # Moderate tolerance
        "High": 30,   # High tolerance
    }
    
    wind_tolerance_threshold = wind_tolerance_map.get(wind_tolerance, 15)
    
    # Wind speed thresholds (km/h)
    if wind_speed <= 5:
        return 100.0  # Calm - perfect
    elif wind_speed <= 10:
        return 85.0   # Light breeze - minor impact
    elif wind_speed <= 20:
        return 60.0   # Moderate breeze - moderate impact
    elif wind_speed <= 30:
        return 40.0   # Strong wind - significant impact
    else:
        return 20.0   # Strong wind/gale - poor match
