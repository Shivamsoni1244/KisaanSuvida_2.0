"""
services/mistral_crop_engine.py - Mistral AI-powered crop recommendation engine

Integrates with Mistral AI for crop selection only.

recommend_crops() - Sends complete farmer input and available weather to Mistral
  and returns exactly one primary crop plus two alternative crops.
  No rule-based scoring, no ML prediction, no explanations, no scores.
  If Mistral is unavailable or returns an invalid response, returns an
  unavailable state with status "error".
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
from services.groq_service import get_crop_guide_part1, get_crop_guide_part2

logger = logging.getLogger(__name__)

# Cache for Mistral recommendation responses (TTL: 1 hour, max 100 entries)
_recommendation_cache = TTLCache(maxsize=100, ttl=3600)


def _get_mistral_config() -> Dict[str, Optional[str]]:
    """Retrieve Mistral API configuration from environment variables."""
    return {
        "api_key": os.environ.get("MISTRAL_API_KEY"),
        "model": os.environ.get("MISTRAL_MODEL_1", "mistral-small-latest"),
        "base_url": os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
    }


def _call_mistral_api(
    prompt: str, api_key: str, model: str, base_url: str
) -> Optional[Dict[str, Any]]:
    """
    Call the Mistral API with the given prompt.

    Args:
        prompt: Formatted prompt string
        api_key: Mistral API key
        model: Mistral model name
        base_url: Base URL for Mistral API

    Returns:
        Parsed JSON response or None on failure
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,
        "max_tokens": 1000,
    }

    try:
        start_time = time.time()
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        latency_ms = (time.time() - start_time) * 1000

        response.raise_for_status()
        data = response.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            logger.error("Mistral API returned empty content")
            record_api_call(
                provider="mistral",
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
                    logger.error("Failed to parse Mistral response as JSON")
                    record_api_call(
                        provider="mistral",
                        model=model,
                        input_text=prompt,
                        output_text=content,
                        latency_ms=latency_ms,
                        success=False,
                        error="JSON parse error",
                    )
                    return None

        record_api_call(
            provider="mistral",
            model=model,
            input_text=prompt,
            output_text=content,
            latency_ms=latency_ms,
            success=True,
        )
        return result

    except requests.exceptions.Timeout:
        logger.error("Mistral API request timed out")
        record_api_call(
            provider="mistral",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=30000,
            success=False,
            error="Timeout",
        )
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Mistral API connection error")
        record_api_call(
            provider="mistral",
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
            logger.error("Mistral API authentication failed")
        elif e.response.status_code == 429:
            logger.error("Mistral API rate limit exceeded")
        else:
            logger.error("Mistral API HTTP error: %s", e)
        record_api_call(
            provider="mistral",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None
    except Exception as e:
        logger.error("Unexpected error calling Mistral API: %s", e)
        record_api_call(
            provider="mistral",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None


def _build_recommend_crops_prompt(
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build a prompt asking Mistral to recommend one primary crop plus two alternatives
    based ONLY on the farmer's actual inputs and current weather.
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
        }

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Recommend exactly one primary crop and exactly two alternative crops based ONLY on the farmer's actual inputs and current weather. Do NOT use any hardcoded rules, scoring tables, or default crops.

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
- Temperature: {weather_summary.get('temperature', 'Not available')}°C
- Humidity: {weather_summary.get('humidity', 'Not available')}%
- Condition: {weather_summary.get('condition', 'Not available')}
- Rainfall: {weather_summary.get('rainfall', 'Not available')} mm

TASK:
1. Select ONE primary crop that best fits this specific farm.
2. Select TWO alternative crops worth considering.
3. For the primary crop, estimate compatibility percentages (0-100) for Soil, Season, and Region based on the farm context, plus list any cultivation risks.

Return ONLY valid JSON with this exact structure:
{{
  "status": "success",
  "top_crop": {{
    "name": "Crop name",
    "soil_compatibility": 85,
    "seasonal_compatibility": 90,
    "regional_compatibility": 88,
    "cultivation_risks": ["Risk 1", "Risk 2"],
    "suitability_score": 87
  }},
  "alternatives": [
    {{
      "name": "Alternative crop 1",
      "suitability_score": 80
    }},
    {{
      "name": "Alternative crop 2",
      "suitability_score": 75
    }}
  ]
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks, no additional text
- Base everything on the farmer's actual inputs and Indian agricultural conditions
- Do NOT default to any specific crop
- All three crop names must be provided
- The primary crop and alternatives should be different from each other
- All scores are integers between 0 and 100
"""

    return prompt


def _safe_int(value: Any, default: Any = "Not available") -> Any:
    try:
        result = int(value)
        if 0 <= result <= 100:
            return result
    except (TypeError, ValueError):
        pass
    return default


def _validate_and_normalize_recommendation(
    ai_response: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Validate and normalize the Mistral recommendation response.

    Returns the response with status "success" or "error".
    """
    if ai_response is None:
        return {
            "status": "error",
            "error": "Mistral API unavailable - recommendation could not be generated.",
            "top_crop": {"name": None},
            "alternatives": [{"name": None}, {"name": None}],
        }

    status = ai_response.get("status", "error")
    top_crop = ai_response.get("top_crop", {}) or {}
    alternatives = ai_response.get("alternatives", []) or []

    top_name = top_crop.get("name") if isinstance(top_crop, dict) else None
    alt_names = []
    alt_scores = []
    for alt in alternatives[:2]:
        if isinstance(alt, dict):
            alt_names.append(alt.get("name"))
            alt_scores.append(_safe_int(alt.get("suitability_score"), "Not available"))
        else:
            alt_names.append(None)
            alt_scores.append("Not available")

    # Ensure exactly two alternatives
    while len(alt_names) < 2:
        alt_names.append(None)
        alt_scores.append("Not available")

    # Validate: all three names must be non-empty strings
    if not top_name or not isinstance(top_name, str) or top_name.strip() == "":
        return {
            "status": "error",
            "error": "Mistral did not return a valid primary crop name.",
            "top_crop": {"name": None},
            "alternatives": [{"name": None}, {"name": None}],
        }

    valid_alternatives = []
    for i, name in enumerate(alt_names):
        if name and isinstance(name, str) and name.strip() != "":
            valid_alternatives.append({
                "name": name.strip(),
                "suitability_score": alt_scores[i] if i < len(alt_scores) else "Not available",
            })
        else:
            valid_alternatives.append({
                "name": None,
                "suitability_score": "Not available",
            })

    # If any alternative is missing, it's a failure
    if any(alt["name"] is None for alt in valid_alternatives):
        return {
            "status": "error",
            "error": "Mistral did not return two valid alternative crop names.",
            "top_crop": {
                "name": top_name.strip(),
                "soil_compatibility": _safe_int(top_crop.get("soil_compatibility"), "Not available"),
                "seasonal_compatibility": _safe_int(top_crop.get("seasonal_compatibility"), "Not available"),
                "regional_compatibility": _safe_int(top_crop.get("regional_compatibility"), "Not available"),
                "cultivation_risks": top_crop.get("cultivation_risks", ["Not available"]) if isinstance(top_crop.get("cultivation_risks"), list) else ["Not available"],
                "suitability_score": _safe_int(top_crop.get("suitability_score"), "Not available"),
            },
            "alternatives": valid_alternatives,
        }

    return {
        "status": "success",
        "top_crop": {
            "name": top_name.strip(),
            "soil_compatibility": _safe_int(top_crop.get("soil_compatibility"), "Not available"),
            "seasonal_compatibility": _safe_int(top_crop.get("seasonal_compatibility"), "Not available"),
            "regional_compatibility": _safe_int(top_crop.get("regional_compatibility"), "Not available"),
            "cultivation_risks": top_crop.get("cultivation_risks", ["Not available"]) if isinstance(top_crop.get("cultivation_risks"), list) else ["Not available"],
            "suitability_score": _safe_int(top_crop.get("suitability_score"), "Not available"),
        },
        "alternatives": valid_alternatives,
    }


def recommend_crops(
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get AI-powered crop recommendation from Mistral.

    Recommends one primary crop plus two alternatives based on the complete
    farm context and current weather. No rule-based scoring.

    If Mistral is unavailable or returns an invalid response, returns an
    error state with status "error".

    Args:
        farm_context: Farm context dictionary (state, district, season,
            soil_type, n, p, k, ph, irrigation)
        weather: Current weather data dictionary
        language: Response language ('en' or 'hi')

    Returns:
        Dictionary with status, top_crop, and alternatives
    """
    config = _get_mistral_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    cache_key = (
        f"recommend:{farm_context.get('state', '')}:{farm_context.get('district', '')}"
        f":{farm_context.get('season', '')}:{farm_context.get('soil_type', '')}"
        f":{farm_context.get('n', '')}:{farm_context.get('p', '')}:{farm_context.get('k', '')}"
        f":{farm_context.get('ph', '')}:{farm_context.get('irrigation', '')}:{language}"
    )
    if cache_key in _recommendation_cache:
        logger.info("Returning cached Mistral recommendation")
        return _recommendation_cache[cache_key]

    if api_key and api_key != "your_mistral_api_key_here":
        prompt = _build_recommend_crops_prompt(farm_context, weather, language)
        ai_response = _call_mistral_api(prompt, api_key, model, base_url)
        result = _validate_and_normalize_recommendation(ai_response)
    else:
        logger.warning("Mistral API key not configured - recommendation not available")
        result = _validate_and_normalize_recommendation(None)

    _recommendation_cache[cache_key] = result
    return result


_groq_crop_guide_cache = {}

def get_crop_guide(
    crop_name: str,
    farm_context: Dict[str, Any],
    language: str = "en",
    weather: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Get detailed crop cultivation guide using Groq API #3.

    Part 1 (growing & preparation) uses Groq API key 3.
    Part 2 (protection, harvest, post-harvest) uses Groq API key 3.

    If either key is unavailable, its part returns 'Not available'.

    Args:
        crop_name: Name of the crop
        farm_context: Farm context dictionary
        language: Response language
        weather: Optional current weather data dictionary

    Returns:
        Merged crop guide dictionary from both Groq API calls
    """
    na = "Not available"

    # Build weather summary for prompts
    weather_summary = {}
    if weather and weather.get("source") == "openweathermap":
        weather_summary = {
            "temperature": weather.get("temperature", "Not available"),
            "humidity": weather.get("humidity", "Not available"),
            "condition": weather.get("description", "Not available"),
            "rainfall": weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0,
            "wind_speed": weather.get("wind_speed", "Not available"),
        }

    cache_key = f"groq3_guide:{crop_name}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _groq_crop_guide_cache:
        logger.info("Returning cached Groq #3 crop guide")
        return _groq_crop_guide_cache[cache_key]

    # Fetch Part 1 from Groq API key 3
    part1 = get_crop_guide_part1(crop_name, farm_context, weather_summary, language)

    # Fetch Part 2 from Groq API key 3
    part2 = get_crop_guide_part2(crop_name, farm_context, weather_summary, language)

    # Merge both parts into a single guide
    guide = {
        **part1,
        **part2,
        "source": "groq_3",
        "farm_context": farm_context,
        "weather": weather_summary,
    }

    _groq_crop_guide_cache[cache_key] = guide
    return guide
