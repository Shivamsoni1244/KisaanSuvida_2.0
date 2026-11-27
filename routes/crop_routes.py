"""
routes/crop_routes.py - Crop recommendation powered by Mistral AI

Handles:
- GET/POST /recommendation - Farm input form and Mistral-powered recommendations
- POST /api/crop/recommend - REST API for recommendations
- GET /crop-guide/<crop_name> - Detailed crop cultivation guide (existing, preserved)
- GET /crop/suitability - Crop suitability input form (existing, preserved)
- POST /api/crop/suitability - Crop suitability analysis API (existing, preserved)
- GET /api/crop/search - Search crops by name

The top crop and two alternatives are produced entirely by the Mistral API.
No rule-based scoring engine, no ML prediction, no Groq, no Gemini is used
for crop selection. If Mistral is unavailable or returns an invalid response,
an error state is returned.
"""

import logging
import json
from datetime import datetime
from typing import Dict
import uuid

import pytz
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, make_response
from fpdf import FPDF

from data.db import get_db
from mysql.connector import Error

from services.mistral_crop_engine import (
    recommend_crops,
    get_crop_guide,
)
from services.groq_service import explain_recommendation, validate_recommendation
from services.crop_engine import (
    SOIL_TYPE_AVERAGES,
    STATE_DISTRICTS,
    CROPS_DATABASE,
    calculate_suitability,
)
from services.weather_engine import (
    get_current_weather,
    format_weather_for_display,
)
from services.crop_service import (
    search_crops,
)

crop_bp = Blueprint("crop", __name__)

logger = logging.getLogger(__name__)

# Server-side cache for recommendation results keyed by UUID (PRG pattern)
_recommendation_result_cache = {}

IST = pytz.timezone("Asia/Kolkata")

CROPS_LIST = list(CROPS_DATABASE.keys())


def get_current_user():
    """Return the authenticated user's profile from session, or None for guests."""
    return session.get("user_profile")


def _get_automatic_season(state: str, district: str) -> str:
    """
    Automatically determine the current agricultural season based on date.

    - Kharif: June-October (monsoon crops)
    - Rabi: November-March (winter crops)
    - Zaid: April-May (summer crops)
    """
    now = datetime.now(IST)
    month = now.month

    if month in (6, 7, 8, 9, 10):
        return "Kharif"
    elif month in (11, 12, 1, 2, 3):
        return "Rabi"
    else:
        return "Zaid"


def get_greeting() -> str:
    """Return greeting based on Asia/Kolkata local time."""
    now = datetime.now(IST)
    hour = now.hour

    if 5 <= hour < 12:
        return "Good Morning"
    elif 12 <= hour < 17:
        return "Good Afternoon"
    elif 17 <= hour < 21:
        return "Good Evening"
    else:
        return "Good Night"


def get_current_datetime() -> Dict[str, str]:
    """Get current date and time in Indian local timezone."""
    now = datetime.now(IST)
    return {
        "date": now.strftime("%d %b %Y"),
        "day": now.strftime("%A"),
        "time": now.strftime("%I:%M %p"),
        "datetime_iso": now.isoformat(),
        "greeting": get_greeting(),
    }


@crop_bp.route("/recommendation", methods=["GET", "POST"])
def recommendation():
    user = get_current_user() or {}

    # Get current date/time/greeting for the page
    current_datetime = get_current_datetime()

    # Determine automatic season
    auto_season = _get_automatic_season(
        user.get("state", "Punjab"),
        user.get("district", "Ludhiana"),
    )

    if request.method == "POST":
        mode = request.form.get("mode", "advanced")

        # Resolved location names from cascading dropdowns
        state = (
            request.form.get("state_name")
            or request.form.get("state")
            or user.get("state", "")
        )
        district = (
            request.form.get("district_name")
            or request.form.get("district")
            or user.get("district", "")
        )
        season = request.form.get("season", auto_season)
        soil_type = request.form.get("soil_type", "Alluvial")
        irrigation = request.form.get("irrigation", "Canal irrigation")
        language = user.get("preferred_language", "en")

        # Soil nutrient values
        if mode == "basic":
            defaults = SOIL_TYPE_AVERAGES.get(
                soil_type, {"n": 90, "p": 42, "k": 43, "ph": 6.5}
            )
            n = float(defaults["n"])
            p = float(defaults["p"])
            k = float(defaults["k"])
            ph = float(defaults["ph"])
            soil_values_source = "estimated"
        else:
            try:
                n = float(request.form.get("nitrogen", 90))
                p = float(request.form.get("phosphorus", 42))
                k = float(request.form.get("potassium", 43))
                ph = float(request.form.get("soil_ph", 6.5))
            except ValueError:
                n, p, k, ph = 90.0, 42.0, 43.0, 6.5
            soil_values_source = "advanced"

        # Fetch real-time weather
        weather = get_current_weather(state, district)
        weather_display = format_weather_for_display(weather)

        # Farm context passed in full to Mistral
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
            "soil_values_source": soil_values_source,
        }

        # Mistral produces the top crop + two alternatives + compatibility (Image 2)
        mistral_result = recommend_crops(farm_context, weather, language)

        na = "Not available"

        mistral_success = mistral_result.get("status") == "success"
        top_crop_name = mistral_result["top_crop"].get("name") if mistral_success else None
        alt_names = []
        alt_scores = []
        if mistral_success:
            alt_names = [a.get("name") for a in mistral_result["alternatives"][:2] if a.get("name")]
            alt_scores = [a.get("suitability_score", na) for a in mistral_result["alternatives"][:2]]
        while len(alt_names) < 2:
            alt_names.append(na)
            alt_scores.append(na)

        # Groq produces Image 1 explanation sections (Why this crop, Key factors, etc.)
        groq_result = explain_recommendation(
            top_crop={"name": top_crop_name} if top_crop_name else {"name": na},
            farm_context=farm_context,
            language=language,
        ) if top_crop_name else {
            "explanation": na,
            "key_factors": [na],
            "states_where_it_grows": [na],
            "did_you_know": na,
            "how_to_grow_summary": na,
            "source": "not_available",
        }

        # Groq #2 validates the recommendation
        validation_result = validate_recommendation(
            recommendation={
                "top_crop": {"name": top_crop_name or na, "suitability_score": na},
                "alternatives": [],
            },
            farm_context=farm_context,
            weather=weather,
            language=language,
        ) if top_crop_name else {
            "validation_status": na,
            "overall_score": na,
            "summary": na,
            "validations": [na],
            "contradictions": [na],
            "missing_information": [na],
            "recommendations": [na],
            "risks": [na],
            "disclaimer": na,
            "source": "not_available",
        }

        # Build top_crop: Mistral supplies name + compatibility (Image 2), Groq supplies explanation (Image 1)
        top_crop = {
            "name": top_crop_name or na,
            "summary": groq_result.get("how_to_grow_summary", na),
            "ml_probability": na,
            "explanation_source": groq_result.get("source", "not_available"),
            "explanation": groq_result.get("explanation", na),
            "key_factors": groq_result.get("key_factors", [na]),
            "important_considerations": groq_result.get("key_factors", [na]),
            "states_where_it_grows": groq_result.get("states_where_it_grows", [na]),
            "did_you_know": groq_result.get("did_you_know", na),
            "weather_summary": na,
            "water_requirement": na,
            "irrigation_advice": na,
            "soil_compatibility": mistral_result["top_crop"].get("soil_compatibility", na) if mistral_success else na,
            "seasonal_compatibility": mistral_result["top_crop"].get("seasonal_compatibility", na) if mistral_success else na,
            "regional_compatibility": mistral_result["top_crop"].get("regional_compatibility", na) if mistral_success else na,
            "cultivation_risks": mistral_result["top_crop"].get("cultivation_risks", [na]) if mistral_success else [na],
            "suitability_score": mistral_result["top_crop"].get("suitability_score", na) if mistral_success else na,
        }

        # Build alternatives: Mistral supplies names + scores
        alternatives = []
        for i, alt_name in enumerate(alt_names):
            alternatives.append({
                "name": alt_name,
                "suitability_score": alt_scores[i] if i < len(alt_scores) else na,
                "summary": na,
                "water_requirement": na,
                "season": na,
            })

        # Compose final result for the template
        result = {
            "top_crop": top_crop,
            "alternatives": alternatives,
            "status": mistral_result.get("status", "error"),
            "error": mistral_result.get("error"),
            "disclaimer": "AI-generated crop recommendations. Consult local agricultural experts before major decisions.",
            "weather_context": {
                "temperature": weather.get("temperature", "Not available"),
                "humidity": weather.get("humidity", "Not available"),
                "condition": weather.get("description", "Not available"),
                "rainfall": weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0,
            },
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
            },
            "source": "mistral_ai",
            "validation": {
                "validation_status": validation_result.get("validation_status", na),
                "overall_score": validation_result.get("overall_score", na),
                "summary": validation_result.get("summary", na),
                "validations": validation_result.get("validations", [na]),
                "contradictions": validation_result.get("contradictions", [na]),
                "missing_information": validation_result.get("missing_information", [na]),
                "recommendations": validation_result.get("recommendations", [na]),
                "risks": validation_result.get("risks", [na]),
                "disclaimer": validation_result.get("disclaimer", na),
                "source": validation_result.get("source", "not_available"),
            },
        }

        # Add display-friendly data
        result["weather_display"] = weather_display
        result["current_datetime"] = current_datetime
        result["auto_season"] = auto_season
        result["selected_season"] = season
        result["language"] = language
        result["soil_values_source"] = soil_values_source
        result["user"] = user

        # Save to recommendation history (session-based)
        _save_recommendation_history(user, result)

        # Save farm inputs to session for persistence across navigation
        session["last_farm_inputs"] = {
            "state": state,
            "district": district,
            "season": season,
            "soil_type": soil_type,
            "irrigation": irrigation,
            "n": n,
            "p": p,
            "k": k,
            "ph": ph,
            "mode": mode,
            "soil_values_source": soil_values_source,
        }
        session.modified = True

        # Save result to server-side cache with a UUID key (PRG pattern)
        result_id = str(uuid.uuid4())
        _recommendation_result_cache[result_id] = result
        session.modified = True

        # PRG: Redirect to GET result page to prevent duplicate form submission
        return redirect(url_for("crop.recommendation_result", result_id=result_id))

    # GET request - show recommendation form or result
    result_id = request.args.get("result_id")
    saved_result = None
    if result_id:
        saved_result = _recommendation_result_cache.get(result_id)

    if saved_result:
        saved_inputs = session.get("last_farm_inputs", {})
        return render_template(
            "crop_result.html",
            user=user,
            result=saved_result,
            result_id=result_id,
            active_page="recommendation",
        )

    # Restore saved farm inputs if available (for back navigation persistence)
    saved_inputs = session.get("last_farm_inputs", {})
    return render_template(
        "crop_recommendation.html",
        user=user,
        soil_averages=SOIL_TYPE_AVERAGES,
        active_page="recommendation",
        current_datetime=current_datetime,
        auto_season=auto_season,
        saved_inputs=saved_inputs,
    )


@crop_bp.route("/recommendation/result")
def recommendation_result():
    """GET route for displaying recommendation result (PRG pattern target)."""
    user = get_current_user() or {}
    result_id = request.args.get("result_id")

    result = None
    if result_id:
        result = _recommendation_result_cache.get(result_id)

    if not result:
        return redirect(url_for("crop.recommendation"))

    return render_template(
        "crop_result.html",
        user=user,
        result=result,
        result_id=result_id,
        active_page="recommendation",
    )


@crop_bp.route("/recommendation/result/download")
def recommendation_result_download():
    """Download combined recommendation + cultivation guide report as PDF."""
    result_id = request.args.get("result_id")

    result = None
    if result_id:
        result = _recommendation_result_cache.get(result_id)

    if not result:
        return redirect(url_for("crop.recommendation"))

    crop_name = result.get("top_crop", {}).get("name", "")
    user = get_current_user() or {}
    language = user.get("preferred_language", "en")

    guide = _get_guide_for_result(crop_name, result, language)

    return _generate_combined_crop_report_pdf(result, guide, result_id)


# ============================================================================
# PDF Download Routes
# ============================================================================

@crop_bp.route("/recommendation/download-pdf")
def download_recommendation_pdf():
    """Download detailed recommendation report as PDF (alias for combined report)."""
    return recommendation_result_download()


@crop_bp.route("/crop-guide/download-pdf/<crop_name>")
def download_crop_guide_pdf(crop_name: str):
    """Download combined recommendation + cultivation guide report as PDF."""
    user = get_current_user() or {}
    language = user.get("preferred_language", "en")

    result_id = request.args.get("result_id")

    result = None
    if result_id:
        result = _recommendation_result_cache.get(result_id)

    guide = _get_guide_for_result(crop_name, result, language)

    if not guide:
        return redirect(url_for("crop.crop_guide", crop_name=crop_name))

    if not result:
        return redirect(url_for("crop.recommendation"))

    return _generate_combined_crop_report_pdf(result, guide, result_id)


def _get_guide_for_result(crop_name: str, result, language: str):
    """Retrieve or generate the cultivation guide for a recommendation result.

    Uses the session cache if available; otherwise generates a fresh guide
    using the result's farm context (never default Punjab/Ludhiana values
    when a recommendation result exists).
    """
    if not crop_name:
        return None

    cached = session.get(f"crop_guide:{crop_name}")
    if cached:
        cached["source"] = cached.get("source", "cached")
        cached["from_cache"] = True
        return cached

    if result:
        farm_context = result.get("farm_context", {})
        weather = result.get("weather_context", {})
        try:
            guide = get_crop_guide(crop_name, farm_context, language, weather)
            if guide:
                session[f"crop_guide:{crop_name}"] = guide
                session.modified = True
                return guide
        except Exception as e:
            logger.error("Failed to generate crop guide for %s: %s", crop_name, e)
            return None
    return None


# ============================================================================
# PDF Generation Helpers
# ============================================================================

# ============================================================================
# Combined PDF Generation Helpers
# ============================================================================

def _sanitize_pdf_text(text: str) -> str:
    """Replace characters that can't be encoded in latin-1 (fpdf2 Helvetica limit)."""
    if text is None:
        return ""
    text = str(text)
    # Map common unicode to latin-1-safe equivalents
    replacements = {
        "\u2022": "-",       # bullet
        "\u2013": "-",       # en dash
        "\u2014": "-",       # em dash
        "\u2018": "'",       # left single quote
        "\u2019": "'",       # right single quote
        "\u201c": '"',       # left double quote
        "\u201d": '"',       # right double quote
        "\u00a0": " ",       # non-breaking space
        "\u2026": "...",     # ellipsis
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _wrap_multi_cell(pdf, text: str, w: float, line_height: float = 5.0, font_size: int = 10):
    """Render text into a multi_cell with manual word wrapping to avoid overflow."""
    if not text:
        return
    text = _sanitize_pdf_text(str(text))
    words = text.split()
    lines = []
    current = ""
    max_w = w - 4
    for word in words:
        test = (current + " " + word).strip()
        if pdf.get_string_width(test) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        pdf.multi_cell(w, line_height, line)


def _pdf_header(pdf, title: str, subtitle: str):
    """Draw report header with Kisaan Suvidha branding."""
    pdf.add_page()
    pdf.set_draw_color(21, 58, 37)
    pdf.set_line_width(1.2)
    pdf.line(15, 32, 195, 32)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(21, 58, 37)
    pdf.cell(0, 14, "Kisaan Suvidha", align="C")
    pdf.ln(7)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 14, _sanitize_pdf_text(title), align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5, _sanitize_pdf_text(subtitle))
    pdf.ln(8)


def _pdf_section_heading(pdf, text: str):
    """Draw a section heading bar."""
    pdf.set_fill_color(232, 245, 236)
    pdf.set_draw_color(21, 58, 37)
    pdf.set_line_width(0.5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(21, 58, 37)
    pdf.cell(0, 10, "  " + _sanitize_pdf_text(text), fill=True, border=1)
    pdf.ln(8)


def _pdf_field(pdf, label: str, value: str):
    """Draw a stacked field: bold label on its own line, value below."""
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(21, 58, 37)
    pdf.multi_cell(0, 5, _sanitize_pdf_text(label))
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(60, 60, 60)
    _wrap_multi_cell(pdf, value, 180, line_height=5)
    pdf.ln(6)


def _pdf_footer(pdf, page_num: int):
    """Draw page footer with page number."""
    pdf.set_y(-18)
    pdf.set_draw_color(21, 58, 37)
    pdf.set_line_width(0.5)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, _sanitize_pdf_text(f"Kisaan Suvidha - Crop Recommendation & Cultivation Report    Page {page_num}"), align="C")


def _generate_combined_crop_report_pdf(result, guide, result_id) -> object:
    """Generate a single combined PDF containing recommendation + cultivation guide.

    This is the shared generator used by both download buttons.
    """
    na = "Not available"
    top = result.get("top_crop", {}) or {}
    farm = result.get("farm_context", {}) or {}
    validation = result.get("validation", {}) or {}
    weather_ctx = result.get("weather_context", {}) or {}
    crop_name = top.get("name", na)

    now_ist = datetime.now(IST)
    report_date = now_ist.strftime("%d %B %Y")
    report_time = now_ist.strftime("%I:%M %p IST")

    safe_crop = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in str(crop_name)).strip()
    filename = f"Kisaan_Suvidha_{safe_crop}_Complete_Report.pdf"

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(15, 20, 15)

    # Try to register Hindi-compatible fonts if available on the system
    import os
    font_dirs = ["C:/Windows/Fonts/", "/usr/share/fonts/truetype/", "/System/Library/Fonts/"]
    hindi_font = None
    for d in font_dirs:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            fl = fname.lower()
            if any(k in fl for k in ("nirmala", "mangal", "tunga", "gautami", "lakki", "kokila", "shruti")):
                hindi_font = d + fname
                break
        if hindi_font:
            break

    if hindi_font:
        try:
            pdf.add_font("Hindi", "", hindi_font)
            pdf.add_font("Hindi", "B", hindi_font)
        except Exception:
            pass

    page_count = 0

    def new_page():
        nonlocal page_count
        page_count += 1

    # ---------- Cover / Report Header ----------
    new_page()
    _pdf_header(pdf, "Crop Recommendation & Cultivation Report",
                f"Recommended crop: {crop_name}    |    Generated: {report_date} at {report_time}")
    _pdf_field(pdf, "Location", f"{farm.get('district', na)}, {farm.get('state', na)}")

    pdf.ln(3)

    # ---------- Section 1: Farm Profile ----------
    _pdf_section_heading(pdf, "Section 1: Farm Profile")
    farm_rows = [
        ("State", farm.get("state", na)),
        ("District", farm.get("district", na)),
        ("Season", result.get("selected_season", na)),
        ("Soil Type", f"{farm.get('soil_type', na)} soil"),
        ("Irrigation Method", farm.get("irrigation", na)),
        ("Nitrogen (N)", f"{farm.get('n', na)} kg/ha"),
        ("Phosphorus (P)", f"{farm.get('p', na)} kg/ha"),
        ("Potassium (K)", f"{farm.get('k', na)} kg/ha"),
        ("Soil pH", str(farm.get("ph", na))),
    ]
    temp_weather = weather_ctx or {}
    if temp_weather:
        farm_rows.append(("Weather", f"{temp_weather.get('temperature', na)}°C, {temp_weather.get('condition', na)}"))
    for label, value in farm_rows:
        _pdf_field(pdf, label, value)
    pdf.ln(6)

    # ---------- Section 2: Crop Recommendation ----------
    _pdf_section_heading(pdf, "Section 2: Crop Recommendation")
    _pdf_field(pdf, "Top Recommended Crop", top.get("name", na))
    if guide and guide.get("hindi_name") and guide.get("hindi_name") != na:
        _pdf_field(pdf, "Hindi Name", guide.get("hindi_name"))
    _pdf_field(pdf, "Crop Summary", top.get("summary", na))
    _pdf_field(pdf, "Why This Crop Was Recommended", result.get("explanation", na))
    _pdf_field(pdf, "Farm Compatibility",
                   f"Soil: {top.get('soil_compatibility', na)}% | Season: {top.get('seasonal_compatibility', na)}% | Region: {top.get('regional_compatibility', na)}%")
    _pdf_field(pdf, "Suitability Score", f"{top.get('suitability_score', na)}%")

    # Alternative crops
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(21, 58, 37)
    pdf.cell(0, 6, "Alternative Crops:")
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    for alt in result.get("alternatives", []) or []:
        pdf.cell(8, 5, "-")
        pdf.cell(0, 5, _sanitize_pdf_text(f"{alt.get('name', na)} - {alt.get('suitability_score', na)}% suitability"))
        pdf.ln()
    pdf.ln(2)

    _pdf_field(pdf, "Important Considerations", "; ".join(top.get("important_considerations", [na]) if isinstance(top.get("important_considerations"), list) else [top.get("important_considerations", na)]))
    _pdf_field(pdf, "Regional Suitability", "; ".join(top.get("states_where_it_grows", [na]) if isinstance(top.get("states_where_it_grows"), list) else [top.get("states_where_it_grows", na)]))
    _pdf_field(pdf, "Validation Status", validation.get("validation_status", na))
    _pdf_field(pdf, "Overall Score", f"{validation.get('overall_score', na)}")
    _pdf_field(pdf, "Validation Summary", validation.get("summary", na))

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(21, 58, 37)
    pdf.cell(0, 6, "Recommendations:")
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    for r in validation.get("recommendations", [na]) if isinstance(validation.get("recommendations"), list) else [validation.get("recommendations", na)]:
        pdf.cell(8, 5, "-")
        _wrap_multi_cell(pdf, r, 182, line_height=5.5)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(21, 58, 37)
    pdf.cell(0, 6, "Contradictions & Risks:")
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    risks = validation.get("contradictions", [na]) if isinstance(validation.get("contradictions"), list) else [validation.get("contradictions", na)]
    risks += top.get("cultivation_risks", [na]) if isinstance(top.get("cultivation_risks"), list) else [top.get("cultivation_risks", na)]
    for r in risks:
        pdf.cell(8, 5, "-")
        _wrap_multi_cell(pdf, r, 182, line_height=5.5)
    pdf.ln(2)

    _pdf_field(pdf, "Missing Information", "; ".join(validation.get("missing_information", [na]) if isinstance(validation.get("missing_information"), list) else [validation.get("missing_information", na)]))
    _pdf_field(pdf, "Disclaimer", result.get("disclaimer", na))
    pdf.ln(6)

    # ---------- Section 3: Crop Overview ----------
    _pdf_section_heading(pdf, "Section 3: Crop Overview")
    _pdf_field(pdf, "Crop Name", guide.get("crop_name", crop_name) if guide else crop_name)
    _pdf_field(pdf, "Hindi Name", guide.get("hindi_name", na) if guide else na)
    _pdf_field(pdf, "Sowing Window", guide.get("sowing_time", na) if guide else na)
    _pdf_field(pdf, "Crop Duration", f"{guide.get('crop_duration_days', na)} days" if guide else na)
    _pdf_field(pdf, "Expected Yield", guide.get("expected_yield", na) if guide else na)
    _pdf_field(pdf, "Climate & Temperature", guide.get("climate_temperature", na) if guide else na)
    pdf.ln(6)

    # ---------- Section 4: Before You Plant ----------
    _pdf_section_heading(pdf, "Section 4: Before You Plant")
    _pdf_field(pdf, "Climate & Temperature", guide.get("climate_temperature", na) if guide else na)
    _pdf_field(pdf, "Rainfall Requirements", guide.get("rainfall_requirements", na) if guide else na)
    _pdf_field(pdf, "Land Preparation", guide.get("land_preparation", na) if guide else na)
    _pdf_field(pdf, "Soil Types", guide.get("soil_types", na) if guide else na)
    _pdf_field(pdf, "Recommended pH", guide.get("recommended_ph", na) if guide else na)
    pdf.ln(6)

    # ---------- Section 5: Seeds & Sowing ----------
    _pdf_section_heading(pdf, "Section 5: Seeds & Sowing")
    _pdf_field(pdf, "Seed Selection", guide.get("seed_selection", na) if guide else na)
    _pdf_field(pdf, "Seed Treatment", guide.get("seed_treatment", na) if guide else na)
    _pdf_field(pdf, "Seed Rate", guide.get("seed_rate", na) if guide else na)
    _pdf_field(pdf, "Sowing Method", guide.get("sowing_method", na) if guide else na)
    _pdf_field(pdf, "Sowing Time", guide.get("sowing_time", na) if guide else na)
    _pdf_field(pdf, "Row Spacing", guide.get("spacing_row", na) if guide else na)
    _pdf_field(pdf, "Plant Spacing", guide.get("spacing_plant", na) if guide else na)
    pdf.ln(6)

    # ---------- Section 6: Nutrition & Water Management ----------
    _pdf_section_heading(pdf, "Section 6: Nutrition & Water Management")
    _pdf_field(pdf, "Fertilizer Requirements", guide.get("fertilizer_requirements", na) if guide else na)
    _pdf_field(pdf, "Nitrogen Management", guide.get("nitrogen_management", na) if guide else na)
    _pdf_field(pdf, "Phosphorus Management", guide.get("phosphorus_management", na) if guide else na)
    _pdf_field(pdf, "Potassium Management", guide.get("potassium_management", na) if guide else na)
    _pdf_field(pdf, "Organic Fertilizer", guide.get("organic_fertilizer", na) if guide else na)
    _pdf_field(pdf, "Nutrient Deficiency", guide.get("nutrient_deficiency", na) if guide else na)
    _pdf_field(pdf, "Irrigation Requirements", guide.get("irrigation_requirements", na) if guide else na)
    pdf.ln(6)

    # ---------- Section 7: Crop Protection ----------
    _pdf_section_heading(pdf, "Section 7: Crop Protection")
    _pdf_field(pdf, "Weed Management", guide.get("weed_management", na) if guide else na)
    _pdf_field(pdf, "Pest Management", guide.get("pest_disease_management", na) if guide else na)
    _pdf_field(pdf, "Disease Management", guide.get("pest_disease_management", na) if guide else na)
    pdf.ln(6)

    # ---------- Section 8: Growth Stages ----------
    _pdf_section_heading(pdf, "Section 8: Growth Stages")
    stage_fields = [
        ("Germination", "growth_stage_germination"),
        ("Seedling", "growth_stage_seedling"),
        ("Vegetative Growth", "growth_stage_vegetative"),
        ("Flowering", "growth_stage_flowering"),
        ("Fruiting / Grain Filling", "growth_stage_fruit_grain"),
        ("Maturity", "growth_stage_maturity"),
    ]
    if guide:
        for stage_label, field in stage_fields:
            value = guide.get(field, "")
            if value and value != na:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(21, 58, 37)
                pdf.cell(0, 6, stage_label)
                pdf.ln(2)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(60, 60, 60)
                _wrap_multi_cell(pdf, value, 180, line_height=5.5)
                pdf.ln(2)
    pdf.ln(6)

    # ---------- Section 9: Harvest & Post-Harvest ----------
    _pdf_section_heading(pdf, "Section 9: Harvest & Post-Harvest")
    if guide:
        _pdf_field(pdf, "Harvesting Time", guide.get("harvesting_time", na))
        _pdf_field(pdf, "Harvesting Method", guide.get("harvesting_method", na))
        _pdf_field(pdf, "Harvesting Signs", guide.get("harvesting_signs", na))
        _pdf_field(pdf, "Post-Harvest Management", guide.get("post_harvest_management", na))
    pdf.ln(6)

    # ---------- Section 10: Important Precautions ----------
    _pdf_section_heading(pdf, "Section 10: Important Precautions")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    _wrap_multi_cell(pdf, guide.get("precautions", na) if guide else na, 180, line_height=5.5)
    pdf.ln(6)

    # Disclaimer / metadata
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 4.5, _sanitize_pdf_text(
        f"Disclaimer: {result.get('disclaimer', 'AI-generated recommendations. Consult local agricultural experts before major decisions.')}"
    ))
    pdf.ln(2)
    pdf.multi_cell(0, 4.5, _sanitize_pdf_text(
        f"Report generated on {report_date} at {report_time} by Kisaan Suvidha. "
        f"Result ID: {result_id}"
    ))

    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode("latin-1")
    elif isinstance(pdf_output, bytearray):
        pdf_output = bytes(pdf_output)

    response = make_response(pdf_output)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Type"] = "application/pdf"
    return response


# ============================================================================
# Legacy PDF helpers (kept for backward compatibility, delegate to combined)
# ============================================================================

def _generate_recommendation_pdf(result, result_id_short: str):
    """Legacy helper retained for external callers; redirects to combined PDF."""
    return _generate_combined_crop_report_pdf(result, None, result_id_short or "unknown")


def _generate_crop_guide_pdf(guide, crop_name: str):
    """Legacy helper retained for external callers; returns a minimal combined PDF."""
    from flask import redirect, url_for
    return redirect(url_for("crop.recommendation"))


@crop_bp.route("/crop-guide/<crop_name>")
def crop_guide(crop_name: str):
    """Display detailed crop cultivation guide page (existing feature, preserved)."""
    user = get_current_user() or {}
    language = user.get("preferred_language", "en")

    result_id = request.args.get("result_id")
    result = None
    if result_id:
        result = _recommendation_result_cache.get(result_id)

    existing_guide = session.get(f"crop_guide:{crop_name}")
    if existing_guide:
        guide = existing_guide
        guide["source"] = existing_guide.get("source", "cached")
        guide["from_cache"] = True
    else:
        # Use recommendation result's farm context when available (never default Punjab/Ludhiana)
        if result:
            farm_context = result.get("farm_context", {})
            weather = result.get("weather_context", {})
        else:
            farm_context = {
                "state": user.get("state", "Punjab"),
                "district": user.get("district", "Ludhiana"),
                "season": _get_automatic_season(
                    user.get("state", "Punjab"),
                    user.get("district", "Ludhiana"),
                ),
                "soil_type": user.get("soil_type", "Alluvial"),
                "irrigation": user.get("irrigation", "Canal irrigation"),
                "n": user.get("n"),
                "p": user.get("p"),
                "k": user.get("k"),
                "ph": user.get("ph"),
                "soil_values_source": user.get("soil_values_source", "estimated"),
            }
            weather = None

        current_datetime = get_current_datetime()

        weather_data = weather if weather and weather.get("source") == "openweathermap" else None
        if not weather_data and not result:
            weather_data = get_current_weather(
                farm_context["state"], farm_context["district"]
            )

        guide = get_crop_guide(crop_name, farm_context, language, weather_data)

        session[f"crop_guide:{crop_name}"] = guide
        session.modified = True

    return render_template(
        "crop_guide.html",
        user=user,
        guide=guide,
        crop_name=crop_name,
        result_id=result_id,
        active_page="recommendation",
    )


@crop_bp.route("/api/crop/recommend", methods=["POST"])
def api_recommend():
    """REST API endpoint for Mistral-powered recommendations."""
    data = request.get_json() or {}
    state = data.get("state", "Punjab")
    district = data.get("district", "Ludhiana")
    season = data.get("season", _get_automatic_season(state, district))
    soil_type = data.get("soil_type", "Alluvial")
    n = float(data.get("nitrogen", 90))
    p = float(data.get("phosphorus", 42))
    k = float(data.get("potassium", 43))
    ph = float(data.get("soil_ph", 6.5))
    irrigation = data.get("irrigation", "Canal irrigation")
    language = data.get("language", "en")

    weather = get_current_weather(state, district)

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
        "soil_values_source": data.get("soil_values_source", "estimated"),
    }

    mistral_result = recommend_crops(farm_context, weather, language)

    na = "Not available"

    mistral_success = mistral_result.get("status") == "success"
    top_crop_name = mistral_result["top_crop"].get("name") if mistral_success else None
    alt_names = []
    alt_scores = []
    if mistral_success:
        alt_names = [a.get("name") for a in mistral_result["alternatives"][:2] if a.get("name")]
        alt_scores = [a.get("suitability_score", na) for a in mistral_result["alternatives"][:2]]
    while len(alt_names) < 2:
        alt_names.append(na)
        alt_scores.append(na)

    # Groq produces Image 1 explanation sections
    groq_result = explain_recommendation(
        top_crop={"name": top_crop_name} if top_crop_name else {"name": na},
        farm_context=farm_context,
        language=language,
    ) if top_crop_name else {
        "explanation": na,
        "key_factors": [na],
        "states_where_it_grows": [na],
        "did_you_know": na,
        "how_to_grow_summary": na,
        "source": "not_available",
    }

    # Groq #2 validates the recommendation
    validation_result = validate_recommendation(
        recommendation={
            "top_crop": {"name": top_crop_name or na, "suitability_score": na},
            "alternatives": [],
        },
        farm_context=farm_context,
        weather=weather,
        language=language,
    ) if top_crop_name else {
        "validation_status": na,
        "overall_score": na,
        "summary": na,
        "validations": [na],
        "contradictions": [na],
        "missing_information": [na],
        "recommendations": [na],
        "risks": [na],
        "disclaimer": na,
        "source": "not_available",
    }

    top_crop = {
        "name": top_crop_name or na,
        "summary": groq_result.get("how_to_grow_summary", na),
        "ml_probability": na,
        "explanation_source": groq_result.get("source", "not_available"),
        "explanation": groq_result.get("explanation", na),
        "key_factors": groq_result.get("key_factors", [na]),
        "important_considerations": groq_result.get("key_factors", [na]),
        "states_where_it_grows": groq_result.get("states_where_it_grows", [na]),
        "did_you_know": groq_result.get("did_you_know", na),
        "weather_summary": na,
        "water_requirement": na,
        "irrigation_advice": na,
        "soil_compatibility": mistral_result["top_crop"].get("soil_compatibility", na) if mistral_success else na,
        "seasonal_compatibility": mistral_result["top_crop"].get("seasonal_compatibility", na) if mistral_success else na,
        "regional_compatibility": mistral_result["top_crop"].get("regional_compatibility", na) if mistral_success else na,
        "cultivation_risks": mistral_result["top_crop"].get("cultivation_risks", [na]) if mistral_success else [na],
        "suitability_score": mistral_result["top_crop"].get("suitability_score", na) if mistral_success else na,
    }

    alternatives = []
    for i, alt_name in enumerate(alt_names):
        alternatives.append({
            "name": alt_name,
            "suitability_score": alt_scores[i] if i < len(alt_scores) else na,
            "summary": na,
            "water_requirement": na,
            "season": na,
        })

    result = {
        "top_crop": top_crop,
        "alternatives": alternatives,
        "status": mistral_result.get("status", "error"),
        "error": mistral_result.get("error"),
        "disclaimer": "AI-generated crop recommendations. Consult local agricultural experts before major decisions.",
        "weather_context": {
            "temperature": weather.get("temperature", "Not available"),
            "humidity": weather.get("humidity", "Not available"),
            "condition": weather.get("description", "Not available"),
            "rainfall": weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0,
        },
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
        },
        "source": "mistral_ai",
        "validation": {
            "validation_status": validation_result.get("validation_status", na),
            "overall_score": validation_result.get("overall_score", na),
            "summary": validation_result.get("summary", na),
            "validations": validation_result.get("validations", [na]),
            "contradictions": validation_result.get("contradictions", [na]),
            "missing_information": validation_result.get("missing_information", [na]),
            "recommendations": validation_result.get("recommendations", [na]),
            "risks": validation_result.get("risks", [na]),
            "disclaimer": validation_result.get("disclaimer", na),
            "source": validation_result.get("source", "not_available"),
        },
    }

    return jsonify({"success": True, "data": result})


@crop_bp.route("/api/crop/search", methods=["GET"])
def api_search_crops():
    """REST API endpoint to search crops by name."""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"success": False, "error": "Query parameter 'q' is required"}), 400

    crops = search_crops(query)
    return jsonify({"success": True, "data": crops})


@crop_bp.route("/api/crop/suitability", methods=["POST"])
def api_crop_suitability():
    """REST API endpoint for crop suitability analysis (existing, preserved)."""
    data = request.get_json() or {}
    state = data.get("state", "Punjab")
    district = data.get("district", "Ludhiana")
    season = data.get("season", _get_automatic_season(state, district))
    soil_type = data.get("soil_type", "Alluvial")
    n = float(data.get("nitrogen", 90))
    p = float(data.get("phosphorus", 42))
    k = float(data.get("potassium", 43))
    ph = float(data.get("soil_ph", 6.5))
    irrigation = data.get("irrigation", "Canal irrigation")
    language = data.get("language", "en")

    # Fetch real-time weather
    weather = get_current_weather(state, district)

    # Get recommendation using the existing crop engine (preserved)
    ml_result = calculate_suitability(
        state=state,
        district=district,
        season=season,
        soil_type=soil_type,
        n=n,
        p=p,
        k=k,
        ph=ph,
        irrigation=irrigation,
    )

    top_crop = ml_result["top_crop"]
    alternatives = ml_result["alternatives"]

    result = {
        "top_crop": top_crop,
        "alternatives": alternatives,
        "validation": {
            "validation_status": "valid",
            "summary": "Recommendation generated based on ML model and agronomic rules.",
            "disclaimer": "Illustrative results. Consult a local agronomist before major crop decisions.",
        },
        "weather_context": {
            "temperature": weather.get("temperature", "Not available"),
            "humidity": weather.get("humidity", "Not available"),
            "condition": weather.get("description", "Not available"),
            "rainfall": weather.get("rainfall_1h") or weather.get("rainfall_3h") or 0,
        },
        "important_factors": [],
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
        },
        "source": "deterministic_ml",
        "ml_source": "crop_engine",
    }

    return jsonify({"success": True, "data": result})


def _save_recommendation_history(user: Dict, result: Dict) -> None:
    """Save recommendation to user's history in both session and MySQL."""
    try:
        history = session.get("recommendation_history", [])

        history_entry = {
            "id": len(history) + 1,
            "date": result.get("current_datetime", {}).get("date", ""),
            "activity": "Crop recommendation",
            "activity_type": "recommendation",
            "crop": result.get("top_crop", {}).get("name", "Unknown"),
            "location": result.get("farm_context", {}).get("district", ""),
            "state": result.get("farm_context", {}).get("state", ""),
            "result": result.get("status", "unknown"),
            "status": "View",
            "source": result.get("source", "unknown"),
            "details": {
                "top_crop": result.get("top_crop", {}).get("name", "Unknown"),
                "alternatives": result.get("alternatives", []),
                "season": result.get("farm_context", {}).get("season", ""),
                "soil": result.get("farm_context", {}).get("soil_type", ""),
                "irrigation": result.get("farm_context", {}).get("irrigation", ""),
                "weather": result.get("weather_display", {}),
                "error": result.get("error"),
            },
        }

        history.insert(0, history_entry)
        history = history[:50]

        session["recommendation_history"] = history
        session.modified = True

        # Also persist to MySQL database for cross-session history
        user_id = user.get("id")
        if user_id:
            top_crop = result.get("top_crop", {}) or {}
            farm_ctx = result.get("farm_context", {}) or {}
            details_json = json.dumps(history_entry.get("details", {}))
            conn = None
            cur = None
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO crop_suitability_history
                       (user_id, crop_id, state, district, season, soil_type, soil_ph,
                        n_value, p_value, k_value, irrigation, overall_score,
                        activity_type, tehsil, village, details, analysis_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                    (
                        user_id,
                        None,
                        farm_ctx.get("state", ""),
                        farm_ctx.get("district", ""),
                        farm_ctx.get("season", ""),
                        farm_ctx.get("soil_type", ""),
                        farm_ctx.get("ph"),
                        farm_ctx.get("n"),
                        farm_ctx.get("p"),
                        farm_ctx.get("k"),
                        farm_ctx.get("irrigation", ""),
                        top_crop.get("suitability_score"),
                        "recommendation",
                        "",
                        "",
                        details_json,
                    ),
                )
                conn.commit()
            except Error as e:
                logger.error("MySQL error saving recommendation history: %s", e)
            except Exception as e:
                logger.error("Unexpected error saving recommendation history to MySQL: %s", e)
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

    except Exception as e:
        logger.error("Failed to save recommendation history: %s", e)
