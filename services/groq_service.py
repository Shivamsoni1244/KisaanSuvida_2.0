"""
services/groq_service.py - Groq API service for alternative crop analysis

Provides fast, cost-effective alternative crop recommendations using Groq's
Llama models. Responsible for generating explanations for alternative crops
worth considering, comparing them based on water requirements, soil compatibility,
season, regional suitability, and growing conditions.
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

# Cache for Groq alternative crop responses (TTL: 1 hour, max 100 entries)
_groq_cache = TTLCache(maxsize=100, ttl=3600)


def _get_groq_config() -> Dict[str, Optional[str]]:
    """Retrieve Groq API configuration from environment variables."""
    return {
        "api_key": os.environ.get("GROQ_API_KEY"),
        "model": os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
        "base_url": os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    }


def _build_groq_prompt(
    top_crop: Dict[str, Any],
    alternatives: List[Dict[str, Any]],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build a structured prompt for Groq AI with farm context and top crop.

    Args:
        top_crop: The top ML-recommended crop
        alternatives: List of alternative crop dictionaries
        farm_context: Farm context dictionary
        language: Response language ('en' or 'hi')

    Returns:
        Formatted prompt string
    """
    lang_instruction = (
        "Respond in Hindi (हिन्दी)."
        if language == "hi"
        else "Respond in English."
    )

    # Build alternatives context
    alternatives_context = ""
    for i, alt in enumerate(alternatives[:3], 1):
        alternatives_context += f"""
        {i}. {alt.get('name', 'Unknown')} ({alt.get('hindi_name', '')})
           - Season: {alt.get('season', 'Not specified')}
           - Water needs: {alt.get('water_requirement', 'Not specified')}
           - Suitability: {alt.get('suitability_score', 'Not available')}%
           - Description: {alt.get('summary', 'Not available')}
        """

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Analyze alternative crops for a farmer's situation.

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

TOP ML RECOMMENDATION:
- Crop: {top_crop.get('name', 'Not specified')}
- Suitability score: {top_crop.get('suitability_score', 'Not available')}%
- Soil compatibility: {top_crop.get('soil_compatibility', 'Not available')}%
- Season compatibility: {top_crop.get('seasonal_compatibility', 'Not available')}%
- Regional compatibility: {top_crop.get('regional_compatibility', 'Not available')}%
- Water requirement: {top_crop.get('water_requirement', 'Not available')}

ALTERNATIVE CROPS TO EVALUATE:
{alternatives_context}

TASK:
Evaluate each alternative crop and explain why it could be a good fit for this farmer's specific situation. Consider:
1. How well each crop matches the soil type, pH, and NPK levels
2. How well each crop matches the season and regional climate
3. Water requirement vs irrigation availability
4. Regional growing suitability for the farmer's state/district

Return ONLY valid JSON with this exact structure:
{{
  "alternative_crops": [
    {{
      "name": "Crop name",
      "hindi_name": "Hindi name in Devanagari (when language is hi)",
      "suitability_score": 85,
      "summary": "Short explanation of why this crop is suitable (1-2 sentences)",
      "water_requirement": "High/Medium/Low",
      "season": "Kharif/Rabi/Zaid",
      "soil_compatibility": 90,
      "season_compatibility": 95,
      "regional_compatibility": 88,
      "why_suitable": "Detailed explanation of why this crop fits this specific farm (2-3 sentences)",
      "key_advantages": ["Advantage 1", "Advantage 2"],
      "key_considerations": ["Consideration 1", "Consideration 2"]
    }}
  ],
  "comparison_summary": "Brief comparison of all alternatives (2-3 sentences)",
  "disclaimer": "AI-generated recommendations. Consult local agricultural experts before major decisions."
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks
- Base recommendations on Indian agricultural conditions
- Do NOT hardcode Rice, Maize, or Cotton - base selections on actual farm data
- All scores must be integers between 0 and 100
- Hindi names in Devanagari script when language is 'hi'
- Provide exactly the alternative crops given in the input, do not add or remove crops
"""

    return prompt


def _call_groq_api(
    prompt: str, api_key: str, model: str, base_url: str, max_tokens: int = 1500
) -> Optional[Dict[str, Any]]:
    """
    Call the Groq API with the given prompt.

    Args:
        prompt: Formatted prompt string
        api_key: Groq API key
        model: Groq model name
        base_url: Base URL for Groq API
        max_tokens: Maximum tokens in response (default 1500)

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
                "role": "system",
                "content": "You are an expert agricultural advisor for Indian farmers. Return only valid JSON.",
            },
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
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
            logger.error("Groq API returned empty content")
            record_api_call(
                provider="groq",
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
            import re
            json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    logger.error("Failed to parse Groq response as JSON")
                    record_api_call(
                        provider="groq",
                        model=model,
                        input_text=prompt,
                        output_text=content,
                        latency_ms=latency_ms,
                        success=False,
                        error="JSON parse error",
                    )
                    return None

        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text=content,
            latency_ms=latency_ms,
            success=True,
        )
        return result

    except requests.exceptions.Timeout:
        logger.error("Groq API request timed out")
        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=30000,
            success=False,
            error="Timeout",
        )
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Groq API connection error")
        record_api_call(
            provider="groq",
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
            logger.error("Groq API authentication failed")
        elif e.response.status_code == 429:
            logger.error("Groq API rate limit exceeded")
        else:
            logger.error("Groq API HTTP error: %s", e)
        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None
    except Exception as e:
        logger.error("Unexpected error calling Groq API: %s", e)
        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None


def _validate_and_normalize_alternatives(
    ai_response: Optional[Dict[str, Any]],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Validate and normalize the Groq API response for alternative crops.

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
            "alternative_crops": [
                {
                    "name": na,
                    "hindi_name": na,
                    "suitability_score": na,
                    "summary": na,
                    "water_requirement": na,
                    "season": na,
                    "soil_compatibility": na,
                    "season_compatibility": na,
                    "regional_compatibility": na,
                    "why_suitable": na,
                    "key_advantages": [na],
                    "key_considerations": [na],
                }
            ],
            "comparison_summary": na,
            "disclaimer": "Groq API unavailable - alternative crop analysis not available.",
            "source": "not_available",
        }

    alternative_crops = ai_response.get("alternative_crops", []) or []
    comparison_summary = ai_response.get("comparison_summary", "")
    disclaimer = ai_response.get(
        "disclaimer", "Consult local agricultural experts before major decisions."
    )

    normalized_alternatives = []
    for alt in alternative_crops[:3]:
        if not isinstance(alt, dict):
            continue
        normalized_alternatives.append({
            "name": alt.get("name", na),
            "hindi_name": alt.get("hindi_name", na),
            "suitability_score": _safe_int(alt.get("suitability_score"), na),
            "summary": alt.get("summary", na),
            "water_requirement": alt.get("water_requirement", na),
            "season": alt.get("season", na),
            "soil_compatibility": _safe_int(alt.get("soil_compatibility"), na),
            "season_compatibility": _safe_int(alt.get("season_compatibility"), na),
            "regional_compatibility": _safe_int(alt.get("regional_compatibility"), na),
            "why_suitable": alt.get("why_suitable", na),
            "key_advantages": alt.get("key_advantages", [na]) if isinstance(alt.get("key_advantages"), list) else [na],
            "key_considerations": alt.get("key_considerations", [na]) if isinstance(alt.get("key_considerations"), list) else [na],
        })

    # Ensure we have at least 2 alternatives
    while len(normalized_alternatives) < 2:
        normalized_alternatives.append({
            "name": na,
            "hindi_name": na,
            "suitability_score": na,
            "summary": na,
            "water_requirement": na,
            "season": na,
            "soil_compatibility": na,
            "season_compatibility": na,
            "regional_compatibility": na,
            "why_suitable": na,
            "key_advantages": [na],
            "key_considerations": [na],
        })

    return {
        "alternative_crops": normalized_alternatives,
        "comparison_summary": comparison_summary or na,
        "disclaimer": disclaimer,
        "source": "groq",
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


def get_alternative_crops(
    top_crop: Dict[str, Any],
    alternatives: List[Dict[str, Any]],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get alternative crop analysis using Groq API.

    Args:
        top_crop: The top ML-recommended crop dictionary
        alternatives: List of alternative crop dictionaries from ML engine
        farm_context: Farm context dictionary
        language: Response language ('en' or 'hi')

    Returns:
        Structured alternative crop analysis dictionary
    """
    config = _get_groq_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    # Check cache
    cache_key = f"groq_alt:{top_crop.get('name', '')}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{farm_context.get('season', '')}:{language}"
    if cache_key in _groq_cache:
        logger.info("Returning cached Groq alternative crops")
        return _groq_cache[cache_key]

    # Try Groq API only
    if api_key and api_key != "your_groq_api_key_here":
        prompt = _build_groq_prompt(top_crop, alternatives, farm_context, language)
        ai_response = _call_groq_api(prompt, api_key, model, base_url)
        result = _validate_and_normalize_alternatives(ai_response, farm_context, language)
    else:
        logger.warning("Groq API key not configured - returning 'Not available'")
        result = _validate_and_normalize_alternatives(None, farm_context, language)

    # Cache the result
    _groq_cache[cache_key] = result
    return result


# =============================================================================
# GROQ - Crop Explanation (Image 1 sections)
# =============================================================================

def _build_explain_prompt(
    top_crop: Dict[str, Any],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build a prompt for Groq to explain why a crop was recommended.

    Returns: explanation, key_factors, states_where_it_grows, did_you_know, how_to_grow_summary
    """
    lang_instruction = (
        "Respond in Hindi (हिन्दी)."
        if language == "hi"
        else "Respond in English."
    )

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Explain why the recommended crop suits this farmer's situation.

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

RECOMMENDED CROP:
- Name: {top_crop.get('name', 'Not specified')}

TASK:
Provide the following for this crop recommendation:
1. A 2-3 sentence explanation of why this crop suits this specific farm
2. 3 key factors that make this crop suitable
3. States where this crop is commonly grown (list of state names)
4. An interesting "Did you know?" fact about this crop
5. A 1-2 sentence summary of how to grow this crop

Return ONLY valid JSON with this exact structure:
{{
  "explanation": "2-3 sentences explaining why this crop suits this farm",
  "key_factors": ["Factor 1", "Factor 2", "Factor 3"],
  "states_where_it_grows": ["State 1", "State 2", "State 3"],
  "did_you_know": "Interesting fact about this crop",
  "how_to_grow_summary": "1-2 sentence summary of how to grow this crop"
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks, no additional text
- Base everything on Indian agricultural conditions
- Hindi content in Devanagari script when language is 'hi'
"""

    return prompt


def _call_groq_api(
    prompt: str, api_key: str, model: str, base_url: str, max_tokens: int = 1500
) -> Optional[Dict[str, Any]]:
    """
    Call the Groq API with the given prompt.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert agricultural advisor for Indian farmers. Return only valid JSON.",
            },
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
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
            logger.error("Groq API returned empty content")
            record_api_call(
                provider="groq",
                model=model,
                input_text=prompt,
                output_text="",
                latency_ms=latency_ms,
                success=False,
                error="Empty response",
            )
            return None

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    logger.error("Failed to parse Groq response as JSON")
                    record_api_call(
                        provider="groq",
                        model=model,
                        input_text=prompt,
                        output_text=content,
                        latency_ms=latency_ms,
                        success=False,
                        error="JSON parse error",
                    )
                    return None

        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text=content,
            latency_ms=latency_ms,
            success=True,
        )
        return result

    except requests.exceptions.Timeout:
        logger.error("Groq API request timed out")
        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=30000,
            success=False,
            error="Timeout",
        )
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Groq API connection error")
        record_api_call(
            provider="groq",
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
            logger.error("Groq API authentication failed")
        elif e.response.status_code == 429:
            logger.error("Groq API rate limit exceeded")
        else:
            logger.error("Groq API HTTP error: %s", e)
        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None
    except Exception as e:
        logger.error("Unexpected error calling Groq API: %s", e)
        record_api_call(
            provider="groq",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None


def explain_recommendation(
    top_crop: Dict[str, Any],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get AI-powered explanation for why a crop was recommended using Groq.

    Returns:
        explanation, key_factors, states_where_it_grows, did_you_know, how_to_grow_summary
    """
    config = _get_groq_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = (
        f"groq_explain:{top_crop.get('name', '')}:{farm_context.get('state', '')}"
        f":{farm_context.get('district', '')}:{language}"
    )
    if cache_key in _groq_cache:
        logger.info("Returning cached Groq explanation")
        return _groq_cache[cache_key]

    if api_key and api_key != "your_groq_api_key_here":
        prompt = _build_explain_prompt(top_crop, farm_context, language)
        ai_response = _call_groq_api(prompt, api_key, model, base_url)
    else:
        logger.warning("Groq API key not configured - explanation not available")
        ai_response = None

    if ai_response is None:
        result = {
            "explanation": na,
            "key_factors": [na],
            "states_where_it_grows": [na],
            "did_you_know": na,
            "how_to_grow_summary": na,
            "source": "not_available",
        }
    else:
        result = {
            "explanation": ai_response.get("explanation", na),
            "key_factors": ai_response.get("key_factors", [na])
            if isinstance(ai_response.get("key_factors"), list)
            else [na],
            "states_where_it_grows": ai_response.get("states_where_it_grows", [na])
            if isinstance(ai_response.get("states_where_it_grows"), list)
            else [na],
            "did_you_know": ai_response.get("did_you_know", na),
            "how_to_grow_summary": ai_response.get("how_to_grow_summary", na),
            "source": "groq",
        }

    _groq_cache[cache_key] = result
    return result


# =============================================================================
# GROQ #2 - Agricultural Validation (replaces Gemini validation)
# =============================================================================

_groq_cache_2 = TTLCache(maxsize=100, ttl=3600)


def _get_groq_config_2() -> Dict[str, Optional[str]]:
    """Retrieve Groq API #2 configuration (validation) from environment variables."""
    return {
        "api_key": os.environ.get("GROQ_API_KEY_2"),
        "model": os.environ.get("GROQ_MODEL_2", "llama-3.1-8b-instant"),
        "base_url": os.environ.get("GROQ_BASE_URL_2", "https://api.groq.com/openai/v1"),
    }


def _build_validation_prompt(
    recommendation: Dict[str, Any],
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
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
- Rainfall: {weather.get('rainfall_1h') or weather.get('rainfall_3h') or 0} mm

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


def _validate_and_normalize_validation_response(
    ai_response: Optional[Dict[str, Any]],
    farm_context: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    na = "Not available"

    if ai_response is None:
        return {
            "validation_status": "not_recommended",
            "overall_score": 0,
            "summary": "Validation unavailable - Groq API #2 not accessible",
            "validations": [
                {
                    "aspect": "Overall",
                    "status": "fail",
                    "message": "Groq API #2 unavailable - cannot validate recommendations",
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
            "disclaimer": "Groq API #2 unavailable - validation not performed.",
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
        "source": "groq_2",
    }


def validate_recommendation(
    recommendation: Dict[str, Any],
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Validate crop recommendation using Groq API #2.

    Replaces Gemini validation pipeline. Uses GROQ_API_KEY_2.

    Args:
        recommendation: The recommendation result from Mistral
        farm_context: Farm context dictionary
        weather: Current weather data dictionary
        language: Response language ('en' or 'hi')

    Returns:
        Validation result dictionary
    """
    config = _get_groq_config_2()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = f"groq2_val:{recommendation.get('top_crop', {}).get('name', '')}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _groq_cache_2:
        logger.info("Returning cached Groq #2 validation")
        return _groq_cache_2[cache_key]

    if api_key and api_key != "your_groq_api_key_2_here":
        prompt = _build_validation_prompt(recommendation, farm_context, weather, language)
        ai_response = _call_groq_api(prompt, api_key, model, base_url)
    else:
        logger.warning("Groq API key 2 not configured - validation not available")
        ai_response = None

    result = _validate_and_normalize_validation_response(ai_response, farm_context, language)

    _groq_cache_2[cache_key] = result
    return result


# =============================================================================
# GROQ #3 - Crop Guide Parts 1 & 2 (replaces Gemini parts 1 & 2)
# =============================================================================

_groq_cache_3 = TTLCache(maxsize=100, ttl=3600)


def _get_groq_config_3() -> Dict[str, Optional[str]]:
    """Retrieve Groq API #3 configuration (crop guide) from environment variables."""
    return {
        "api_key": os.environ.get("GROQ_API_KEY_3"),
        "model": os.environ.get("GROQ_MODEL_3", "llama-3.1-8b-instant"),
        "base_url": os.environ.get("GROQ_BASE_URL_3", "https://api.groq.com/openai/v1"),
    }


def _build_crop_guide_prompt_part1(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
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


def _build_crop_guide_prompt_part2(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
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


def _normalize_crop_guide_part1(
    ai_response: Optional[Dict[str, Any]],
    crop_name: str,
) -> Dict[str, Any]:
    na = "Not available"

    if ai_response is None:
        return {
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

    return {**ai_response, "source": "groq_3"}


def _normalize_crop_guide_part2(
    ai_response: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    na = "Not available"

    if ai_response is None:
        return {
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
            "disclaimer": "Groq API #3 unavailable - crop guide not available.",
            "source": "not_available",
        }

    return {**ai_response, "source": "groq_3"}


def get_crop_guide_part1(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get Part 1 of crop guide (growing & preparation) using Groq API #3.

    Replaces Gemini crop guide part 1. Uses GROQ_API_KEY_3.
    """
    config = _get_groq_config_3()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = f"groq3_guide1:{crop_name}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _groq_cache_3:
        logger.info("Returning cached Groq #3 crop guide part 1")
        return _groq_cache_3[cache_key]

    if api_key and api_key != "your_groq_api_key_3_here":
        prompt = _build_crop_guide_prompt_part1(
            crop_name, farm_context, weather, language
        )
        ai_response = _call_groq_api(prompt, api_key, model, base_url, max_tokens=4000)
    else:
        logger.warning("Groq API key 3 not configured - crop guide part 1 not available")
        ai_response = None

    result = _normalize_crop_guide_part1(ai_response, crop_name)

    _groq_cache_3[cache_key] = result
    return result


def get_crop_guide_part2(
    crop_name: str,
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get Part 2 of crop guide (protection, harvest, post-harvest) using Groq API #3.

    Replaces Gemini crop guide part 2. Uses GROQ_API_KEY_3.
    """
    config = _get_groq_config_3()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = f"groq3_guide2:{crop_name}:{farm_context.get('state', '')}:{farm_context.get('district', '')}:{language}"
    if cache_key in _groq_cache_3:
        logger.info("Returning cached Groq #3 crop guide part 2")
        return _groq_cache_3[cache_key]

    if api_key and api_key != "your_groq_api_key_3_here":
        prompt = _build_crop_guide_prompt_part2(
            crop_name, farm_context, weather, language
        )
        ai_response = _call_groq_api(prompt, api_key, model, base_url, max_tokens=4000)
    else:
        logger.warning("Groq API key 3 not configured - crop guide part 2 not available")
        ai_response = None

    result = _normalize_crop_guide_part2(ai_response)

    _groq_cache_3[cache_key] = result
    return result


# =============================================================================
# GROQ CROP RECOMMENDATION FALLBACK (used when Mistral is unavailable)
# =============================================================================

_groq_recommend_cache = TTLCache(maxsize=100, ttl=3600)


def _build_groq_recommend_crops_prompt(
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build a prompt for Groq to recommend crops when Mistral is unavailable.
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

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Recommend exactly one primary crop and exactly two alternative crops based ONLY on the farmer's actual inputs and current weather.

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


def recommend_crops_groq(
    farm_context: Dict[str, Any],
    weather: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Get crop recommendations from Groq as a fallback when Mistral is unavailable.

    Returns the same structure as Mistral's recommend_crops() so the caller
    can use it interchangeably.
    """
    config = _get_groq_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"

    cache_key = (
        f"groq_recommend:{farm_context.get('state', '')}:{farm_context.get('district', '')}"
        f":{farm_context.get('season', '')}:{farm_context.get('soil_type', '')}"
        f":{farm_context.get('n', '')}:{farm_context.get('p', '')}:{farm_context.get('k', '')}"
        f":{farm_context.get('ph', '')}:{farm_context.get('irrigation', '')}:{language}"
    )
    if cache_key in _groq_recommend_cache:
        logger.info("Returning cached Groq crop recommendation")
        return _groq_recommend_cache[cache_key]

    if api_key and api_key != "your_groq_api_key_here":
        prompt = _build_groq_recommend_crops_prompt(farm_context, weather, language)
        ai_response = _call_groq_api(prompt, api_key, model, base_url)
    else:
        logger.warning("Groq API key not configured - crop recommendation fallback not available")
        ai_response = None

    if ai_response is None:
        result = {
            "status": "error",
            "error": "Groq fallback unavailable - crop recommendation could not be generated.",
            "top_crop": {"name": None},
            "alternatives": [{"name": None}, {"name": None}],
            "source": "groq_fallback_unavailable",
        }
    else:
        # Normalize the response similar to Mistral's validator
        status = ai_response.get("status", "error")
        top_crop = ai_response.get("top_crop", {}) or ai_response.get("top_cock", {}) or {}
        alternatives = ai_response.get("alternatives", []) or []

        top_name = top_crop.get("name") if isinstance(top_crop, dict) else None
        alt_names = []
        alt_scores = []
        for alt in alternatives[:2]:
            if isinstance(alt, dict):
                alt_names.append(alt.get("name"))
                alt_scores.append(int(alt.get("suitability_score", na)) if isinstance(alt.get("suitability_score"), (int, float)) else na)
            else:
                alt_names.append(None)
                alt_scores.append(na)

        while len(alt_names) < 2:
            alt_names.append(None)
            alt_scores.append(na)

        if not top_name or not isinstance(top_name, str) or top_name.strip() == "":
            result = {
                "status": "error",
                "error": "Groq did not return a valid primary crop name.",
                "top_crop": {"name": None},
                "alternatives": [{"name": None}, {"name": None}],
                "source": "groq_fallback",
            }
        else:
            valid_alternatives = []
            for i, name in enumerate(alt_names):
                if name and isinstance(name, str) and name.strip() != "":
                    valid_alternatives.append({
                        "name": name.strip(),
                        "suitability_score": alt_scores[i] if i < len(alt_scores) else na,
                    })
                else:
                    valid_alternatives.append({
                        "name": None,
                        "suitability_score": na,
                    })

            if any(alt["name"] is None for alt in valid_alternatives):
                result = {
                    "status": "error",
                    "error": "Groq did not return two valid alternative crop names.",
                    "top_crop": {
                        "name": top_name.strip(),
                        "soil_compatibility": int(top_crop.get("soil_compatibility", na)) if isinstance(top_crop.get("soil_compatibility"), (int, float)) else na,
                        "seasonal_compatibility": int(top_crop.get("seasonal_compatibility", na)) if isinstance(top_crop.get("seasonal_compatibility"), (int, float)) else na,
                        "regional_compatibility": int(top_crop.get("regional_compatibility", na)) if isinstance(top_crop.get("regional_compatibility"), (int, float)) else na,
                        "cultivation_risks": top_crop.get("cultivation_risks", [na]) if isinstance(top_crop.get("cultivation_risks"), list) else [na],
                        "suitability_score": int(top_crop.get("suitability_score", na)) if isinstance(top_crop.get("suitability_score"), (int, float)) else na,
                    },
                    "alternatives": valid_alternatives,
                    "source": "groq_fallback",
                }
            else:
                result = {
                    "status": "success",
                    "top_crop": {
                        "name": top_name.strip(),
                        "soil_compatibility": int(top_crop.get("soil_compatibility", na)) if isinstance(top_crop.get("soil_compatibility"), (int, float)) else na,
                        "seasonal_compatibility": int(top_crop.get("seasonal_compatibility", na)) if isinstance(top_crop.get("seasonal_compatibility"), (int, float)) else na,
                        "regional_compatibility": int(top_crop.get("regional_compatibility", na)) if isinstance(top_crop.get("regional_compatibility"), (int, float)) else na,
                        "cultivation_risks": top_crop.get("cultivation_risks", [na]) if isinstance(top_crop.get("cultivation_risks"), list) else [na],
                        "suitability_score": int(top_crop.get("suitability_score", na)) if isinstance(top_crop.get("suitability_score"), (int, float)) else na,
                    },
                    "alternatives": valid_alternatives,
                    "source": "groq_fallback",
                }

    _groq_recommend_cache[cache_key] = result
    return result