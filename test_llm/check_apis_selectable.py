"""
test_llm/check_apis.py - Standalone LLM API tester (does NOT touch the project)

Tests each LLM provider independently using example inputs matching the project's
request/response format. Run from terminal:

    cd C:\\Users\\shubh\\Desktop\\Kisaan Suvida 2.0\\test_llm
    ..\\venv\\Scripts\\python.exe check_apis.py

Groq and Gemini depend on Mistral output, so they receive a sample Mistral result
as input (simulating what the project would pass).
"""

import json
import os
import sys
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

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_BASE = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-4-argon")
GEMINI_BASE = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")

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
# Groq (depends on Mistral output -> uses sample recommendation)
# ---------------------------------------------------------------------------
def test_groq(mistral_result):
    print("=" * 60)
    print("TEST: Groq AI (depends on Mistral top_crop)")
    print("=" * 60)
    if not GROQ_KEY or GROQ_KEY.startswith("your_"):
        _print_result("Groq", False, {"error": "GROQ_API_KEY not set"})
        return

    top_crop = {
        "name": "Rice (Paddy)",
        "suitability_score": 87,
        "soil_compatibility": 85,
        "seasonal_compatibility": 90,
        "regional_compatibility": 88,
        "water_requirement": "High",
    }
    alternatives = [
        {"name": "Maize", "suitability_score": 80, "hindi_name": "मक्का", "season": "Kharif", "water_requirement": "Medium", "summary": "Alternative grain crop"},
        {"name": "Cotton", "suitability_score": 75, "hindi_name": "कपास", "season": "Kharif", "water_requirement": "Medium", "summary": "Cash crop alternative"},
    ]

    prompt = (
        "You are an expert agricultural advisor for Indian farmers. Analyze alternative crops "
        "for a farmer's situation. Return ONLY valid JSON.\n"
        f"FARM CONTEXT: {json.dumps(EXAMPLE_FARM_CONTEXT)}\n"
        f"TOP CROP: {json.dumps(top_crop)}\n"
        f"ALTERNATIVES: {json.dumps(alternatives)}\n"
        'Return: {"alternative_crops":[{"name":"","suitability_score":0,"summary":"","water_requirement":"","season":""}],"comparison_summary":"","disclaimer":""}'
    )

    try:
        r = requests.post(
            f"{GROQ_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "messages": [{"role": "system", "content": "Return only valid JSON."}, {"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 1500},
            timeout=30,
        )
        ok = r.status_code == 200
        body = r.json() if ok else {"status_code": r.status_code, "text": r.text[:500]}
        _print_result("Groq", ok, body)
    except Exception as e:
        _print_result("Groq", False, {"error": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------------------
# Gemini (depends on Mistral output -> uses sample recommendation)
# ---------------------------------------------------------------------------
def test_gemini(mistral_result):
    print("=" * 60)
    print("TEST: Gemini AI (depends on Mistral recommendation)")
    print("=" * 60)
    if not GEMINI_KEY or GEMINI_KEY.startswith("your_"):
        _print_result("Gemini", False, {"error": "GEMINI_API_KEY not set"})
        return

    recommendation = mistral_result if mistral_result else {
        "top_crop": {"name": "Rice (Paddy)", "suitability_score": 87, "soil_compatibility": 85, "seasonal_compatibility": 90, "regional_compatibility": 88, "water_requirement": "High"},
        "alternatives": [{"name": "Maize", "suitability_score": 80}, {"name": "Cotton", "suitability_score": 75}],
    }

    prompt = (
        "You are an expert agricultural validator for Indian farmers. Validate the following "
        "crop recommendation. Return ONLY valid JSON.\n"
        f"FARM CONTEXT: {json.dumps(EXAMPLE_FARM_CONTEXT)}\n"
        f"WEATHER: {json.dumps(EXAMPLE_WEATHER)}\n"
        f"RECOMMENDATION: {json.dumps(recommendation)}\n"
        'Return: {"validation_status":"valid","overall_score":85,"summary":"","validations":[],"contradictions":[],"missing_information":[],"recommendations":[],"risks":[],"disclaimer":""}'
    )

    try:
        r = requests.post(
            f"{GEMINI_BASE.rstrip('/')}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500}},
            timeout=30,
        )
        ok = r.status_code == 200
        body = r.json() if ok else {"status_code": r.status_code, "text": r.text[:500]}
        _print_result("Gemini", ok, body)
    except Exception as e:
        _print_result("Gemini", False, {"error": f"{type(e).__name__}: {e}"})


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
# Main - interactive test selection
# ---------------------------------------------------------------------------
def show_menu():
    print("=" * 60)
    print("LLM API Standalone Tester")
    print("=" * 60)
    print("Select which API you want to test:")
    print("  1. Gemini only")
    print("  2. Groq only")
    print("  3. Mistral only")
    print("  4. OpenWeatherMap only")
    print("  5. Test all APIs")
    print("  0. Exit")
    print("-" * 60)


def main():
    print(f"Project root: {PROJECT_ROOT}")
    print(f".env loaded: {os.path.exists(ENV_PATH)}")
    print()

    while True:
        show_menu()
        choice = input("Enter your choice (0-5): ").strip()

        if choice == "1":
            # Uses the sample recommendation; does NOT call Mistral.
            test_gemini(None)
        elif choice == "2":
            # Uses the sample crop data; does NOT call Mistral.
            test_groq(None)
        elif choice == "3":
            test_mistral()
        elif choice == "4":
            test_openweather()
        elif choice == "5":
            mistral_result = test_mistral()
            test_groq(mistral_result)
            test_gemini(mistral_result)
            test_openweather()
        elif choice == "0":
            print("Exiting tester.")
            break
        else:
            print("Invalid choice. Please enter a number from 0 to 5.")

        print()


if __name__ == "__main__":
    main()
