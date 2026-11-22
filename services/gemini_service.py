"""
services/gemini_service.py - Gemini API service for agricultural validation

Provides agricultural validation and quality check using Google's Gemini models.
Responsible for validating generated agricultural recommendations, identifying
contradictions between crop requirements and farmer inputs, checking seasonal
and regional appropriateness, and flagging recommendations that require
additional soil testing or local expert consultation.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
from cachetools import TTLCache

from services.cost_tracker import record_api_call

logger = logging.getLogger(__name__)

# Cache for Gemini validation responses (TTL: 1 hour, max 100 entries)
_gemini_cache = TTLCache(maxsize=100, ttl=3600)


def _get_gemini_config() -> Dict[str, Optional[str]]:
    """Retrieve Gemini API configuration from environment variables."""
    return {
        "api_key": os.environ.get("GEMINI_API_KEY"),
        "model": os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
        "base_url": os.environ.get(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        ),
    }


def _get_gemini_config_2() -> Dict[str, Optional[str]]:
    """Retrieve second Gemini API configuration from environment variables."""
    return {
        "api_key": os.environ.get("GEMINI_API_KEY_2"),
        "model": os.environ.get("GEMINI_MODEL_2", "gemini-1.5-flash"),
        "base_url": os.environ.get(
            "GEMINI_BASE_URL_2", "https://generativelanguage.googleapis.com/v1beta"
        ),
    }


def _build_gemini_prompt(
    recommendation: Dict[str, Any],
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build a structured prompt for Gemini AI with farm context and recommendation.

    Args:
        recommendation: The ML + AI recommendation result
        farm_context: Farm context dictionary
        weather: Current weather data dictionary
        language: Response language ('en' or 'hi')

    Returns:
        Formatted prompt string
    """
    lang_instruction = (
        "Respond in Hindi (हिन्दी)."
        if language == "hi"
        else "Respond in English."
    )

    top_crop = recommendation.get("top_crop", {})
    alternatives = recommendation.get("alternatives", [])

    prompt = f"""You are an expert agricultural validator for Indian farmers. Review the following crop recommendation and validate its agricultural soundness.

{lang_instruction}

FARM CONTEXT:
- State: {farm_context.get('state', 'Not specified')}
- District: {farm_context.get('district', 'Not specified')}
- Season: {farm_context.get('season', 'Not specified')}
- Soil type: {farm_context.get('soil_type', 'Not specified')}
- Nitrogen (N): {farm_context.get('n', 'Not specified')} kg/ha
- Phosphorus (P): {farm_context.get('p', 'Not specified')} kg/ha
- Potassium (K): {farm_context.get('k', 'Not specified')} kg/ha
- Soil pH: {farm_context.get('ph', 'Not specified')}
- Irrigation: {farm_context.get('irrigation', 'Not specified')}

CURRENT WEATHER:
- Temperature: {weather.get('temperature', 'Not available')}°C
- Humidity: {weather.get('humidity', 'Not available')}%
- Condition: {weather.get('description', 'Not available')}
- Rainfall: {weather.get('rainfall', 'Not available')} mm

TOP RECOMMENDATION:
- Crop: {top_crop.get('name', 'Not specified')}
- Suitability score: {top_crop.get('suitability_score', 'Not available')}%
- Soil compatibility: {top_crop.get('soil_compatibility', 'Not available')}%
- Season compatibility: {top_crop.get('seasonal_compatibility', 'Not available')}%
- Regional compatibility: {top_crop.get('regional_compatibility', 'Not available')}%
- Water requirement: {top_crop.get('water_requirement', 'Not available')}

ALTERNATIVE CROPS:
{json.dumps(alternatives, indent=2) if alternatives else 'None provided'}

TASK:
Validate this agricultural recommendation. Check for:
1. Is the recommended crop suitable for the farmer's soil type, pH, and NPK levels?
2. Is the season appropriate for this crop in this region?
3. Is the water requirement compatible with the irrigation availability?
4. Are there any contradictions between crop requirements and farmer inputs?
5. Is the regional suitability accurate for this state/district?
6. What additional soil testing or expert consultation is needed?
7. Are there any risks or warnings the farmer should know?

Return ONLY valid JSON with this exact structure:
{{
  "validation_status": "valid/minor_concerns/major_concerns/not_recommended",
  "overall_score": 85,
  "summary": "Brief validation summary (1-2 sentences)",
  "validations": [
    {{
      "aspect": "Soil compatibility",
      "status": "pass/warning/fail",
      "message": "Detailed explanation",
      "confidence": "high/medium/low"
    }}
  ],
  "contradictions": [
    {{
      "aspect": "Water requirement vs irrigation",
      "issue": "Description of contradiction",
      "severity": "low/medium/high"
    }}
  ],
  "missing_information": [
    "Soil test for micronutrients",
    "Local pest pressure data"
  ],
  "recommendations": [
    "Consult local KVK for variety selection",
    "Conduct soil test before planting"
  ],
  "risks": [
    "Heat stress during flowering",
    "Waterlogging risk in monsoon"
  ],
  "disclaimer": "Validation is advisory. Consult local agricultural experts before major decisions."
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks
- Base validation on Indian agricultural conditions
- Be honest about uncertainties and limitations
- Do not fabricate agricultural statistics
- All scores must be integers between 0 and 100
- validation_status must be one of: valid, minor_concerns, major_concerns, not_recommended
- Each validation status must be: pass, warning, or fail
- Each contradiction severity must be: low, medium, or high
"""

    return prompt


def _call_gemini_api(
    prompt: str, api_key: str, model: str, base_url: str
) -> Optional[Dict[str, Any]]:
    """
    Call the Gemini API with the given prompt.

    Args:
        prompt: Formatted prompt string
        api_key: Gemini API key
        model: Gemini model name
        base_url: Base URL for Gemini API

    Returns:
        Parsed JSON response or None on failure
    """
    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1500,
        },
    }

    try:
        start_time = time.time()
        response = requests.post(
            f"{base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}",
            headers=headers,
            json=payload,
            timeout=30,
        )
        latency_ms = (time.time() - start_time) * 1000

        response.raise_for_status()
        data = response.json()

        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {}).get("parts", [{}])[0].get(
                "text", ""
            )

        if not content:
            logger.error("Gemini API returned empty content")
            record_api_call(
                provider="gemini",
                model=model,
                input_text=prompt,
                output_text="",
                latency_ms=latency_ms,
                success=False,
                error="Empty response",
            )
            return None

        # Try to parse JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    logger.error("Failed to parse Gemini response as JSON")
                    record_api_call(
                        provider="gemini",
                        model=model,
                        input_text=prompt,
                        output_text=content,
                        latency_ms=latency_ms,
                        success=False,
                        error="JSON parse error",
                    )
                    return None

        record_api_call(
            provider="gemini",
            model=model,
            input_text=prompt,
            output_text=content,
            latency_ms=latency_ms,
            success=True,
        )
        return result

    except requests.exceptions.Timeout:
        logger.error("Gemini API request timed out")
        record_api_call(
            provider="gemini",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=30000,
            success=False,
            error="Timeout",
        )
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Gemini API connection error")
        record_api_call(
            provider="gemini",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error="Connection error",
        )
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("Gemini API authentication failed")
        elif e.response.status_code == 429:
            logger.error("Gemini API rate limit exceeded")
        else:
            logger.error("Gemini API HTTP error: %s", e)
        record_api_call(
            provider="gemini",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None
    except Exception as e:
        logger.error("Unexpected error calling Gemini API: %s", e)
        record_api_call(
            provider="gemini",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None


def _validate_and_normalize_response(
    ai_response: Optional[Dict[str, Any]],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Validate and normalize the Gemini API response.

    Args:
        ai_response: Raw AI response dictionary or None
        farm_context: Original farm context
        language: Response language

    Returns:
        Normalized response dictionary
    """
    na = "Not available"

    if ai_response is None:
        return {
            "validation_status": "not_recommended",
            "overall_score": 0,
            "summary": "Validation unavailable - Gemini API not accessible",
            "validations": [
                {
                    "aspect": "Overall",
                    "status": "fail",
                    "message": "Gemini API unavailable - cannot validate recommendations",
                    "confidence": "low",
                }
            ],
            "contradictions": [
                {
                    "aspect": "All",
                    "issue": "Cannot validate without API access",
                    "severity": "high",
                }
            ],
            "missing_information": ["API validation unavailable"],
            "recommendations": ["Consult local agricultural experts before planting"],
            "risks": ["Validation unavailable"],
            "disclaimer": "Gemini API unavailable - validation not performed.",
            "source": "not_available",
        }

    return {
        "validation_status": ai_response.get(
            "validation_status", "not_recommended"
        ),
        "overall_score": _safe_int(ai_response.get("overall_score"), 0),
        "summary": ai_response.get(
            "summary", "Validation completed with limited information."
        ),
        "validations": ai_response.get("validations", [])
        if isinstance(ai_response.get("validations"), list)
        else [
            {
                "aspect": "Overall",
                "status": "warning",
                "message": "Validation data incomplete",
                "confidence": "low",
            }
        ],
        "contradictions": ai_response.get("contradictions", [])
        if isinstance(ai_response.get("contradictions"), list)
        else [],
        "missing_information": ai_response.get("missing_information", [])
        if isinstance(ai_response.get("missing_information"), list)
        else [],
        "recommendations": ai_response.get("recommendations", [])
        if isinstance(ai_response.get("recommendations"), list)
        else [],
        "risks": ai_response.get("risks", [])
        if isinstance(ai_response.get("risks"), list)
        else [],
        "disclaimer": ai_response.get(
            "disclaimer",
            "Validation is advisory. Consult local agricultural experts before major decisions.",
        ),
        "source": "gemini",
    }


def _safe_int(value: Any, default: str = "Not available") -> str:
    """Safely convert a value to int string."""
    try:
        result = int(value)
        if 0 <= result <= 100:
            return str(result)
    except (TypeError, ValueError):
        pass
    return default


def validate_recommendation(
    recommendation: Dict[str, Any],
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Validate crop recommendation using Gemini API.

    Args:
        recommendation: The recommendation result from Mistral + ML engine
        farm_context: Farm context dictionary
        weather: Current weather data dictionary
        language: Response language ('en' or 'hi')

    Returns:
        Validation result dictionary
    """
    config = _get_gemini_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    # Check cache
    cache_key = f"gemini_val:{recommendation.get('top_crop', {}).get('name', '')}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _gemini_cache:
        logger.info("Returning cached Gemini validation")
        return _gemini_cache[cache_key]

    # Try Gemini API only
    if api_key and api_key != "your_gemini_api_key_here":
        prompt = _build_gemini_prompt(recommendation, farm_context, weather, language)
        ai_response = _call_gemini_api(prompt, api_key, model, base_url)
        result = _validate_and_normalize_response(ai_response, farm_context, language)
    else:
        logger.warning("Gemini API key not configured - validation not available")
        result = _validate_and_normalize_response(None, farm_context, language)

    # Cache the result
    _gemini_cache[cache_key] = result
    return result


# =============================================================================
# GEMINI - Crop Guide Part 1 & Part 2 (two API keys, same model)
# =============================================================================

def _build_gemini_crop_guide_prompt_part1(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build Part 1 of the crop guide: growing & preparation info.
    Uses Gemini API key 1.
    """
    lang_instruction = (
        "Respond in Hindi (हिन्दी)."
        if language == "hi"
        else "Respond in English."
    )

    soil_values_note = (
        "Measured from soil health card"
        if farm_context.get("soil_values_source") == "advanced"
        else "Estimated from regional soil type averages"
    )

    weather_summary = {}
    if weather and weather.get("source") == "openweathermap":
        weather_summary = {
            "temperature": weather.get("temperature", "Not available"),
            "humidity": weather.get("humidity", "Not available"),
            "condition": weather.get("description", "Not available"),
            "rainfall": weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0,
            "wind_speed": weather.get("wind_speed", "Not available"),
        }

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Provide Part 1 of the detailed cultivation guide for {crop_name}.

{lang_instruction}

FARM CONTEXT:
- State: {farm_context.get('state', 'Not specified')}
- District: {farm_context.get('district', 'Not specified')}
- Season: {farm_context.get('season', 'Not specified')}
- Soil type: {farm_context.get('soil_type', 'Not specified')}
- Nitrogen (N): {farm_context.get('n', 'Not specified')} kg/ha ({soil_values_note})
- Phosphorus (P): {farm_context.get('p', 'Not specified')} kg/ha ({soil_values_note})
- Potassium (K): {farm_context.get('k', 'Not specified')} kg/ha ({soil_values_note})
- Soil pH: {farm_context.get('ph', 'Not specified')} ({soil_values_note})
- Irrigation: {farm_context.get('irrigation', 'Not specified')}

CURRENT WEATHER:
- Temperature: {weather_summary.get('temperature', 'Not available')}°C
- Humidity: {weather_summary.get('humidity', 'Not available')}%
- Condition: {weather_summary.get('condition', 'Not available')}
- Rainfall: {weather_summary.get('rainfall', 'Not available')} mm
- Wind speed: {weather_summary.get('wind_speed', 'Not available')} m/s

TASK: Generate Part 1 of a comprehensive cultivation guide for {crop_name} tailored to this specific farm context. Cover growing conditions, land preparation, seed, fertilizer, and irrigation.

Return ONLY valid JSON with this exact structure:
{{
  "crop_name": "{crop_name}",
  "hindi_name": "Hindi name in Devanagari script (when language is hi)",
  "scientific_name": "Scientific name if known",
  "introduction": "2-3 sentence introduction explaining why this crop suits the farm context",
  "climate_temperature": "Ideal temperature range and suitable climatic conditions",
  "rainfall_requirements": "Rainfall requirements and water needs",
  "soil_types": "Suitable soil types for this crop",
  "recommended_ph": "Recommended soil pH range",
  "land_preparation": "Detailed land preparation steps",
  "seed_selection": "Recommended seed varieties appropriate to the region",
  "seed_treatment": "Seed treatment precautions and methods",
  "seed_rate": "Seed rate per hectare when reliable regional data exists",
  "sowing_time": "Best sowing/planting period",
  "sowing_method": "Sowing method and technique",
  "spacing_row": "Row-to-row spacing when known",
  "spacing_plant": "Plant-to-plant spacing when known",
  "fertilizer_requirements": "Fertilizer requirements based on soil test results",
  "nitrogen_management": "Nitrogen management guidance",
  "phosphorus_management": "Phosphorus management guidance",
  "potassium_management": "Potassium management guidance",
  "organic_fertilizer": "Organic fertilizer options",
  "nutrient_deficiency": "Nutrient deficiency symptoms and management",
  "irrigation_requirements": "Water requirements for this crop",
  "irrigation_frequency": "Irrigation frequency guidance",
  "critical_irrigation_stages": "Critical growth stages for irrigation",
  "drip_sprinkler": "Drip or sprinkler irrigation suitability",
  "waterlogging_precautions": "Waterlogging precautions"
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks
- Base all recommendations on Indian agricultural conditions
- Consider the farmer's actual state, district, soil type, and season
- Do not invent specific fertilizer dosages, pesticide names, or guaranteed yields
- When information is unavailable, state that clearly
- Hindi names in Devanagari script when language is 'hi'
"""

    return prompt


def _build_gemini_crop_guide_prompt_part2(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build Part 2 of the crop guide: protection, harvest & post-harvest info.
    Uses Gemini API key 2.
    """
    lang_instruction = (
        "Respond in Hindi (हिन्दी)."
        if language == "hi"
        else "Respond in English."
    )

    weather_summary = {}
    if weather and weather.get("source") == "openweathermap":
        weather_summary = {
            "temperature": weather.get("temperature", "Not available"),
            "humidity": weather.get("humidity", "Not available"),
            "condition": weather.get("description", "Not available"),
            "rainfall": weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0,
            "wind_speed": weather.get("wind_speed", "Not available"),
        }

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Provide Part 2 of the detailed cultivation guide for {crop_name}.

{lang_instruction}

FARM CONTEXT:
- State: {farm_context.get('state', 'Not specified')}
- District: {farm_context.get('district', 'Not specified')}
- Season: {farm_context.get('season', 'Not specified')}
- Soil type: {farm_context.get('soil_type', 'Not specified')}
- Irrigation: {farm_context.get('irrigation', 'Not specified')}

CURRENT WEATHER:
- Temperature: {weather_summary.get('temperature', 'Not available')}°C
- Humidity: {weather_summary.get('humidity', 'Not available')}%
- Condition: {weather_summary.get('condition', 'Not available')}
- Rainfall: {weather_summary.get('rainfall', 'Not available')} mm

TASK: Generate Part 2 of a comprehensive cultivation guide for {crop_name} tailored to this specific farm context. Cover pest/disease management, harvesting, post-harvest, and precautions.

Return ONLY valid JSON with this exact structure:
{{
  "common_weeds": "Common weeds affecting this crop",
  "weed_manual_control": "Manual and mechanical weed control methods",
  "weed_preventive": "Preventive weed management practices",
  "herbicide_precautions": "Herbicide use precautions",
  "common_pests": "Common regional pests",
  "common_diseases": "Common crop diseases",
  "pest_symptoms": "Symptoms to watch for",
  "pest_preventive": "Preventive pest management measures",
  "ipm": "Integrated Pest Management approach",
  "biological_control": "Biological control options",
  "pesticide_precautions": "Safe pesticide use precautions - never specify dosages",
  "growth_stage_germination": "Germination stage description",
  "growth_stage_seedling": "Seedling establishment stage description",
  "growth_stage_vegetative": "Vegetative growth stage description",
  "growth_stage_flowering": "Flowering stage description",
  "growth_stage_fruit_grain": "Fruit/grain formation stage description",
  "growth_stage_maturity": "Maturity stage description",
  "harvesting_signs": "Signs of crop maturity",
  "harvesting_time": "Appropriate harvesting time",
  "harvesting_method": "Harvesting techniques",
  "crop_duration_days": 120,
  "expected_yield": "Expected yield range with disclaimer about variability",
  "post_harvest_cleaning": "Cleaning after harvest",
  "post_harvest_drying": "Drying requirements",
  "post_harvest_storage": "Storage conditions",
  "post_harvest_transport": "Transportation and handling",
  "precautions": "Important precautions and common mistakes",
  "disclaimer": "Consult local agricultural experts and KVK before implementation. Do not invent fertilizer dosages or guaranteed yields."
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks
- Base all recommendations on Indian agricultural conditions
- Consider the farmer's actual state, district, soil type, and season
- Do not invent specific fertilizer dosages, pesticide names, or guaranteed yields
- When information is unavailable, state that clearly
- Hindi content in Devanagari script when language is 'hi'
"""

    return prompt


def validate_recommendation(
    recommendation: Dict[str, Any],
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Validate crop recommendation using Gemini API.
    """
    config = _get_gemini_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    # Check cache
    cache_key = f"gemini_val:{recommendation.get('top_crop', {}).get('name', '')}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _gemini_cache:
        logger.info("Returning cached Gemini validation")
        return _gemini_cache[cache_key]

    # Try Gemini API only
    if api_key and api_key != "your_gemini_api_key_here":
        prompt = _build_gemini_prompt(recommendation, farm_context, weather, language)
        ai_response = _call_gemini_api(prompt, api_key, model, base_url)
        result = _validate_and_normalize_response(ai_response, farm_context, language)
    else:
        logger.warning("Gemini API key not configured - validation not available")
        result = _validate_and_normalize_response(None, farm_context, language)

    # Cache the result
    _gemini_cache[cache_key] = result
    return result


def get_crop_guide_part1(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get Part 1 of crop guide (growing & preparation) using Gemini API key 1.
    """
    config = _get_gemini_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = f"gemini_guide1:{crop_name}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _gemini_cache:
        logger.info("Returning cached Gemini crop guide part 1")
        return _gemini_cache[cache_key]

    if api_key and api_key != "your_gemini_api_key_here":
        prompt = _build_gemini_crop_guide_prompt_part1(
            crop_name, farm_context, weather, language
        )
        ai_response = _call_gemini_api(prompt, api_key, model, base_url)
    else:
        logger.warning("Gemini API key 1 not configured - crop guide part 1 not available")
        ai_response = None

    if ai_response is None:
        result = {
            "crop_name": crop_name,
            "hindi_name": na,
            "scientific_name": na,
            "introduction": na,
            "climate_temperature": na,
            "rainfall_requirements": na,
            "soil_types": na,
            "recommended_ph": na,
            "land_preparation": na,
            "seed_selection": na,
            "seed_treatment": na,
            "seed_rate": na,
            "sowing_time": na,
            "sowing_method": na,
            "spacing_row": na,
            "spacing_plant": na,
            "fertilizer_requirements": na,
            "nitrogen_management": na,
            "phosphorus_management": na,
            "potassium_management": na,
            "organic_fertilizer": na,
            "nutrient_deficiency": na,
            "irrigation_requirements": na,
            "irrigation_frequency": na,
            "critical_irrigation_stages": na,
            "drip_sprinkler": na,
            "waterlogging_precautions": na,
            "source": "not_available",
        }
    else:
        result = {**ai_response, "source": "gemini_1"}

    _gemini_cache[cache_key] = result
    return result


def get_crop_guide_part2(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get Part 2 of crop guide (protection, harvest, post-harvest) using Gemini API key 2.
    """
    config = _get_gemini_config_2()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = f"gemini_guide2:{crop_name}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _gemini_cache:
        logger.info("Returning cached Gemini crop guide part 2")
        return _gemini_cache[cache_key]

    if api_key and api_key != "your_gemini_api_key_2_here" and api_key:
        prompt = _build_gemini_crop_guide_prompt_part2(
            crop_name, farm_context, weather, language
        )
        ai_response = _call_gemini_api(prompt, api_key, model, base_url)
    else:
        logger.warning("Gemini API key 2 not configured - crop guide part 2 not available")
        ai_response = None

    if ai_response is None:
        result = {
            "common_weeds": na,
            "weed_manual_control": na,
            "weed_preventive": na,
            "herbicide_precautions": na,
            "common_pests": na,
            "common_diseases": na,
            "pest_symptoms": na,
            "pest_preventive": na,
            "ipm": na,
            "biological_control": na,
            "pesticide_precautions": na,
            "growth_stage_germination": na,
            "growth_stage_seedling": na,
            "growth_stage_vegetative": na,
            "growth_stage_flowering": na,
            "growth_stage_fruit_grain": na,
            "growth_stage_maturity": na,
            "harvesting_signs": na,
            "harvesting_time": na,
            "harvesting_method": na,
            "crop_duration_days": na,
            "expected_yield": na,
            "post_harvest_cleaning": na,
            "post_harvest_drying": na,
            "post_harvest_storage": na,
            "post_harvest_transport": na,
            "precautions": na,
            "disclaimer": "Gemini API unavailable - crop guide not available.",
            "source": "not_available",
        }
    else:
        result = {**ai_response, "source": "gemini_2"}

    _gemini_cache[cache_key] = result
    return result