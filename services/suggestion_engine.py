"""
services/suggestion_engine.py - Dynamic suggestion engine for KisaanBot.

Generates contextual suggested questions based on:
- Current intent
- Latest crop recommendation (actual crop name from DB)
- Available suitability records
- Available cultivation guides
- Recent conversation context
- Language preference

All crop names come from actual farmer records — never hardcoded.
"""

import re
from typing import Any, Dict, List, Optional

from services.prompt_templates import SUGGESTION_TEMPLATES, get_fallback_suggestions

# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
def _fill_template(template: str, crop_name: Optional[str], language: str = "en") -> str:
    """Replace {crop_name} placeholder in a template."""
    if crop_name:
        return template.replace("{crop_name}", crop_name)
    return template.replace("{crop_name}", "my crop")


def _dedupe(suggestions: List[str]) -> List[str]:
    """Remove duplicate suggestions while preserving order."""
    seen: set = set()
    result: List[str] = []
    for s in suggestions:
        key = s.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(s)
    return result


# ---------------------------------------------------------------------------
# Main suggestion generation
# ---------------------------------------------------------------------------
def generate_suggestions(
    intent: str,
    language: str = "en",
    latest_crop: Optional[str] = None,
    has_suitability: bool = False,
    has_cultivation_guide: bool = False,
    recent_context: str = "",
    farmer_records: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Generate a list of suggested follow-up questions.

    Args:
        intent: Current classified intent (greeting, recommendation, suitability,
            cultivation_guide, disease_detection, history, general_app, unrelated).
        language: 'en', 'hi', or 'hinglish'.
        latest_crop: Actual crop name from the farmer's latest recommendation.
        has_suitability: Whether a suitability analysis exists.
        has_cultivation_guide: Whether a cultivation guide exists.
        recent_context: Recent conversation context string.
        farmer_records: Raw farmer records (for additional dynamic suggestions).

    Returns:
        A deduplicated list of 4-6 suggested question strings.
    """
    suggestions: List[str] = []

    # --- Greeting / initial opening ---
    if intent == "greeting":
        base = get_fallback_suggestions("greeting", language)
        # If farmer has history, prioritise personalised suggestions
        if farmer_records:
            if farmer_records.get("has_recommendation") and latest_crop:
                rec_templates = get_fallback_suggestions("recommendation", language)
                for t in rec_templates[:3]:
                    suggestions.append(_fill_template(t, latest_crop, language))
            if farmer_records.get("has_suitability") and latest_crop:
                sat_templates = get_fallback_suggestions("suitability", language)
                for t in sat_templates[:2]:
                    suggestions.append(_fill_template(t, latest_crop, language))
        # Fill remaining with general
        general = get_fallback_suggestions("general", language)
        for g in general:
            if len(suggestions) >= 6:
                break
            suggestions.append(g)
        return _dedupe(suggestions)[:6]

    # --- Unrelated / out of scope ---
    if intent == "unrelated":
        base = get_fallback_suggestions("general", language)
        if farmer_records and farmer_records.get("has_recommendation") and latest_crop:
            rec_templates = get_fallback_suggestions("recommendation", language)
            for t in rec_templates[:2]:
                suggestions.append(_fill_template(t, latest_crop, language))
        for b in base:
            if len(suggestions) >= 5:
                break
            suggestions.append(b)
        return _dedupe(suggestions)[:5]

    # --- Recommendation intent ---
    if intent == "recommendation" or (latest_crop and intent in ("follow_up", "general_app")):
        if latest_crop:
            rec_templates = get_fallback_suggestions("recommendation", language)
            for t in rec_templates:
                suggestions.append(_fill_template(t, latest_crop, language))
            if has_suitability:
                sat_templates = get_fallback_suggestions("suitability", language)
                for t in sat_templates[:2]:
                    suggestions.append(_fill_template(t, latest_crop, language))
            if has_cultivation_guide:
                cult_templates = get_fallback_suggestions("cultivation_guide", language)
                for t in cult_templates[:2]:
                    suggestions.append(_fill_template(t, latest_crop, language))
        else:
            # No crop known - general app suggestions
            suggestions.extend(get_fallback_suggestions("general", language))
        return _dedupe(suggestions)[:6]

    # --- Suitability intent ---
    if intent == "suitability":
        if latest_crop and has_suitability:
            sat_templates = get_fallback_suggestions("suitability", language)
            for t in sat_templates:
                suggestions.append(_fill_template(t, latest_crop, language))
        else:
            suggestions.extend(get_fallback_suggestions("general", language))
        return _dedupe(suggestions)[:6]

    # --- Cultivation guide intent ---
    if intent == "cultivation_guide":
        if latest_crop and has_cultivation_guide:
            cult_templates = get_fallback_suggestions("cultivation_guide", language)
            for t in cult_templates:
                suggestions.append(_fill_template(t, latest_crop, language))
        else:
            suggestions.extend(get_fallback_suggestions("general", language))
        return _dedupe(suggestions)[:6]

    # --- Disease detection intent ---
    if intent == "disease_detection":
        suggestions.extend(get_fallback_suggestions("disease_detection", language))
        return _dedupe(suggestions)[:6]

    # --- Follow-up intent ---
    if intent == "follow_up":
        if latest_crop:
            # Use recommendation templates as follow-ups default to last discussed crop
            rec_templates = get_fallback_suggestions("recommendation", language)
            for t in rec_templates[:3]:
                suggestions.append(_fill_template(t, latest_crop, language))
            if has_suitability:
                sat_templates = get_fallback_suggestions("suitability", language)
                for t in sat_templates[:2]:
                    suggestions.append(_fill_template(t, latest_crop, language))
        else:
            suggestions.extend(get_fallback_suggestions("general", language))
        return _dedupe(suggestions)[:6]

    # --- General app / default ---
    suggestions.extend(get_fallback_suggestions("general", language))
    if farmer_records and farmer_records.get("has_recommendation") and latest_crop:
        rec_templates = get_fallback_suggestions("recommendation", language)
        for t in rec_templates[:2]:
            suggestions.append(_fill_template(t, latest_crop, language))
    return _dedupe(suggestions)[:6]


# ---------------------------------------------------------------------------
# Initial suggestions (when chatbot first opens)
# ---------------------------------------------------------------------------
def get_initial_suggestions(
    language: str = "en",
    farmer_records: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Get suggestions shown when the chatbot first opens.

    If the farmer has previous activity, personalised suggestions are prioritised.
    """
    suggestions: List[str] = []

    if farmer_records:
        latest_crop = None
        if farmer_records.get("latest_recommendation"):
            latest_crop = farmer_records["latest_recommendation"].get("crop_name")

        if latest_crop:
            # Personalised: use actual crop name
            rec_templates = get_fallback_suggestions("recommendation", language)
            for t in rec_templates[:3]:
                suggestions.append(_fill_template(t, latest_crop, language))
            if farmer_records.get("has_suitability"):
                sat_templates = get_fallback_suggestions("suitability", language)
                for t in sat_templates[:2]:
                    suggestions.append(_fill_template(t, latest_crop, language))
        else:
            # Has records but no clear latest crop - general
            suggestions.extend(get_fallback_suggestions("general", language))

        # Always include a couple of general app questions
        general = get_fallback_suggestions("general", language)
        for g in general:
            if len(suggestions) >= 6:
                break
            suggestions.append(g)
    else:
        # No history - general app suggestions
        suggestions.extend(get_fallback_suggestions("general", language))

    return _dedupe(suggestions)[:6]


# ---------------------------------------------------------------------------
# Convenience: build suggestions from context builder output
# ---------------------------------------------------------------------------
def build_suggestions_from_context(
    context: Dict[str, Any],
    language: str = "en",
) -> List[str]:
    """Build suggestions from a full context dict (output of build_context)."""
    intent_result = context.get("intent", {})
    intent = intent_result.get("intent", "general_app")
    farmer_records = context.get("farmer_records", {})

    latest_crop = None
    if farmer_records.get("latest_recommendation"):
        latest_crop = farmer_records["latest_recommendation"].get("crop_name")

    has_suitability = farmer_records.get("has_suitability", False)
    has_cultivation_guide = farmer_records.get("has_cultivation_guide", False)
    recent_context = context.get("conversation_context", "")

    return generate_suggestions(
        intent=intent,
        language=language,
        latest_crop=latest_crop,
        has_suitability=has_suitability,
        has_cultivation_guide=has_cultivation_guide,
        recent_context=recent_context,
        farmer_records=farmer_records,
    )
