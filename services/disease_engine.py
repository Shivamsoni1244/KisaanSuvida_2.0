"""
services/disease_engine.py - AI Crop Disease Detection Engine
Botanical pathology engine offering diagnostic evaluation, symptoms, remedies,
and clean hooks for PyTorch / TensorFlow / ONNX Deep Learning models.
"""

import os
from typing import Dict, Any, Optional, List

# Agricultural pathology database
DISEASE_CATALOG = {
    "rice_blast": {
        "id": "rice_blast",
        "crop": "Rice (Paddy)",
        "disease_name": "Rice Blast",
        "scientific_name": "Magnaporthe oryzae",
        "pathogen_type": "Fungal Pathogen",
        "default_confidence": 94.8,
        "severity": "Moderate Severity",
        "severity_badge": "action_required",
        "description": "Rice blast is one of the most destructive diseases affecting rice crops worldwide. It causes spindle-shaped lesions with ash-grey centers and brownish-red borders on leaf blades and neck nodes.",
        "symptoms": [
            "Spindle-shaped (eye-shaped) lesions on leaf blades with pointed ends",
            "Ash-grey or whitish center with distinct brown or reddish-brown margins",
            "Lesions coalesce under high humidity leading to complete leaf blighting",
            "Node and neck rot leading to empty panicles ('neck blast')"
        ],
        "chemical_treatment": [
            "Spray Tricyclazole 75% WP @ 0.6 g/L or Isoprothiolane 40% EC @ 1.5 mL/L of water.",
            "Apply Azoxystrobin 18.2% + Difenoconazole 11.4% SC @ 1 mL/L at the first appearance of leaf lesions.",
            "Repeat spray after 10-12 days if damp cloudy conditions persist."
        ],
        "organic_treatment": [
            "Foliar spray of Pseudomonas fluorescens @ 10 g/L or 2.5 kg/ha in 500 L water.",
            "Spray cold-pressed Neem seed kernel extract (NSKE 5%) or 3000 ppm Neem oil @ 3 mL/L.",
            "Apply fermented cow urine and sour buttermilk solution (1:10 dilution) as a natural antifungal biostimulant."
        ],
        "preventive_practices": [
            "Avoid excessive split applications of Nitrogen fertilizer (especially urea overdose).",
            "Maintain optimal plant spacing to avoid dense canopy humidity.",
            "Adopt alternate wetting and drying (AWD) water management rather than continuous deep submergence.",
            "Treat seed before sowing with Carbendazim 2g/kg or Trichoderma viride 10g/kg."
        ],
        "kisaanbot_prompt": "How can I prevent Rice Blast from spreading to the panicle neck on my 4.5 acre farm?"
    },
    "tomato_late_blight": {
        "id": "tomato_late_blight",
        "crop": "Tomato",
        "disease_name": "Tomato Late Blight",
        "scientific_name": "Phytophthora infestans",
        "pathogen_type": "Oomycete Fungus",
        "default_confidence": 92.4,
        "severity": "High Severity",
        "severity_badge": "urgent",
        "description": "Late blight is a fast-spreading disease favored by cool, moist weather. It causes dark water-soaked patches on foliage and firm, greasy lesions on green fruit.",
        "symptoms": [
            "Irregular pale green to dark brown water-soaked lesions on older leaves",
            "Delicate white fungal downy growth visible on leaf undersides in morning dew",
            "Rapid browning and collapse of stems and foliage ('blight' appearance)",
            "Dark brown, leathery blemishes on green tomato fruits"
        ],
        "chemical_treatment": [
            "Spray Metalaxyl-M 4% + Mancozeb 64% WP @ 2.5 g/L immediately upon detection.",
            "Alternate with Cymoxanil 8% + Mancozeb 64% WP @ 2 g/L after 7 days.",
            "Apply Copper oxychloride 50% WP @ 3 g/L as a protective canopy shield."
        ],
        "organic_treatment": [
            "Apply Trichoderma harzianum or Bacillus subtilis foliar spray @ 5 g/L.",
            "Spray copper-based Bordeaux mixture (1%) as an approved organic fungicide.",
            "Prune lower infected leaves using sterilized pruning shears and burn or bury infected debris."
        ],
        "preventive_practices": [
            "Avoid overhead sprinkler irrigation; use drip irrigation to keep foliage dry.",
            "Stake tomato plants and increase row spacing for adequate air circulation.",
            "Rotate crops away from Solanaceae family (potato, tomato, eggplant) for at least 2 seasons."
        ],
        "kisaanbot_prompt": "What is the best fungicide schedule for late blight on tomatoes during cloudy monsoon days?"
    },
    "wheat_stripe_rust": {
        "id": "wheat_stripe_rust",
        "crop": "Wheat",
        "disease_name": "Wheat Yellow / Stripe Rust",
        "scientific_name": "Puccinia striiformis f. sp. tritici",
        "pathogen_type": "Fungal Pathogen",
        "default_confidence": 96.1,
        "severity": "High Severity",
        "severity_badge": "urgent",
        "description": "Stripe rust is a major fungal threat in Northern wheat-growing regions like Punjab and Haryana. Bright yellow pustules erupt in linear stripes parallel to leaf veins.",
        "symptoms": [
            "Bright yellow powder-filled pustules (urediniospores) aligned in narrow linear stripes",
            "Yellow dusty spores easily rub off onto fingers or clothing",
            "Premature drying, yellowing and scorch of flag leaves",
            "Shriveled grain formation and severe test-weight reduction"
        ],
        "chemical_treatment": [
            "Spray Propiconazole 25% EC (Tilt) @ 1 mL/L or 200 mL in 200 L water per acre.",
            "Alternatively, apply Tebuconazole 25.9% EC @ 1 mL/L.",
            "Spray thoroughly covering the flag leaf and upper canopy foliage."
        ],
        "organic_treatment": [
            "Foliar spray of 10% cow urine solution with freshly crushed garlic extract.",
            "Soil drenching and foliar application of Bio-fertilizers enriched with Trichoderma.",
            "Apply wood ash dusting in early morning dew."
        ],
        "preventive_practices": [
            "Sow certified rust-resistant wheat varieties recommended by PAU (such as PBW-824, PBW-803, DBW-187).",
            "Avoid late sowing (complete sowing by mid-November in Punjab).",
            "Scout border rows and field corners weekly during January and February."
        ],
        "kisaanbot_prompt": "How many sprays of Tilt (Propiconazole) are needed for wheat yellow rust in Ludhiana?"
    },
    "cotton_leaf_curl": {
        "id": "cotton_leaf_curl",
        "crop": "Cotton",
        "disease_name": "Cotton Leaf Curl Disease (CLCuD)",
        "scientific_name": "Begomovirus / Whitefly vector",
        "pathogen_type": "Viral Disease (Vector-Borne)",
        "default_confidence": 91.5,
        "severity": "High Severity",
        "severity_badge": "urgent",
        "description": "A devastating viral disease transmitted by the silverleaf whitefly (Bemisia tabaci). It causes upward leaf curling, vein thickening, and leaf enations (cup-like outgrowths).",
        "symptoms": [
            "Upward cupping and curling of leaf margins on younger leaves",
            "Thickening of major and minor leaf veins visible on leaf undersides",
            "Small leaf-like enations developing underneath the main veins",
            "Stunted plant growth and severely reduced boll formation"
        ],
        "chemical_treatment": [
            "Spray Diafenthiuron 50% WP @ 1.2 g/L or Pyriproxyfen 10% EC @ 2 mL/L to control whitefly vector.",
            "Alternate with Afidopyropen 50 g/L DC @ 2 mL/L for quick whitefly knockdown.",
            "Ensure spray nozzles direct mist to the underside of the leaf canopy where whiteflies harbor."
        ],
        "organic_treatment": [
            "Install yellow sticky traps (15-20 traps per acre) at canopy height to capture whiteflies.",
            "Spray Neem oil 10,000 ppm @ 2 mL/L or 5% NSKE (Neem Seed Kernel Extract).",
            "Spray Verticillium lecanii (entomopathogenic fungus) @ 5 g/L during humid hours."
        ],
        "preventive_practices": [
            "Eradicate alternative weed hosts (like Kanghi buti, Peeli buti, Congress grass) along field bunds.",
            "Select CLCuD-tolerant Bt cotton hybrids approved for the Northern zone.",
            "Avoid excessive vegetative growth caused by surplus urea."
        ],
        "kisaanbot_prompt": "What is the recommended spray threshold for whiteflies to stop leaf curl in cotton?"
    },
    "healthy_crop": {
        "id": "healthy_crop",
        "crop": "Rice / General",
        "disease_name": "Healthy Crop Foliage",
        "scientific_name": "No Pathogen Detected",
        "pathogen_type": "Healthy Plant Tissue",
        "default_confidence": 98.7,
        "severity": "Normal / Healthy",
        "severity_badge": "healthy",
        "description": "The scanned leaf shows deep chlorophyll pigmentation, active stomatal integrity, and absence of necrotic lesions or pest puncture marks. The plant is thriving under optimal nourishment.",
        "symptoms": [
            "Vigorous green leaf blade with uniform coloration",
            "Absence of fungal pustules, necrotic halos, or bacterial water-soaking",
            "Strong turgor pressure and erect leaf architecture",
            "Healthy vascular veins without discoloration or vein clearing"
        ],
        "chemical_treatment": [
            "No chemical pesticide or fungicide intervention is required.",
            "Continue standard scheduled macro and micronutrient management."
        ],
        "organic_treatment": [
            "Periodic foliar spray of seaweed extract (2 mL/L) or Panchagavya (3%) to maintain immunity.",
            "Maintain soil organic carbon with farmyard manure (FYM) or vermicompost."
        ],
        "preventive_practices": [
            "Continue regular weekly field scouting across all farm corners.",
            "Maintain clean irrigation channels and weed-free field borders.",
            "Follow balanced NPK fertilization as per your soil health test."
        ],
        "kisaanbot_prompt": "My crop is healthy today. What preventive care should I take during monsoon humidity?"
    }
}


def diagnose_crop_image(
    filename: Optional[str] = None,
    crop_hint: Optional[str] = None,
    sample_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Simulates ML/CNN inference on an uploaded or sample leaf image.
    In production, this function connects to:
      - PyTorch model (`torch.load('crop_resnet50.pt')`)
      - ONNX runtime (`ort.InferenceSession('crop_disease.onnx')`)
      - TensorFlow Lite model
    """
    # 1. If explicit sample requested
    if sample_id and sample_id in DISEASE_CATALOG:
        return DISEASE_CATALOG[sample_id]
        
    # 2. Check filename keywords for realistic automatic matching
    if filename:
        name_lower = filename.lower()
        if "blast" in name_lower or "paddy" in name_lower or "rice" in name_lower:
            return DISEASE_CATALOG["rice_blast"]
        elif "blight" in name_lower or "tomato" in name_lower:
            return DISEASE_CATALOG["tomato_late_blight"]
        elif "rust" in name_lower or "wheat" in name_lower:
            return DISEASE_CATALOG["wheat_stripe_rust"]
        elif "cotton" in name_lower or "curl" in name_lower:
            return DISEASE_CATALOG["cotton_leaf_curl"]
        elif "healthy" in name_lower:
            return DISEASE_CATALOG["healthy_crop"]

    # 3. Check crop hint
    if crop_hint:
        hint_lower = crop_hint.lower()
        if "rice" in hint_lower or "paddy" in hint_lower:
            return DISEASE_CATALOG["rice_blast"]
        elif "tomato" in hint_lower:
            return DISEASE_CATALOG["tomato_late_blight"]
        elif "wheat" in hint_lower:
            return DISEASE_CATALOG["wheat_stripe_rust"]
        elif "cotton" in hint_lower:
            return DISEASE_CATALOG["cotton_leaf_curl"]

    # Default to Rice Blast (matches the primary crop in the design mockups)
    return DISEASE_CATALOG["rice_blast"]


def get_all_samples() -> List[Dict[str, str]]:
    """Return lightweight list of sample diseases for UI quick-testing."""
    return [
        {"id": "rice_blast", "name": "Rice Blast", "crop": "Rice (Paddy)"},
        {"id": "tomato_late_blight", "name": "Tomato Late Blight", "crop": "Tomato"},
        {"id": "wheat_stripe_rust", "name": "Wheat Yellow Rust", "crop": "Wheat"},
        {"id": "cotton_leaf_curl", "name": "Cotton Leaf Curl", "crop": "Cotton"},
        {"id": "healthy_crop", "name": "Healthy Paddy Leaf", "crop": "Rice (Healthy)"},
    ]
