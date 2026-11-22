"""
data/store.py - In-memory and session data repository for Kisaan Suvidha
Provides initial realistic data matching the design PDF screenshots.
"""

from typing import Dict, Any, List

# Default logged-in user profile matching the PDF screenshots
USER_PROFILE = {
    "name": "Gurpreet Singh",
    "role": "Farmer",
    "mobile": "+91 98765 43210",
    "state": "Punjab",
    "district": "Ludhiana",
    "farm_size": "4.5",
    "soil_type": "Alluvial",
    "irrigation": "Canal irrigation",
    "preferred_language": "English",
    "password_updated": "08 July 2025",
    "is_verified": True
}

# History activity items matching Screen 10 from the PDF
HISTORY_RECORDS = [
    {
        "id": "rec_001",
        "date": "08 Jul 2025",
        "activity": "Crop recommendation",
        "activity_type": "recommendation",
        "crop": "Rice",
        "location": "Ludhiana",
        "result": "94 / 100 suitability",
        "status": "View",
        "details": {
            "ml_probability": "92%",
            "hybrid_suitability": "94 / 100",
            "confidence": "High",
            "soil_compat": "96%",
            "season_compat": "98%",
            "region_compat": "89%",
            "season": "Kharif",
            "soil": "Alluvial",
            "irrigation": "Canal irrigation"
        }
    },
    {
        "id": "rec_002",
        "date": "08 Jul 2025",
        "activity": "Weather analysis",
        "activity_type": "analysis",
        "crop": "Rice",
        "location": "Ludhiana",
        "result": "74% Moderate",
        "status": "View",
        "details": {
            "period": "08 — 14 July 2025",
            "good_days": 4,
            "poor_days": 1,
            "alert": "Watch the heat on 10 July: 36°C with low humidity"
        }
    },
    {
        "id": "rec_003",
        "date": "02 Jul 2025",
        "activity": "Crop recommendation",
        "activity_type": "recommendation",
        "crop": "Maize",
        "location": "Ludhiana",
        "result": "87 / 100 suitability",
        "status": "Saved",
        "details": {
            "ml_probability": "84%",
            "hybrid_suitability": "87 / 100",
            "confidence": "High",
            "soil_compat": "92%",
            "season_compat": "90%",
            "region_compat": "85%",
            "season": "Kharif",
            "soil": "Alluvial",
            "irrigation": "Canal irrigation"
        }
    },
    {
        "id": "rec_004",
        "date": "27 Jun 2025",
        "activity": "Weather analysis",
        "activity_type": "analysis",
        "crop": "Maize",
        "location": "Ludhiana",
        "result": "82% Good",
        "status": "Saved",
        "details": {
            "period": "27 Jun — 03 Jul 2025",
            "good_days": 5,
            "poor_days": 0,
            "alert": "Moderate rainfall expected on 29 June. Ensure drainage."
        }
    },
    {
        "id": "rec_005",
        "date": "21 Jun 2025",
        "activity": "Crop recommendation",
        "activity_type": "recommendation",
        "crop": "Rice",
        "location": "Ludhiana",
        "result": "91 / 100 suitability",
        "status": "Saved",
        "details": {
            "ml_probability": "89%",
            "hybrid_suitability": "91 / 100",
            "confidence": "High",
            "soil_compat": "96%",
            "season_compat": "95%",
            "region_compat": "89%",
            "season": "Kharif",
            "soil": "Alluvial",
            "irrigation": "Canal irrigation"
        }
    },
    {
        "id": "rec_006",
        "date": "15 Jun 2025",
        "activity": "Crop disease scan",
        "activity_type": "disease",
        "crop": "Rice (Paddy)",
        "location": "Ludhiana",
        "result": "Rice Blast (94.8% Conf)",
        "status": "View",
        "details": {
            "disease": "Rice Blast",
            "pathogen": "Magnaporthe oryzae",
            "severity": "Moderate",
            "chemical": "Tricyclazole 75% WP @ 0.6 g/L",
            "organic": "Pseudomonas fluorescens @ 10 g/L"
        }
    }
]

# Government Schemes catalog matching Screen 11 from the PDF
GOVERNMENT_SCHEMES = [
    {
        "id": "pm_kisan",
        "category": "income",
        "category_badge": "INCOME SUPPORT",
        "code": "PM-KISAN",
        "full_name": "Pradhan Mantri Kisan Samman Nidhi",
        "benefit": "Income support of ₹6,000 per year in three equal instalments for eligible landholding farmer families.",
        "requirements": "Check land records, Aadhaar and e-KYC requirements.",
        "url": "https://pmkisan.gov.in"
    },
    {
        "id": "pmfby",
        "category": "insurance",
        "category_badge": "CROP INSURANCE",
        "code": "PMFBY",
        "full_name": "Pradhan Mantri Fasal Bima Yojana",
        "benefit": "Crop insurance for notified crops against covered risks, subject to scheme terms and seasonal notifications.",
        "requirements": "Premiums and enrolment dates vary by crop and season. Only 2% for Kharif crops.",
        "url": "https://pmfby.gov.in"
    },
    {
        "id": "kcc",
        "category": "credit",
        "category_badge": "FARM CREDIT",
        "code": "Kisan Credit Card",
        "full_name": "KCC scheme",
        "benefit": "Access bank credit for eligible cultivation and related agricultural needs through participating banks.",
        "requirements": "Ask your bank about eligibility, limits and current terms. Concessional 4% interest rate with prompt repayment.",
        "url": "https://agricoop.nic.in"
    },
    {
        "id": "soil_card",
        "category": "soil",
        "category_badge": "SOIL HEALTH",
        "code": "Soil Health Card",
        "full_name": "National Soil Health Card Scheme",
        "benefit": "Free comprehensive soil nutrient testing every 2 years with custom macro/micronutrient recommendations.",
        "requirements": "Collect surface soil samples as per grid guidelines via local Krishi Vigyan Kendra.",
        "url": "https://soilhealth.dac.gov.in"
    },
    {
        "id": "pmksy",
        "category": "irrigation",
        "category_badge": "SUBSIDIES & EQUIPMENT",
        "code": "PMKSY",
        "full_name": "Pradhan Mantri Krishi Sinchayee Yojana",
        "benefit": "Up to 55% direct subsidy on micro-irrigation systems (drip & sprinkler setup) for water conservation.",
        "requirements": "Available for small and marginal landholders with verified water source.",
        "url": "https://pmksy.gov.in"
    }
]

# Support tickets memory store
SUPPORT_TICKETS = [
    {
        "id": "TICK-1082",
        "date": "07 Jul 2025",
        "name": "Gurpreet Singh",
        "mobile": "+91 98765 43210",
        "topic": "Crop recommendation",
        "subject": "Help understanding my soil inputs",
        "status": "In Progress"
    }
]
