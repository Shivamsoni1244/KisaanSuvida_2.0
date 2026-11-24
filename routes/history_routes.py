"""
routes/history_routes.py - Historical recommendations, analyses, and diagnostics
"""

import json
import logging
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, session
from data.db import get_db
from mysql.connector import Error

history_bp = Blueprint("history", __name__)

logger = logging.getLogger(__name__)


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


def _parse_record(row: dict) -> dict | None:
    """Parse a crop_suitability_history row into a history record dict."""
    try:
        details = {}
        if row.get("details"):
            try:
                details = (
                    json.loads(row["details"])
                    if isinstance(row["details"], str)
                    else row["details"]
                )
            except Exception:
                details = {}

        activity_type = row.get("activity_type", "recommendation")
        analysis_date = row.get("analysis_date")
        date_str = (
            analysis_date.strftime("%d %b %Y")
            if isinstance(analysis_date, datetime)
            else str(analysis_date)[:10] if analysis_date else "Unknown"
        )

        # Crop name from details or fallback
        top_crop = details.get("top_crop")
        if isinstance(top_crop, dict):
            crop_name = top_crop.get("name") or details.get("crop_name") or "Unknown"
        elif isinstance(top_crop, str):
            crop_name = top_crop
        else:
            crop_name = details.get("crop_name") or "Unknown"

        location = f"{row.get('district', '')}, {row.get('state', '')}".strip(", ")
        if not location or location == ",":
            location = "Not specified"

        # Result/score
        overall_score = row.get("overall_score")
        if details.get("suitability_score") is not None:
            result = f"{details['suitability_score']}%"
        elif overall_score is not None:
            result = f"{overall_score}%"
        else:
            result = "N/A"

        # Activity display name
        if activity_type == "recommendation":
            activity = "Crop Recommendation"
        elif activity_type == "suitability":
            activity = "Suitability Analysis"
        else:
            activity = activity_type.title()

        return {
            "id": row.get("id"),
            "activity_type": activity_type,
            "activity": activity,
            "date": date_str,
            "crop": crop_name,
            "location": location,
            "result": result,
            "status": "View",
            "details": details,
            "score": row.get("overall_score"),
            "season": row.get("season"),
            "soil_type": row.get("soil_type"),
            "irrigation": row.get("irrigation"),
        }
    except Exception as e:
        logger.error("Failed to parse history record: %s", e)
        return None


@history_bp.route("/history")
def history_page():
    user = get_current_user() or {}
    user_id = session.get("user_id")

    records = []
    recom_count = 0
    analysis_count = 0
    disease_count = 0

    if user_id:
        conn = None
        cur = None
        try:
            conn = get_db()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT id, user_id, crop_id, state, district, season, soil_type,
                          soil_ph, n_value, p_value, k_value, irrigation, overall_score,
                          activity_type, tehsil, village, details, analysis_date
                   FROM crop_suitability_history
                   WHERE user_id = %s
                   ORDER BY analysis_date DESC""",
                (user_id,),
            )
            rows = cur.fetchall() or []

            for row in rows:
                record = _parse_record(row)
                if record:
                    records.append(record)
                    if record["activity_type"] == "recommendation":
                        recom_count += 1
                    elif record["activity_type"] == "analysis":
                        analysis_count += 1

        except Error as e:
            logger.error("MySQL error fetching history: %s", e)
        except Exception as e:
            logger.error("Unexpected error fetching history: %s", e)
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

    return render_template(
        "history.html",
        user=user,
        records=records,
        recom_count=recom_count,
        analysis_count=analysis_count,
        disease_count=disease_count,
        active_page="history"
    )


@history_bp.route("/api/history")
def api_history():
    user_id = session.get("user_id")
    records = []

    if user_id:
        conn = None
        cur = None
        try:
            conn = get_db()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT id, user_id, crop_id, state, district, season, soil_type,
                          soil_ph, n_value, p_value, k_value, irrigation, overall_score,
                          activity_type, tehsil, village, details, analysis_date
                   FROM crop_suitability_history
                   WHERE user_id = %s
                   ORDER BY analysis_date DESC""",
                (user_id,),
            )
            rows = cur.fetchall() or []
            for row in rows:
                record = _parse_record(row)
                if record:
                    records.append(record)
        except Error as e:
            logger.error("MySQL error fetching history API: %s", e)
        except Exception as e:
            logger.error("Unexpected error fetching history API: %s", e)
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

    return jsonify({
        "success": True,
        "count": len(records),
        "records": records
    })
