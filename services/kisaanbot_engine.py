"""
services/kisaanbot_engine.py - KisaanBot conversational AI engine (RAG + MySQL + Groq).

Architecture:
- ChromaDB: application knowledge base (RAG)
- MySQL: authenticated farmer's personal history (recommendations, suitability)
- Flask session: conversation memory (last discussed crop, recent messages)
- Groq: LLM for response generation

The engine processes each query through:
1. Language detection
2. Greeting handling (predefined, no LLM/DB)
3. Intent classification
4. Out-of-scope validation (predefined refusal, no LLM)
5. Context building (ChromaDB + MySQL + session)
6. Groq LLM response generation
7. Dynamic suggestion generation
8. Conversation context update

No hardcoded crop names — all crop names come from actual farmer records.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import requests

from services.prompt_templates import (
    get_system_prompt,
    get_greeting_response,
    get_out_of_scope_message,
    get_missing_history_message,
    build_user_prompt,
)
from services.intent_classifier import classify_intent
from services.context_builder import build_context, update_conversation_context
from services.suggestion_engine import (
    generate_suggestions,
    get_initial_suggestions,
    build_suggestions_from_context,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq configuration
# ---------------------------------------------------------------------------
def _get_groq_config() -> Dict[str, Optional[str]]:
    return {
        "api_key": os.environ.get("GROQ_API_KEY"),
        "model": os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
        "base_url": os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def process_kisaanbot_query(
    query: str,
    language: str = "en",
    farm_context: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    session_obj: Any = None,
) -> Dict[str, Any]:
    """
    Main entry point for processing a KisaanBot query.

    Args:
        query: The farmer's message.
        language: Language hint ('en', 'hi', 'hinglish').
        farm_context: Deprecated - kept for backward compatibility.
        user_id: Authenticated user's ID from session (required for personal history).
        session_obj: Flask session object for conversation memory.

    Returns:
        Dict with reply, language, intent, suggestions, context.
    """
    try:
        return _process_kisaanbot_query_internal(
            query=query,
            language=language,
            farm_context=farm_context,
            user_id=user_id,
            session_obj=session_obj,
        )
    except Exception as exc:
        logger.error("Unexpected error in process_kisaanbot_query: %s", exc)
        lang = _normalise_language(language)
        fallback = _fallback_reply("", lang, "general_app", {})
        _store_conversation(session_obj, query, fallback)
        return {
            "reply": fallback,
            "language": lang,
            "intent": "general_app",
            "suggestions": [],
            "context": {},
        }


def _process_kisaanbot_query_internal(
    query: str,
    language: str = "en",
    farm_context: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    session_obj: Any = None,
) -> Dict[str, Any]:
    # Normalise language
    lang = _normalise_language(language)

    # Empty message -> treat as help/opening
    if not query or not query.strip():
        return _handle_empty_query(lang, session_obj, user_id)

    # 1. Greeting check (predefined, no LLM, no DB)
    greeting_reply = get_greeting_response(query, lang)
    if greeting_reply:
        suggestions = get_initial_suggestions(
            language=lang,
            farmer_records=_get_farmer_records_light(user_id) if user_id else None,
        )
        _store_conversation(session_obj, query, greeting_reply)
        return {
            "reply": greeting_reply,
            "language": lang,
            "intent": "greeting",
            "suggestions": suggestions,
            "context": {},
        }

    # 2. Classify intent
    conv_ctx = _get_conversation_context(session_obj) if session_obj else {}
    last_crop = conv_ctx.get("last_discussed_crop")
    recent_context_str = _format_recent(conv_ctx.get("recent_messages", []))

    intent_result = classify_intent(
        query,
        language=lang,
        has_farmer_history=bool(user_id),
        last_discussed_crop=last_crop,
        conversation_context=recent_context_str,
    )
    detected_lang = intent_result.get("language", lang)
    intent = intent_result.get("intent", "general_app")
    is_unrelated = intent_result.get("is_unrelated", False)

    # 3. Out-of-scope validation (no LLM call)
    if is_unrelated and intent == "unrelated":
        refusal = get_out_of_scope_message(detected_lang)
        suggestions = get_initial_suggestions(
            language=detected_lang,
            farmer_records=_get_farmer_records_light(user_id) if user_id else None,
        )
        _store_conversation(session_obj, query, refusal)
        return {
            "reply": refusal,
            "language": detected_lang,
            "intent": "unrelated",
            "suggestions": suggestions,
            "context": {},
        }

    # 4. Build context (ChromaDB + MySQL + session)
    if not user_id:
        # No authenticated user — cannot provide personal history
        context = _build_guest_context(query, detected_lang, session_obj)
    else:
        context = build_context(
            question=query,
            user_id=user_id,
            language=detected_lang,
            session=session_obj,
        )

    # 5. Validate sufficient relevant information
    if not _has_sufficient_context(context, intent):
        missing_msg = get_missing_history_message("general", detected_lang)
        suggestions = get_initial_suggestions(
            language=detected_lang,
            farmer_records=context.get("farmer_records", {}) if user_id else None,
        )
        _store_conversation(session_obj, query, missing_msg)
        return {
            "reply": missing_msg,
            "language": detected_lang,
            "intent": intent,
            "suggestions": suggestions,
            "context": {},
        }

    # 6. Generate response via Groq LLM
    reply = _generate_llm_response(
        question=query,
        context=context,
        language=detected_lang,
        intent=intent,
    )

    # 7. Generate dynamic suggestions
    suggestions = build_suggestions_from_context(context, language=detected_lang)

    # 8. Update conversation memory
    referenced_crop = intent_result.get("referenced_crop") or last_crop
    activity = intent_result.get("module", "general_app")
    _store_conversation(session_obj, query, reply, crop=referenced_crop, activity=activity)

    return {
        "reply": reply,
        "language": detected_lang,
        "intent": intent,
        "suggestions": suggestions,
        "context": {
            "farmer_records": context.get("farmer_records", {}),
            "referenced_crop": referenced_crop,
        },
    }


def _handle_empty_query(
    lang: str,
    session_obj: Any,
    user_id: Optional[int],
) -> Dict[str, Any]:
    """Handle an empty query — return a welcome message with suggestions."""
    welcome = {
        "en": "Namaste! Welcome to KisaanBot. I can help you understand and use Kisaan Suvidha, explore your previous recommendations, check your analysis results and access your cultivation guides.",
        "hi": "नमस्ते! किसानसुविधा के AI सहायक KisaanBot में आपका स्वागत है। मैं आपकी फसल सिफारिश, उपयुक्तता विश्लेषण, रोग निदान, खेती गाइड और सेव्ड रिकॉर्ड में मदद कर सकता हूँ।",
        "hinglish": "Namaste! Welcome to KisaanBot. Main aapki Kisaan Suvidha ko samajhne aur use karne mein madad kar sakta hoon, aapke pichle recommendations explore karne mein, analysis results check karne mein aur cultivation guides access karne mein.",
    }.get(lang, "Namaste! Welcome to KisaanBot. I can help you understand and use Kisaan Suvidha, explore your previous recommendations, check your analysis results and access your cultivation guides.")

    suggestions = get_initial_suggestions(
        language=lang,
        farmer_records=_get_farmer_records_light(user_id) if user_id else None,
    )
    _store_conversation(session_obj, "", welcome)
    return {
        "reply": welcome,
        "language": lang,
        "intent": "greeting",
        "suggestions": suggestions,
        "context": {},
    }


# ---------------------------------------------------------------------------
# Initial suggestions (chatbot first opening)
# ---------------------------------------------------------------------------
def get_initial_suggestions_for_user(
    language: str = "en",
    user_id: Optional[int] = None,
) -> List[str]:
    """Get initial suggestions when the chatbot first opens."""
    records = _get_farmer_records_light(user_id) if user_id else None
    return get_initial_suggestions(language=language, farmer_records=records)


# ---------------------------------------------------------------------------
# Groq LLM generation
# ---------------------------------------------------------------------------
def _generate_llm_response(
    question: str,
    context: Dict[str, Any],
    language: str,
    intent: str,
) -> str:
    """Call Groq LLM to generate the response.

    Falls back to a predefined message if Groq is unavailable.
    """
    config = _get_groq_config()
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    if not api_key or api_key == "your_groq_api_key_here":
        logger.warning("Groq API key not configured")
        return _fallback_reply(question, language, intent, context)

    system_prompt = get_system_prompt(language)
    user_prompt = build_user_prompt(
        question=question,
        application_context=context.get("application_context", ""),
        farmer_context=context.get("farmer_context", ""),
        conversation_context=context.get("conversation_context", ""),
        language=language,
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 500,
    }

    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            return content.strip()
    except requests.exceptions.Timeout:
        logger.error("Groq API timeout")
    except requests.exceptions.ConnectionError:
        logger.error("Groq API connection error")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.error("Groq API rate limit exceeded")
        elif e.response.status_code == 401:
            logger.error("Groq API authentication failed")
        else:
            logger.error("Groq API HTTP error: %s", e)
    except Exception as e:
        logger.error("Unexpected error calling Groq: %s", e)

    return _fallback_reply(question, language, intent, context)


def _fallback_reply(
    question: str,
    language: str,
    intent: str,
    context: Dict[str, Any],
) -> str:
    """Fallback reply when Groq is unavailable."""
    farmer_records = context.get("farmer_records", {})
    lang = language

    if intent == "recommendation" and farmer_records.get("latest_recommendation"):
        rec = farmer_records["latest_recommendation"]
        crop = rec.get("crop_name", "your crop")
        if lang == "hi":
            return f"मैंने {crop} के बारे में आपकी सेव्ड सिफारिश पाई है, लेकिन फिलहाल विस्तृत उत्तर जनरेट नहीं कर पा रहा हूँ। कृपया बाद में पुनः प्रयास करें।"
        elif lang == "hinglish":
            return f"I found your saved recommendation for {crop}, but I can't generate a detailed response right now. Please try again later."
        return f"I found your saved recommendation for {crop}, but I can't generate a detailed response right now. Please try again later."

    if lang == "hi":
        return "मैं फिलहाल उत्तर जनरेट नहीं कर पा रहा हूँ। कृपया बाद में पुनः प्रयास करें।"
    elif lang == "hinglish":
        return "Main filhaal response generate nahi kar pa raha hoon. Please try again later."
    return "I'm unable to generate a response right now. Please try again later."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise_language(language: str) -> str:
    lang = (language or "en").lower().strip()
    if lang in ["hi", "hindi", "हिन्दी"]:
        return "hi"
    if lang in ["hinglish", "hi-en"]:
        return "hinglish"
    return "en"


def _has_sufficient_context(context: Dict[str, Any], intent: str) -> bool:
    """Validate that sufficient relevant information exists before calling Groq.

    For greetings and general app questions, application docs are sufficient.
    For personal questions, we need farmer records.
    """
    if intent in ("greeting", "unrelated"):
        return True

    app_ctx = context.get("application_context", "")
    farmer_ctx = context.get("farmer_context", "")

    # If the intent is personal (recommendation, suitability) and we have no
    # farmer records and no application docs, we can't answer meaningfully.
    if intent in ("recommendation", "suitability", "cultivation_guide"):
        has_records = (
            context.get("farmer_records", {}).get("has_recommendation")
            or context.get("farmer_records", {}).get("has_suitability")
        )
        if not has_records and not farmer_ctx.strip():
            # Still allow if we have application docs about the topic
            if not app_ctx.strip():
                return False

    return bool(app_ctx.strip() or farmer_ctx.strip())


def _get_farmer_records_light(user_id: int) -> Optional[Dict[str, Any]]:
    """Lightweight farmer record retrieval for suggestions only."""
    from services.context_builder import get_farmer_records
    try:
        return get_farmer_records(user_id, "general_app", limit=3)
    except Exception as e:
        logger.error("Failed to get light farmer records: %s", e)
        return None


def _get_conversation_context(session_obj: Any) -> Dict[str, Any]:
    from services.context_builder import get_conversation_context
    return get_conversation_context(session_obj)


def _store_conversation(
    session_obj: Any,
    user_message: str,
    bot_reply: str,
    crop: Optional[str] = None,
    activity: Optional[str] = None,
) -> None:
    from services.context_builder import update_conversation_context
    if session_obj is not None:
        update_conversation_context(session_obj, user_message, bot_reply, crop=crop, activity=activity)


def _format_recent(messages: List[Dict[str, str]]) -> str:
    from services.context_builder import _format_recent_messages
    return _format_recent_messages(messages)


def _build_guest_context(
    query: str,
    language: str,
    session_obj: Any,
) -> Dict[str, Any]:
    """Build context for unauthenticated users (application docs only)."""
    from services.kb_loader import query_knowledge_base
    docs = query_knowledge_base(query, n_results=4)
    app_ctx = "\n\n".join(f"[{d.get('title', '')}] {d.get('content', '')}" for d in docs) if docs else ""
    return {
        "application_context": app_ctx,
        "farmer_context": "User not authenticated — personal history unavailable.",
        "conversation_context": _format_recent(
            _get_conversation_context(session_obj).get("recent_messages", [])
        ) if session_obj else "No previous conversation.",
        "intent": {"intent": "general_app", "language": language},
        "farmer_records": {},
        "context_summary": "",
    }
