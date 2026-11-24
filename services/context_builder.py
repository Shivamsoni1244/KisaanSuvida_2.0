"""
services/context_builder.py - Context building for KisaanBot.

Combines three context layers:
1. APPLICATION CONTEXT - relevant ChromaDB documents (intent-filtered).
2. FARMER CONTEXT - relevant MySQL records for the authenticated user
   (intent-based retrieval, never all records).
3. CONVERSATION CONTEXT - recent session messages + last discussed crop/activity.

Only data relevant to the current question is included. Missing records are
explicitly marked as unavailable so the LLM never invents them.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from services.kb_loader import query_knowledge_base
from services.intent_classifier import classify_intent
from data.db import get_db
from mysql.connector import Error

logger = logging.getLogger(__name__)

# Intent -> ChromaDB category mapping for targeted retrieval
INTENT_CATEGORY_MAP: Dict[str, Optional[str]] = {
    "recommendation": "recommendation",
    "suitability": "suitability",
    "disease_detection": "disease",
    "cultivation_guide": "cultivation",
    "history": "history",
    "navigation": "navigation",
    "account": "account",
    "kisaanbot": "kisaanbot",
    "general_app": "overview",
    "greeting": "overview",
    "follow_up": None,
    "unrelated": None,
}


# ---------------------------------------------------------------------------
# Farmer record retrieval from MySQL
# ---------------------------------------------------------------------------
def get_farmer_records(
    user_id: int,
    intent: str,
    referenced_crop: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Retrieve only the farmer records relevant to the current intent.

    Never retrieves all records. Uses intent-based filtering.
    """
    records: Dict[str, Any] = {
        "latest_recommendation": None,
        "previous_recommendations": [],
        "latest_suitability": None,
        "previous_suitability": [],
        "cultivation_guide": None,
        "profile": None,
        "has_recommendation": False,
        "has_suitability": False,
        "has_cultivation_guide": False,
    }

    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)

        # User profile (always relevant for personalisation)
        cur.execute(
            """SELECT id, name, mobile, farm_size, soil_type, irrigation,
                      preferred_language, state_name, district_name
               FROM user_profiles WHERE id = %s""",
            (user_id,),
        )
        profile = cur.fetchone()
        if profile:
            records["profile"] = {
                "name": profile.get("name") or "Farmer",
                "farm_size": profile.get("farm_size") or "Not specified",
                "soil_type": profile.get("soil_type") or "Not specified",
                "irrigation": profile.get("irrigation") or "Not specified",
                "state": profile.get("state_name") or "Not specified",
                "district": profile.get("district_name") or "Not specified",
                "language": profile.get("preferred_language") or "en",
            }

        # Query crop_suitability_history for this user
        # activity_type: 'recommendation' or 'suitability'
        if intent in ("recommendation", "general_app", "follow_up") or referenced_crop:
            cur.execute(
                """SELECT id, crop_id, state, district, season, soil_type, soil_ph,
                          n_value, p_value, k_value, irrigation, overall_score,
                          activity_type, tehsil, village, details, analysis_date
                   FROM crop_suitability_history
                   WHERE user_id = %s
                   ORDER BY analysis_date DESC
                   LIMIT %s""",
                (user_id, limit * 2),
            )
            rows = cur.fetchall() or []

            recommendations: List[Dict[str, Any]] = []
            suitabilities: List[Dict[str, Any]] = []

            for row in rows:
                details = {}
                if row.get("details"):
                    try:
                        details = json.loads(row["details"]) if isinstance(row["details"], str) else row["details"]
                    except Exception:
                        details = {}

                record = {
                    "id": row["id"],
                    "crop_name": _safe_crop_name(details)
                    or details.get("crop_name")
                    or details.get("crop"),
                    "crop_id": row.get("crop_id"),
                    "state": row.get("state"),
                    "district": row.get("district"),
                    "season": row.get("season"),
                    "soil_type": row.get("soil_type"),
                    "soil_ph": float(row["soil_ph"]) if row.get("soil_ph") is not None else None,
                    "n_value": row.get("n_value"),
                    "p_value": row.get("p_value"),
                    "k_value": row.get("k_value"),
                    "irrigation": row.get("irrigation"),
                    "overall_score": row.get("overall_score"),
                    "activity_type": row.get("activity_type"),
                    "analysis_date": str(row["analysis_date"]) if row.get("analysis_date") else None,
                    "details": details,
                    "alternatives": details.get("alternatives", []) if isinstance(details.get("alternatives"), list) else [],
                    "explanation": details.get("explanation"),
                    "suitability_score": details.get("suitability_score", row.get("overall_score")),
                    "soil_compatibility": details.get("soil_compatibility"),
                    "seasonal_compatibility": details.get("seasonal_compatibility"),
                    "regional_compatibility": details.get("regional_compatibility"),
                    "key_factors": details.get("key_factors", []) if isinstance(details.get("key_factors"), list) else [],
                }

                if row.get("activity_type") == "recommendation":
                    recommendations.append(record)
                else:
                    suitabilities.append(record)

            if recommendations:
                records["latest_recommendation"] = recommendations[0]
                records["previous_recommendations"] = recommendations[1:]
                records["has_recommendation"] = True

            if suitabilities:
                records["latest_suitability"] = suitabilities[0]
                records["previous_suitability"] = suitabilities[1:]
                records["has_suitability"] = True

    except Error as e:
        logger.error("MySQL error retrieving farmer records: %s", e)
    except Exception as e:
        logger.error("Unexpected error retrieving farmer records: %s", e)
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return records


# ---------------------------------------------------------------------------
# Conversation context from session
# ---------------------------------------------------------------------------
def get_conversation_context(session: Any) -> Dict[str, Any]:
    """Retrieve conversation memory from Flask session.

    Returns recent messages and the last discussed crop/activity.
    """
    history = session.get("kisaanbot_conversation", []) or []
    last_crop = session.get("kisaanbot_last_crop", None)
    last_activity = session.get("kisaanbot_last_activity", None)

    # Keep only the last 6 messages for context
    recent = history[-6:] if history else []

    return {
        "recent_messages": recent,
        "last_discussed_crop": last_crop,
        "last_discussed_activity": last_activity,
        "message_count": len(history),
    }


def update_conversation_context(
    session: Any,
    user_message: str,
    bot_reply: str,
    crop: Optional[str] = None,
    activity: Optional[str] = None,
) -> None:
    """Persist conversation turn to Flask session."""
    history = session.get("kisaanbot_conversation", []) or []
    history.append({"user": user_message, "bot": bot_reply})
    # Keep last 10 turns
    history = history[-10:]
    session["kisaanbot_conversation"] = history

    if crop:
        session["kisaanbot_last_crop"] = crop
    if activity:
        session["kisaanbot_last_activity"] = activity
    session.modified = True


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------
def build_context(
    question: str,
    user_id: int,
    language: str = "en",
    session: Any = None,
) -> Dict[str, Any]:
    """Build the complete context for a KisaanBot query.

    Returns a dict with:
      - application_context: str (relevant ChromaDB docs)
      - farmer_context: str (relevant MySQL records)
      - conversation_context: str (recent session messages)
      - intent: dict (classification result)
      - farmer_records: dict (raw records for suggestion engine)
      - context_summary: str (assembled text for LLM prompt)
    """
    # Classify intent
    conv_ctx = get_conversation_context(session) if session else {}
    last_crop = conv_ctx.get("last_discussed_crop")
    last_activity = conv_ctx.get("last_discussed_activity")
    recent_context_str = _format_recent_messages(conv_ctx.get("recent_messages", []))

    intent_result = classify_intent(
        question,
        language=language,
        has_farmer_history=True,  # We'll check actual records below
        last_discussed_crop=last_crop,
        conversation_context=recent_context_str,
    )

    intent_name = intent_result.get("intent", "general_app")
    referenced_crop = intent_result.get("referenced_crop") or last_crop

    # 1. Application context from ChromaDB (intent-filtered)
    application_context = _build_application_context(question, intent_name, language)

    # 2. Farmer context from MySQL (intent-based retrieval)
    farmer_records = get_farmer_records(user_id, intent_name, referenced_crop)

    # Fall back to session profile when MySQL user_profiles table is empty
    if not farmer_records.get("profile") and session:
        session_profile = session.get("user_profile", {})
        if session_profile:
            farmer_records["profile"] = {
                "name": session_profile.get("name") or "Farmer",
                "farm_size": session_profile.get("farm_size") or "Not set",
                "soil_type": session_profile.get("soil_type") or "Not set",
                "irrigation": session_profile.get("irrigation") or "Not set",
                "state": session_profile.get("state_name") or session_profile.get("state") or "Not set",
                "district": session_profile.get("district_name") or session_profile.get("district") or "Not set",
                "language": session_profile.get("preferred_language") or "en",
            }

    farmer_context = _format_farmer_context(farmer_records, intent_name, language)

    # 3. Conversation context
    conversation_context = recent_context_str
    if last_crop:
        conversation_context += f"\nLast discussed crop: {last_crop}"
    if last_activity:
        conversation_context += f"\nLast discussed activity: {last_activity}"
    if not conversation_context.strip():
        conversation_context = "No previous conversation context."

    # Update intent's has_farmer_history flag based on actual records
    intent_result["has_farmer_history"] = (
        farmer_records["has_recommendation"]
        or farmer_records["has_suitability"]
    )

    # Assemble final context text
    context_summary = f"""APPLICATION CONTEXT:
{application_context}

FARMER CONTEXT:
{farmer_context}

CONVERSATION CONTEXT:
{conversation_context}

CURRENT QUESTION:
{question}"""

    return {
        "application_context": application_context,
        "farmer_context": farmer_context,
        "conversation_context": conversation_context,
        "intent": intent_result,
        "farmer_records": farmer_records,
        "context_summary": context_summary,
        "language": intent_result.get("language", language),
        "referenced_crop": referenced_crop,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _build_application_context(
    question: str,
    intent: str,
    language: str = "en",
) -> str:
    """Retrieve relevant ChromaDB documents for the intent."""
    category = INTENT_CATEGORY_MAP.get(intent)
    docs = query_knowledge_base(question, n_results=4, category_filter=category)

    if not docs:
        # Fallback: general query without category filter
        docs = query_knowledge_base(question, n_results=3)

    if not docs:
        return "No application documentation found for this topic."

    parts: List[str] = []
    for doc in docs:
        parts.append(f"[{doc.get('title', 'Document')}] {doc.get('content', '')}")

    return "\n\n".join(parts)


def _format_farmer_context(
    records: Dict[str, Any],
    intent: str,
    language: str = "en",
) -> str:
    """Format farmer records into a readable context string.

    Missing records are explicitly marked as unavailable.
    """
    parts: List[str] = []

    profile = records.get("profile")
    if profile:
        # Support both state/district and state_name/district_name field names
        profile_district = profile.get("district_name") or profile.get("district") or "Not set"
        profile_state = profile.get("state_name") or profile.get("state") or "Not set"
        parts.append(
            f"Farmer profile: {profile.get('name')}, "
            f"Current location: {profile_district}, {profile_state}, "
            f"Farm size: {profile.get('farm_size') or 'Not set'}, "
            f"Soil: {profile.get('soil_type') or 'Not set'}, "
            f"Irrigation: {profile.get('irrigation') or 'Not set'}"
        )
    else:
        parts.append("Farmer profile: unavailable")

    # Latest recommendation
    if records.get("latest_recommendation"):
        rec = records["latest_recommendation"]
        rec_district = rec.get("district_name") or rec.get("district") or "Not set"
        rec_state = rec.get("state_name") or rec.get("state") or "Not set"
        parts.append(
            f"Latest crop recommendation: {rec.get('crop_name')} "
            f"(season: {rec.get('season')}, "
            f"suitability score: {rec.get('suitability_score')}, "
            f"recommendation location: {rec_district}, {rec_state}, "
            f"soil: {rec.get('soil_type') or 'Not set'}, "
            f"pH: {rec.get('soil_ph') or 'Not set'}, "
            f"irrigation: {rec.get('irrigation') or 'Not set'})"
        )
        if rec.get("alternatives"):
            alts = rec["alternatives"]
            alt_names = []
            for a in alts:
                if isinstance(a, dict):
                    alt_names.append(a.get("name", str(a)))
                elif isinstance(a, str):
                    alt_names.append(a)
            if alt_names:
                parts.append(f"Alternative crops: {', '.join(alt_names)}")
        if rec.get("explanation"):
            parts.append(f"Recommendation explanation: {rec['explanation']}")
    else:
        parts.append("Latest crop recommendation: unavailable (no saved recommendation)")

    # Previous recommendations
    if records.get("previous_recommendations"):
        prev_crops = [r.get("crop_name") for r in records["previous_recommendations"][:3] if r.get("crop_name")]
        if prev_crops:
            parts.append(f"Previous recommendations: {', '.join(prev_crops)}")

    # Latest suitability
    if records.get("latest_suitability"):
        sat = records["latest_suitability"]
        parts.append(
            f"Latest suitability analysis: {sat.get('crop_name')} "
            f"(overall score: {sat.get('overall_score')}, "
            f"soil: {sat.get('soil_type')}, pH: {sat.get('soil_ph')}, "
            f"season: {sat.get('season')})"
        )
    else:
        parts.append("Latest suitability analysis: unavailable (no saved suitability analysis)")

    # Cultivation guide (session-based, no DB table)
    parts.append("Cultivation guide: unavailable (no saved cultivation guide in database)")

    return "\n".join(parts)


def _format_recent_messages(messages: List[Dict[str, str]]) -> str:
    """Format recent conversation messages into a string."""
    if not messages:
        return "No previous conversation."
    lines: List[str] = []
    for m in messages[-5:]:
        lines.append(f"User: {m.get('user', '')}")
        lines.append(f"KisaanBot: {m.get('bot', '')}")
    return "\n".join(lines)


def _safe_crop_name(details: Dict[str, Any]) -> Optional[str]:
    """Safely extract crop name from details, handling dict or string top_crop."""
    top_crop = details.get("top_crop")
    if isinstance(top_crop, dict):
        return top_crop.get("name")
    if isinstance(top_crop, str):
        return top_crop
    return None
