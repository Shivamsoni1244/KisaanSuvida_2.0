"""
services/disease_advisory_service.py - Gemini AI Disease Advisory service

Generates farmer-friendly disease advisory using Google's Gemini API.
This service is INDEPENDENT from crop recommendation (Mistral) and KisaanBot
(Groq). Gemini does NOT identify or override the CNN prediction; it only
provides advisory for the disease already identified by the CNN.

Environment variables:
    GEMINI_API_KEY          - Gemini API key
    GEMINI_DISEASE_MODEL    - Gemini model id (default: gemini-3.8-flash)
    GEMINI_BASE_URL         - Gemini API base URL (default:
                              https://generativelanguage.googleapis.com/v1beta)
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
from services.groq_service import _call_groq_api

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "gemini-1.5-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1"

# Advisory responses cache (TTL: 1 hour, max 200 entries)
_advisory_cache = TTLCache(maxsize=200, ttl=3600)

SUPPORTED_LANGUAGES = {"en", "hi", "hinglish"}

# JSON schema contract communicated to the model
_ADVISORY_SCHEMA = {
    "disease_overview": "Short explanation of the disease (2-4 sentences)",
    "symptoms": ["List of common visible symptoms"],
    "causes_and_spread": "Possible causes and conditions under which it spreads",
    "treatment_options": ["Treatment options (general, no specific doses)"],
    "organic_management": ["Organic / biological management options"],
    "prevention_methods": ["Prevention methods"],
    "immediate_actions": ["Immediate actions the farmer should take"],
    "disclaimer": "Safety disclaimer",
}


def _get_gemini_disease_config() -> Dict[str, Optional[str]]:
    """Retrieve Gemini disease advisory configuration from environment variables."""
    return {
        "api_key": os.environ.get("GEMINI_API_KEY"),
        "model": os.environ.get("GEMINI_DISEASE_MODEL", DEFAULT_MODEL_ID),
        "base_url": os.environ.get("GEMINI_BASE_URL", DEFAULT_BASE_URL),
    }


def _normalize_language(language: Optional[str]) -> str:
    lang = (language or "en").strip().lower()
    if lang in ("hindi", "hi"):
        return "hi"
    if lang in ("hinglish", "hi-en", "hien"):
        return "hinglish"
    return "en"


def _language_instruction(language: str) -> str:
    if language == "hi":
        return (
            "Respond in Hindi (हिन्दी script). Use simple, farmer-friendly Hindi."
        )
    if language == "hinglish":
        return (
            "Respond in Hinglish (Hindi written in English/latin script, as spoken "
            "by farmers). Keep it simple and farmer-friendly."
        )
    return "Respond in English."


def _build_disease_advisory_prompt(
    crop_name: str,
    disease_name: str,
    scientific_name: Optional[str],
    confidence: float,
    language: str,
    symptoms: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Build a structured prompt for Gemini disease advisory.
    Explicitly instructs Gemini NOT to re-identify or override the CNN prediction.
    """
    lang_instruction = _language_instruction(language)
    scientific = scientific_name or "Not available"
    conf_pct = round(confidence * 100, 1)
    symptoms_note = f"\nFarmer-reported symptoms: {symptoms}" if symptoms else ""
    location_note = f"\nFarmer location: {location}" if location else ""

    prompt = f"""You are an expert agricultural advisor for Indian farmers. Provide a DISEASE ADVISORY for a crop disease that has ALREADY been identified by a CNN image-classification model.

{lang_instruction}

CRITICAL INSTRUCTIONS:
- The CNN model has already identified the disease. Do NOT re-identify, re-diagnose, or override the CNN prediction.
- Do NOT claim the image-based prediction is a laboratory-confirmed diagnosis.
- Accept the CNN identification as given and provide advisory only.
- Never invent specific pesticide doses, application schedules, or unregistered pesticides.
- Refer to approved product labels and local agricultural/KVK guidance for chemical application.
- When uncertain, explicitly say so.
- Keep responses concise and farmer-friendly.

CNN IDENTIFICATION (accept as given, do not question):
- Crop: {crop_name}
- Disease: {disease_name}
- Scientific name: {scientific}
- CNN confidence: {conf_pct}% (a model softmax score, not a calibrated probability)
{symptoms_note}
{location_note}

TASK: Generate a disease advisory covering these sections:
1. disease_overview: Short explanation of the disease (2-4 sentences).
2. symptoms: Common visible symptoms (list).
3. causes_and_spread: Possible causes and conditions under which it spreads.
4. treatment_options: Treatment options (general guidance, no specific doses).
5. organic_management: Organic / biological management options (list).
6. prevention_methods: Prevention methods (list).
7. immediate_actions: Immediate actions the farmer should take (list).
8. disclaimer: Safety disclaimer stating this is AI-generated advisory, not a lab diagnosis, and to consult local KVK/agricultural experts.

Return ONLY valid JSON with this exact structure (no markdown code blocks, no extra text):
{json.dumps(_ADVISORY_SCHEMA, indent=2)}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks
- Base all advice on Indian agricultural conditions
- Hindi/Hinglish content must be simple and farmer-friendly
- Do not invent pesticide doses or schedules
- If information is uncertain, state it explicitly
"""

    return prompt


def _call_gemini_disease_api(
    prompt: str, api_key: str, model: str, base_url: str
) -> Optional[str]:
    """
    Call the Gemini disease advisory API. Returns raw text content or None on failure.
    """
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
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

        logger.info("GEMINI RAW RESPONSE: %s", content[:500] if content else "EMPTY")

        if not content:
            logger.error("Gemini disease advisory returned empty content")
            record_api_call(
                provider="gemini_disease",
                model=model,
                input_text=prompt,
                output_text="",
                latency_ms=latency_ms,
                success=False,
                error="Empty response",
            )
            return None

        record_api_call(
            provider="gemini_disease",
            model=model,
            input_text=prompt,
            output_text=content,
            latency_ms=latency_ms,
            success=True,
        )
        return content

    except requests.exceptions.Timeout:
        logger.error("Gemini disease advisory API timed out")
        record_api_call(
            provider="gemini_disease",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=30000,
            success=False,
            error="Timeout",
        )
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Gemini disease advisory API connection error")
        record_api_call(
            provider="gemini_disease",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error="Connection error",
        )
        return None
    except requests.exceptions.HTTPError as e:
        if e.response is not None:
            if e.response.status_code == 401:
                logger.error("Gemini disease advisory authentication failed")
            elif e.response.status_code == 429:
                logger.error("Gemini disease advisory rate limit exceeded")
            else:
                logger.error("Gemini disease advisory HTTP error: %s", e)
        record_api_call(
            provider="gemini_disease",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None
    except Exception as e:
        logger.error("Unexpected error calling Gemini disease advisory API: %s", e)
        record_api_call(
            provider="gemini_disease",
            model=model,
            input_text=prompt,
            output_text="",
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return None


def _parse_advisory_json(content: str) -> Optional[Dict[str, Any]]:
    """Parse Gemini response text into a dict, tolerating markdown fences and extra text."""
    if not content:
        return None

    text = content.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Remove markdown code fences (```json, ```, ~~~ etc.)
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find the first { and last } to extract JSON object
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Try fixing common issues: trailing commas, single quotes
        fixed = re.sub(r",\s*}", "}", candidate)  # remove trailing comma before }
        fixed = fixed.replace("'", '"')  # single quotes to double quotes
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    return None


def _fallback_advisory(
    crop_name: str,
    disease_name: str,
    language: str,
) -> Dict[str, Any]:
    """Build a safe fallback advisory when Gemini is unavailable."""
    na = "Not available"
    if language == "hi":
        overview = f"{crop_name} में {disease_name} रोग की पहचान हुई है। यह एक AI-आधारित अनुमान है, प्रयोगशाला-पुष्टि निदान नहीं।"
        symptoms = ["पत्तियों पर धब्बे या रंग परिवर्तन", "पत्तियों का पीला पड़ना या सूखना"]
        causes = "रोग के फैलने के लिए मौसम, नमी और फसल की स्थिति जिम्मेदार हो सकते हैं।"
        treatment = ["किसी कृषि विशेषज्ञ या केवीके से संपर्क करें", "अनुमोदित उत्पाद लेबल के अनुसार ही दवा का उपयोग करें"]
        organic = ["जैविक खाद और नीम-आधारित उपचार का उपयोग करें"]
        prevention = ["फसल चक्र अपनाएं", "खेत में साफ-सफाई रखें"]
        actions = ["स्पष्ट पत्ती की फोटो खींचकर फिर से जांच कराएं", "स्थानीय कृषि अधिकारी से सलाह लें"]
        disclaimer = "यह सलाह केवल AI-जनित है। प्रयोगशाला निदान नहीं है। केवीके/कृषि विशेषज्ञ से संपर्क करें।"
    elif language == "hinglish":
        overview = f"{crop_name} mein {disease_name} rog ki pehchan hui hai. Ye AI-based estimate hai, lab-confirmed diagnosis nahi."
        symptoms = ["Patte par dhabbe ya rang parivartan", "Patte ka peela hona ya sukna"]
        causes = "Rog phalne ke liye mausam, nami aur fasal ki sthiti zimmedar ho sakte hain."
        treatment = ["Kisi krishi visheshagya ya KVK se sampark karein", "Anumodit product label ke anusar hi dawa ka upyog karein"]
        organic = ["Jaivik khad aur neem-based upchar ka upyog karein"]
        prevention = ["Fasal chakra apnayein", "Khet mein saf-safai rakhein"]
        actions = ["Spasht patti ki photo khiche aur phir se jaanch karayein", "Staniya krishi adhikari se salah lein"]
        disclaimer = "Ye salah sirf AI-generated hai. Lab diagnosis nahi hai. KVKE/krishi visheshagya se sampark karein."
    else:
        overview = f"{crop_name} with {disease_name} has been identified by the CNN model. This is an AI-based estimate, not a laboratory-confirmed diagnosis."
        symptoms = ["Spots or discoloration on leaves", "Leaf yellowing or drying"]
        causes = "Weather, humidity, and crop condition may contribute to disease development and spread."
        treatment = ["Consult a local agricultural expert or KVK", "Use any chemical only as per approved product labels"]
        organic = ["Use organic manure and neem-based treatments"]
        prevention = ["Practice crop rotation", "Keep the field clean and weed-free"]
        actions = ["Retake a clear, well-lit photo of the leaf and re-check", "Consult local agricultural officers"]
        disclaimer = "This advisory is AI-generated only, not a lab diagnosis. Consult local KVK/agricultural experts."

    return {
        "disease_overview": overview,
        "symptoms": symptoms if isinstance(symptoms, list) else [symptoms],
        "causes_and_spread": causes,
        "treatment_options": treatment if isinstance(treatment, list) else [treatment],
        "organic_management": organic if isinstance(organic, list) else [organic],
        "prevention_methods": prevention if isinstance(prevention, list) else [prevention],
        "immediate_actions": actions if isinstance(actions, list) else [actions],
        "disclaimer": disclaimer,
        "source": "fallback",
    }


def get_disease_advisory(
    crop_name: str,
    disease_name: str,
    scientific_name: Optional[str] = None,
    confidence: float = 0.0,
    language: str = "en",
    symptoms: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate disease advisory using Gemini API, falling back to Groq if Gemini fails.
    """
    language = _normalize_language(language)

    # Cache key
    cache_key = (
        f"disease_adv:{crop_name}:{disease_name}:{scientific_name or ''}:"
        f"{round(confidence, 2)}:{language}:{symptoms or ''}:{location or ''}"
    )
    if cache_key in _advisory_cache:
        logger.info("Returning cached disease advisory")
        return _advisory_cache[cache_key]

    config = _get_gemini_disease_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    na = "Not available"
    advisory_error = ""

    if api_key and api_key.strip() and api_key not in ("your_gemini_api_key_here", ""):
        prompt = _build_disease_advisory_prompt(
            crop_name=crop_name,
            disease_name=disease_name,
            scientific_name=scientific_name,
            confidence=confidence,
            language=language,
            symptoms=symptoms,
            location=location,
        )
        try:
            advisory_text = _call_gemini_disease_api(prompt, api_key, model, base_url)
            advisory = _parse_advisory_json(advisory_text) if advisory_text else None
            if advisory:
                advisory["source"] = "gemini"
                _advisory_cache[cache_key] = advisory
                return advisory
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Gemini disease advisory failed")
            advisory_error = "Gemini advisory unavailable. Trying alternative model."
    else:
        advisory_error = "Gemini API key missing or invalid. Trying alternative model."

    # ---- Try Groq fallback ----
    groq_key = os.getenv("GROQ_API_KEY_3") or os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL_3") or os.getenv("GROQ_MODEL_2") or os.getenv("GROQ_MODEL")
    groq_base_url = os.getenv("GROQ_BASE_URL_3") or os.getenv("GROQ_BASE_URL_2") or os.getenv("GROQ_BASE_URL")
    if groq_key and groq_model:
        try:
            prompt = _build_disease_advisory_prompt(
                crop_name=crop_name,
                disease_name=disease_name,
                scientific_name=scientific_name,
                confidence=confidence,
                language=language,
                symptoms=symptoms,
                location=location,
            )
            groq_response = _call_groq_api(prompt, groq_key, groq_model, groq_base_url)
            advisory = groq_response if groq_response else None
            if advisory:
                advisory["source"] = "groq"
                _advisory_cache[cache_key] = advisory
                return advisory
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Groq disease advisory failed")
            advisory_error = advisory_error + " Groq also failed."
    else:
        advisory_error = advisory_error + " Groq credentials not configured."

    # Final fallback
    advisory = _fallback_advisory(crop_name, disease_name, language)
    advisory["source"] = "fallback"
    _advisory_cache[cache_key] = advisory
    return advisory

