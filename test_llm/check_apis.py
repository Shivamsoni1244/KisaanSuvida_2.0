"""
test_llm/check_apis.py - Standalone LLM API tester (does NOT touch the project)

Tests each LLM provider independently using example inputs matching the project's
request/response format. Run from terminal:

    cd C:\\Users\\shubh\\Desktop\\Kisaan Suvida 2.0\\test_llm
    ..\\venv\\Scripts\\python.exe check_apis.py

Three separate Groq keys are tested independently:
  - Groq #1 (explanations): GROQ_API_KEY
  - Groq #2 (validation):   GROQ_API_KEY_2
  - Groq #3 (crop guide):   GROQ_API_KEY_3

Groq #2 and #3 depend on Mistral output, so they receive a sample Mistral result
as input (simulating what the project would pass).
"""

import json
import os
from dotenv import load_dotenv
import requests

# ---------------------------------------------------------------------------
# 1. Load .env from the project root (independent of the app package)
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH, override=True)

MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL_1", "mistral-small-latest")
MISTRAL_BASE = os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

GROQ_KEY_1 = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL_1 = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_BASE_1 = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

GROQ_KEY_2 = os.environ.get("GROQ_API_KEY_2", "")
GROQ_MODEL_2 = os.environ.get("GROQ_MODEL_2", "llama-3.1-8b-instant")
GROQ_BASE_2 = os.environ.get("GROQ_BASE_URL_2", "https://api.groq.com/openai/v1")

GROQ_KEY_3 = os.environ.get("GROQ_API_KEY_3", "")
GROQ_MODEL_3 = os.environ.get("GROQ_MODEL_3", "llama-3.1-8b-instant")
GROQ_BASE_3 = os.environ.get("GROQ_BASE_URL_3", "https://api.groq.com/openai/v1")

OPENWEATHER_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# ---------------------------------------------------------------------------
# Example farm context (matches what the project sends to Mistral)
# ---------------------------------------------------------------------------
EXAMPLE_FARM_CONTEXT = {
    "state": "Punjab",
    "district": "Ludhiana",
    "season": "Kharif",
    "soil_type": "Alluvial",
    "n": 90.0,
    "p": 42.0,
    "k": 43.0,
    "ph": 6.5,
    "irrigation": "Canal irrigation",
    "soil_values_source": "estimated",
}

EXAMPLE_WEATHER = {
    "source": "openweathermap",
    "temperature": 28.5,
    "humidity": 72,
    "description": "scattered clouds",
    "condition": "Clouds",
    "rainfall_1h": 2.0,
    "rainfall_3h": 5.0,
}

# Sample Mistral result (what Groq #2 and #3 receive as input)
SAMPLE_MISTRAL_RESULT = {
    "status": "success",
    "top_crop": {
        "name": "Rice (Paddy)",
        "suitability_score": 87,
        "soil_compatibility": 85,
        "seasonal_compatibility": 90,
        "regional_compatibility": 88,
        "water_requirement": "High",
        "cultivation_risks": ["Waterlogging", "Pest pressure"],
    },
    "alternatives": [
        {"name": "Maize", "suitability_score": 80},
        {"name": "Cotton", "suitability_score": 75},
    ],
}

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _print_result(label, ok, body):
    status = "OK" if ok else "FAIL"
    print(f"[{label}] {status}")
    if isinstance(body, dict):
        print(json.dumps(body, indent=2)[:800])
    else:
        print(str(body)[:800])
    print("-" * 60)


def _call_groq(key, model, base_url, prompt, label):
    if not key or key.startswith("your_"):
        _print_result(label, False, {"error": f"{label} API key not set"})
        return None
    try:
        r = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 1500},
            timeout=30,
        )
        ok = r.status_code == 200
        body = r.json() if ok else {"status_code": r.status_code, "text": r.text[:500]}
        _print_result(label, ok, body)
        return body if ok else None
    except Exception as e:
        _print_result(label, False, {"error": f"{type(e).__name__}: {e}"})
        return None


# ---------------------------------------------------------------------------
# Mistral (independent)
# ---------------------------------------------------------------------------
def test_mistral():
    print("=" * 60)
    print("TEST: Mistral AI (independent)")
    print("=" * 60)
    if not MISTRAL_KEY or MISTRAL_KEY.startswith("your_"):
        _print_result("Mistral", False, {"error": "MISTRAL_API_KEY not set"})
        return None

    prompt = (
        "You are an expert agricultural advisor for Indian farmers. "
        "Recommend exactly one primary crop and two alternatives based ONLY on "
        "the farmer's inputs. Return ONLY valid JSON:\n"
        '{"status":"success","top_crop":{"name":"Crop","soil_compatibility":85,'
        '"seasonal_compatibility":90,"regional_compatibility":88,"cultivation_risks":[],'
        '"suitability_score":87},"alternatives":[{"name":"Alt1","suitability_score":80},'
        '{"name":"Alt2","suitability_score":75}]}'
    )

    try:
        r = requests.post(
            f"{MISTRAL_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"},
            json={"model": MISTRAL_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 1000},
            timeout=30,
        )
        ok = r.status_code == 200
        body = r.json() if ok else {"status_code": r.status_code, "text": r.text[:500]}
        _print_result("Mistral", ok, body)
        return body if ok else None
    except Exception as e:
        _print_result("Mistral", False, {"error": f"{type(e).__name__}: {e}"})
        return None


# ---------------------------------------------------------------------------
# Groq #1 - Explanations (independent)
# ---------------------------------------------------------------------------
def test_groq_1():
    print("=" * 60)
    print("TEST: Groq #1 - Explanations (independent)")
    print("=" * 60)
    prompt = (
        "Explain why Rice (Paddy) is suitable for a farm in Punjab, Ludhiana "
        "during Kharif season with alluvial soil. Return ONLY valid JSON.\n"
        '{"explanation":"","key_factors":[],"states_where_it_grows":[],'
        '"did_you_know":"","how_to_grow_summary":""}'
    )
    return _call_groq(GROQ_KEY_1, GROQ_MODEL_1, GROQ_BASE_1, prompt, "Groq #1")


# ---------------------------------------------------------------------------
# Groq #2 - Validation (depends on Mistral output)
# ---------------------------------------------------------------------------
def test_groq_2(mistral_result):
    print("=" * 60)
    print("TEST: Groq #2 - Validation (depends on Mistral top_crop)")
    print("=" * 60)
    prompt = (
        "You are an expert agricultural validator for Indian farmers. Validate the following "
        "crop recommendation. Return ONLY valid JSON.\n"
        f"FARM CONTEXT: {json.dumps(EXAMPLE_FARM_CONTEXT)}\n"
        f"WEATHER: {json.dumps(EXAMPLE_WEATHER)}\n"
        f"RECOMMENDATION: {json.dumps(mistral_result if mistral_result else SAMPLE_MISTRAL_RESULT)}\n"
        'Return: {"validation_status":"valid","overall_score":85,"summary":"","validations":[],'
        '"contradictions":[],"missing_information":[],"recommendations":[],"risks":[],'
        '"disclaimer":""}'
    )
    return _call_groq(GROQ_KEY_2, GROQ_MODEL_2, GROQ_BASE_2, prompt, "Groq #2")


# ---------------------------------------------------------------------------
# Groq #3 - Crop Guide Part 1 (depends on Mistral output)
# ---------------------------------------------------------------------------
def test_groq_3_part1(mistral_result):
    print("=" * 60)
    print("TEST: Groq #3 - Crop Guide Part 1 (depends on Mistral output)")
    print("=" * 60)
    crop_name = (
        mistral_result.get("top_crop", {}).get("name", "Rice (Paddy)")
        if mistral_result
        else "Rice (Paddy)"
    )
    prompt = (
        f"You are an expert agricultural advisor for Indian farmers. Provide Part 1 of the "
        f"detailed cultivation guide for {crop_name}. Return ONLY valid JSON.\n"
        f"FARM CONTEXT: {json.dumps(EXAMPLE_FARM_CONTEXT)}\n"
        f"WEATHER: {json.dumps(EXAMPLE_WEATHER)}\n"
        'Return: {"crop_name":"","hindi_name":"","scientific_name":"","introduction":"",'
        '"climate_temperature":"","rainfall_requirements":"","soil_types":"",'
        '"recommended_ph":"","land_preparation":"","seed_selection":"","seed_treatment":"",'
        '"seed_rate":"","sowing_time":"","sowing_method":"","spacing_row":"",'
        '"spacing_plant":"","fertilizer_requirements":"","nitrogen_management":"",'
        '"phosphorus_management":"","potassium_management":"","organic_fertilizer":"",'
        '"nutrient_deficiency":"","irrigation_requirements":"","irrigation_frequency":"",'
        '"critical_irrigation_stages":"","drip_sprinkler":"","waterlogging_precautions":""}'
    )
    return _call_groq(GROQ_KEY_3, GROQ_MODEL_3, GROQ_BASE_3, prompt, "Groq #3 (Part 1)")


# ---------------------------------------------------------------------------
# Groq #3 - Crop Guide Part 2 (depends on Mistral output)
# ---------------------------------------------------------------------------
def test_groq_3_part2(mistral_result):
    print("=" * 60)
    print("TEST: Groq #3 - Crop Guide Part 2 (depends on Mistral output)")
    print("=" * 60)
    crop_name = (
        mistral_result.get("top_crop", {}).get("name", "Rice (Paddy)")
        if mistral_result
        else "Rice (Paddy)"
    )
    prompt = (
        f"You are an expert agricultural advisor for Indian farmers. Provide Part 2 of the "
        f"detailed cultivation guide for {crop_name}. Return ONLY valid JSON.\n"
        f"FARM CONTEXT: {json.dumps(EXAMPLE_FARM_CONTEXT)}\n"
        f"WEATHER: {json.dumps(EXAMPLE_WEATHER)}\n"
        'Return: {"common_weeds":"","weed_manual_control":"","weed_preventive":"",'
        '"herbicide_precautions":"","common_pests":"","common_diseases":"",'
        '"pest_symptoms":"","pest_preventive":"","ipm":"","biological_control":"",'
        '"pesticide_precautions":"","growth_stage_germination":"",'
        '"growth_stage_seedling":"","growth_stage_vegetative":"",'
        '"growth_stage_flowering":"","growth_stage_fruit_grain":"",'
        '"growth_stage_maturity":"","harvesting_signs":"","harvesting_time":"",'
        '"harvesting_method":"","crop_duration_days":120,"expected_yield":"",'
        '"post_harvest_cleaning":"","post_harvest_drying":"","post_harvest_storage":"",'
        '"post_harvest_transport":"","precautions":"","disclaimer":""}'
    )
    return _call_groq(GROQ_KEY_3, GROQ_MODEL_3, GROQ_BASE_3, prompt, "Groq #3 (Part 2)")


# ---------------------------------------------------------------------------
# OpenWeather (independent)
# ---------------------------------------------------------------------------
def test_openweather():
    print("=" * 60)
    print("TEST: OpenWeatherMap (independent)")
    print("=" * 60)
    if not OPENWEATHER_KEY or OPENWEATHER_KEY.startswith("your_"):
        _print_result("OpenWeather", False, {"error": "OPENWEATHER_API_KEY not set"})
        return

    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": "Ludhiana,IN", "appid": OPENWEATHER_KEY, "units": "metric"},
            timeout=15,
        )
        ok = r.status_code == 200
        body = r.json() if ok else {"status_code": r.status_code, "text": r.text[:500]}
        _print_result("OpenWeather", ok, body)
    except Exception as e:
        _print_result("OpenWeather", False, {"error": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("LLM API Standalone Tester (3x Groq keys, no Gemini)")
    print(f"Project root: {PROJECT_ROOT}")
    print(f".env loaded: {os.path.exists(ENV_PATH)}")
    print()

    mistral_result = test_mistral()
    print()
    test_groq_1()
    print()
    test_groq_2(mistral_result)
    print()
    test_groq_3_part1(mistral_result)
    print()
    test_groq_3_part2(mistral_result)
    print()
    test_openweather()

    print()
    print("Done. Each API tested independently.")
    print("Groq #2 and #3 received a sample Mistral recommendation as input (dependency simulation).")
