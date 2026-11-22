"""
services/kisaanbot_engine.py - Multilingual AI Assistant Engine
Supports English, Hindi (हिन्दी), and Hinglish with contextual farm memory and domain expertise.
"""

from typing import Dict, Any, List, Optional
import re

DEFAULT_FARM_CONTEXT = {
    "farmer_name": "Gurpreet Singh",
    "state": "Punjab",
    "district": "Ludhiana",
    "soil_type": "Alluvial",
    "ph": 6.5,
    "farm_size": "4.5 acres",
    "irrigation": "Canal irrigation",
    "current_crop": "Rice (Paddy)",
    "season": "Kharif"
}

# Domain knowledge base partitioned by language
KNOWLEDGE_BASE = {
    "why_rice": {
        "en": (
            "Rice is a strong match for your farm because:\n\n"
            "1. **Your alluvial soil and pH of 6.5** are optimal for root nutrient uptake and paddy tillering.\n"
            "2. **Kharif warmth and monsoon rain** provide the required cumulative thermal units and natural moisture.\n"
            "3. **Your canal irrigation** reliably supports its critical water requirements during panicle initiation.\n\n"
            "💡 *Tip: Before sowing, check the specific variety (e.g., PR-126 or PR-131) and water plan with your local agricultural officer in Ludhiana.*"
        ),
        "hi": (
            "आपके खेत के लिए धान (चावल) की सिफारिश इन मुख्य कारणों से की गई है:\n\n"
            "1. **आपकी जलोढ़ (Alluvial) मिट्टी और 6.5 का pH मान** धान की जड़ों और कल्ले फूटने (tillering) के लिए सबसे उपयुक्त है।\n"
            "2. **खरीफ मौसम का तापमान और मानसूनी नमी** धान के स्वस्थ विकास के लिए आदर्श वातावरण प्रदान करती है।\n"
            "3. **नहरी सिंचाई (Canal irrigation)** फसल की कल्ले बनने और बालियां निकलने के समय पानी की मांग पूरी कर सकती है।\n\n"
            "💡 *सलाह: बुवाई से पहले लुधियाना के कृषि विज्ञान केंद्र या स्थानीय कृषि अधिकारी से उन्नत किस्मों (जैसे PR-126, PR-131) की जानकारी अवश्य लें।*"
        ),
        "hinglish": (
            "Aapke khet ke liye Rice (Paddy) recommend hone ke 3 main reasons hain:\n\n"
            "1. **Aapki Alluvial soil aur 6.5 pH value** rice crop ke liye ideal hai, jisse nutrients easily absorb hote hain.\n"
            "2. **Kharif season ka temperature aur monsoon moisture** paddy growth ke liye perfect environment banata hai.\n"
            "3. **Aapki canal irrigation facility** high water requirement wale critical stages par pani ki kami nahi hone degi.\n\n"
            "💡 *Pro-tip: Sowing se pehle Ludhiana local KVK se approved PR-126 ya PR-131 seed varieties ki availability check kar lein.*"
        )
    },
    "water_needs": {
        "en": (
            "**Water Management for Rice (Paddy):**\n\n"
            "• **Total requirement:** Approximately 1,200 to 1,500 mm of water throughout the Kharif season.\n"
            "• **Establishment stage (First 15 days):** Maintain 2–3 cm of standing water to promote rooting and suppress weeds.\n"
            "• **Tillering to Flowering:** Adopt **Alternate Wetting and Drying (AWD)**: irrigate 2 days after ponded water has infiltrated to save up to 25% water without yield reduction.\n"
            "• **Grain filling to maturity:** Keep soil moist; drain standing water 10-12 days before harvesting."
        ),
        "hi": (
            "**धान की फसल में जल प्रबंधन (Water Management):**\n\n"
            "• **कुल पानी की आवश्यकता:** पूरे खरीफ मौसम में लगभग 1,200 से 1,500 मिमी जल की आवश्यकता होती है।\n"
            "• **रोपाई के पहले 15 दिन:** खेत में 2-3 सेमी उथला पानी बनाए रखें ताकि खरपतवार न उगें और जड़ें जम सकें।\n"
            "• **कल्ले निकलने से फूल आने तक:** 'वैकल्पिक गीला और सूखा' (AWD) तरीका अपनाएं — पानी सूखने के 2 दिन बाद दोबारा पानी दें। इससे 25% पानी की बचत होती है।\n"
            "• **कटाई से पूर्व:** कटाई से 10-12 दिन पहले खेत से अतिरिक्त पानी निकाल दें।"
        ),
        "hinglish": (
            "**Rice crop ke liye Water Requirement & Irrigation:**\n\n"
            "• **Total Water:** Poore Kharif season mein lagbhag 1,200 – 1,500 mm water ki jarurat hoti hai.\n"
            "• **Pehle 15 din:** Field mein 2-3 cm shallow water maintain karein taaki weeds control rahein aur roots acche se settle ho sakein.\n"
            "• **Tillering se Flowering:** Alternate Wetting and Drying (AWD) technique use karein — jab pani zameen mein absorb ho jaye, uske 2 din baad hi agli irrigation karein. Isse 25% canal water save hota hai.\n"
            "• **Harvest se pehle:** Harvesting se 10-12 din pehle paani band kar dein."
        )
    },
    "soil_ph": {
        "en": (
            "**What your Soil pH (6.5) means:**\n\n"
            "• **Optimal Range:** A pH of 6.5 is nearly neutral (slightly acidic) — considered the **gold standard** in agronomy.\n"
            "• **Nutrient Availability:** Essential macronutrients (Nitrogen, Phosphorus, Potassium) and micronutrients (Zinc, Boron, Iron) have maximum solubility at this pH.\n"
            "• **No Corrective Amendments Needed:** You do not need to add agricultural lime (used for acidic soils < 5.5) or gypsum (used for alkaline/sodic soils > 8.0).\n"
            "• **Maintenance:** Continue incorporating organic matter (farmyard manure or green manuring with Dhaincha) to preserve biological microbial activity."
        ),
        "hi": (
            "**आपकी मिट्टी के pH मान (6.5) का अर्थ:**\n\n"
            "• **सर्वोत्तम स्तर:** 6.5 pH को कृषि विज्ञान में सर्वोत्तम 'गोल्डन रेंज' माना जाता है (हल्का अम्लीय से उदासीन)।\n"
            "• **पोषक तत्वों की उपलब्धता:** इस pH पर नाइट्रोजन, फॉस्फोरस, पोटाश के साथ-साथ जिंक और आयरन पौधों को बहुत आसानी से मिलते हैं।\n"
            "• **सुधारक की आवश्यकता नहीं:** आपको खेत में चूना (Lime) या जिप्सम (Gypsum) डालने की कोई आवश्यकता नहीं है।\n"
            "• **मिट्टी का रखरखाव:** गोबर की सड़ी खाद (FYM) या ढैंचा की हरी खाद का प्रयोग जारी रखें ताकि मिट्टी की उर्वरता बनी रहे।"
        ),
        "hinglish": (
            "**Aapki Soil pH 6.5 ka matlab aur fayde:**\n\n"
            "• **Near Perfect Range:** 6.5 pH ko agricultural science mein ideal neutral range maana jaata hai.\n"
            "• **Maximum Nutrient Absorption:** Is pH par N-P-K ke sath Zinc aur Iron plants ko sabse easily available hote hain.\n"
            "• **No Chemical Amendments Needed:** Aapko khet mein Lime ya Gypsum add karne ki koi jarurat nahi hai.\n"
            "• **Soil Care:** Bas har saal gobar ki compost khaad ya Dhaincha ki green manure use karte rahein taaki soil health strong bani rahe."
        )
    },
    "schemes": {
        "en": (
            "**Top Government Agricultural Schemes for your farm:**\n\n"
            "1. **PM-KISAN (Pradhan Mantri Kisan Samman Nidhi):**\n"
            "   • Direct bank transfer of **₹6,000 per year** in 3 equal instalments of ₹2,000.\n"
            "   • Requires verified land record mutations, Aadhaar, and active e-KYC.\n\n"
            "2. **PMFBY (Pradhan Mantri Fasal Bima Yojana):**\n"
            "   • Crop insurance covering non-preventable natural calamities, pests, and drought.\n"
            "   • Nominal premium: only **2% for Kharif crops** (Rice/Maize/Cotton).\n\n"
            "3. **Kisan Credit Card (KCC):**\n"
            "   • Flexible institutional credit up to ₹3,00,000 at an effective **4% interest rate** (with prompt repayment incentive).\n\n"
            "4. **Sub-Mission on Agricultural Mechanization (SMAM):**\n"
            "   • 40% to 50% subsidy on agricultural implements (happy seeder, laser leveler, super seeder)."
        ),
        "hi": (
            "**आपके खेत के लिए प्रमुख सरकारी कृषि योजनाएं:**\n\n"
            "1. **पीएम-किसान (PM-KISAN सम्मान निधि):**\n"
            "   • पात्र किसान परिवारों को प्रति वर्ष **₹6,000** की सहायता (₹2,000 की 3 किस्तों में)।\n"
            "   • इसके लिए आधार कार्ड, बैंक खाता और ई-केवाईसी (e-KYC) अनिवार्य है।\n\n"
            "2. **प्रधानमंत्री फसल बीमा योजना (PMFBY):**\n"
            "   • प्राकृतिक आपदा, सूखा, बाढ़ या कीट-रोग से फसल नुकसान होने पर वित्तीय सुरक्षा।\n"
            "   • खरीफ फसलों (धान, मक्का आदि) पर मात्र **2% प्रीमियम** देय है।\n\n"
            "3. **किसान क्रेडिट कार्ड (KCC):**\n"
            "   • बैंक से खेती की जरूरतों के लिए ₹3 लाख तक का सस्ता ऋण केवल **4% प्रभावी ब्याज दर** पर मिलता है।\n\n"
            "4. **कृषि यंत्रीकरण एवं पराली प्रबंधन सब्सिडी:**\n"
            "   • सुपर सीडर, लेजर लैंड लेवलर पर पंजाब सरकार द्वारा 40% से 50% तक की छूट।"
        ),
        "hinglish": (
            "**Aapke farm ke liye Top Government Schemes:**\n\n"
            "1. **PM-KISAN Samman Nidhi:**\n"
            "   • Har saal seedhe bank account mein **₹6,000** (₹2,000 ki 3 installments).\n"
            "   • Aadhaar aur e-KYC update hona jaruri hai.\n\n"
            "2. **PMFBY (Fasal Bima Yojana):**\n"
            "   • Kharif crops (Paddy/Maize) ke liye sirf **2% premium** par complete natural risk insurance cover milta hai.\n\n"
            "3. **Kisan Credit Card (KCC):**\n"
            "   • Fast loan up to ₹3 Lakhs at subsidized **4% interest** (time par repay karne par 3% interest subvention milti hai).\n\n"
            "4. **Machinery Subsidy:**\n"
            "   • Punjab mein Happy Seeder aur Super Seeder par 50% tak direct subsidy available hai."
        )
    },
    "disease_treatment": {
        "en": (
            "**Crop Disease Advisory:**\n\n"
            "• **Rice Blast:** If spindle-shaped spots appear, spray **Tricyclazole 75% WP @ 0.6 g/L** or Isoprothiolane 40% EC @ 1.5 mL/L.\n"
            "• **Wheat Yellow Rust:** At first sign of yellow striped powder on leaves, spray **Tilt (Propiconazole 25% EC) @ 1 mL/L** in 200 L water/acre.\n"
            "• **Tomato Late Blight:** Spray Metalaxyl-M + Mancozeb @ 2.5 g/L. Avoid overhead watering.\n"
            "• **Bio-Control:** You can also apply *Pseudomonas fluorescens* (10 g/L) or cold-pressed Neem oil (3,000 ppm) as organic preventive shields.\n\n"
            "Use our **AI Crop Disease Detection** tool to upload a photo for instant diagnosis!"
        ),
        "hi": (
            "**फसल रोग निदान एवं उपचार सलाह:**\n\n"
            "• **धान का झुलसा (Rice Blast):** यदि पत्तों पर आंखनुमा धब्बे दिखें, तो तुरंत **ट्राइसाइक्लाजोल 75% WP (0.6 ग्राम प्रति लीटर पानी)** का छिड़काव करें।\n"
            "• **गेहूं का पीला रतुआ (Yellow Rust):** पत्तों पर पीली धारियां दिखने पर **टिल्ट (प्रोपिकोनाजोल 25% EC) 1 मिली प्रति लीटर** के हिसाब से 200 लीटर पानी में मिलाकर स्प्रे करें।\n"
            "• **जैविक समाधान:** ट्राइकोडर्मा विरिडी या स्यूडोमोनास फ्लोरेसेंस (10 ग्राम/लीटर) और नीम तेल का छिड़काव प्रारंभिक अवस्था में बहुत प्रभावी रहता है।\n\n"
            "अपनी फसल के पत्ते का फोटो खींचकर सटीक जांच के लिए हमारे **AI Crop Disease Detection** पेज का उपयोग करें!"
        ),
        "hinglish": (
            "**Crop Disease Care & Fungicide Spray Advice:**\n\n"
            "• **Rice Blast:** Agar leaves par eye-shaped brown spots dikh rahe hain, toh **Tricyclazole 75% WP @ 0.6 g/L** ya Isoprothiolane spray karein.\n"
            "• **Wheat Stripe Rust:** Peeli dhariyan aane par **Propiconazole (Tilt) @ 1 ml/L** spray karein, preferably morning hours mein.\n"
            "• **Organic Protection:** Neem oil (3000 ppm @ 3 ml/L) ya *Pseudomonas fluorescens* natural bio-control ke liye best hain.\n\n"
            "Instant AI diagnosis ke liye sidebar mein **AI Disease Detection** option use karein aur leaf photo upload karein!"
        )
    },
    "fertilizer_guide": {
        "en": (
            "**Nutrient and Fertilizer Management for Alluvial Soil (Kharif Paddy):**\n\n"
            "• **Recommended Dose:** 120 kg Nitrogen, 30 kg Phosphorus, 30 kg Potassium per hectare.\n"
            "• **Basal Dose (at transplanting):** Apply full Phosphorus (DAP/SSP), full Potash (MOP), and 1/3rd of total Nitrogen.\n"
            "• **Top Dressing (Split 1):** Apply 1/3rd Nitrogen at 21 days after transplanting (active tillering).\n"
            "• **Top Dressing (Split 2):** Apply remaining 1/3rd Nitrogen at panicle initiation (around 42 days).\n"
            "• **Zinc Deficiency Alert:** Apply 25 kg Zinc Sulphate (21%) per hectare at puddling to prevent Khaira disease."
        ),
        "hi": (
            "**जलोढ़ मिट्टी में धान की फसल के लिए खाद व उर्वरक प्रबंधन:**\n\n"
            "• **अनुशंसित मात्रा:** प्रति हेक्टेयर 120 किग्रा नाइट्रोजन, 30 किग्रा फास्फोरस और 30 किग्रा पोटाश।\n"
            "• **बुवाई/रोपाई के समय (Basal):** फास्फोरस की पूरी मात्रा, पोटाश की पूरी मात्रा और नाइट्रोजन (यूरिया) का एक-तिहाई भाग दें।\n"
            "• **पहली टॉप ड्रेसिंग:** रोपाई के 21 दिन बाद (कल्ले फूटने के समय) यूरिया का दूसरा भाग दें।\n"
            "• **दूसरी टॉप ड्रेसिंग:** रोपाई के 42 दिन बाद (बालियां बनने की शुरुआत में) अंतिम भाग दें।\n"
            "• **जिंक की मात्रा:** खैरा रोग से बचाव के लिए कद्दू करते समय 25 किग्रा जिंक सल्फेट (21%) प्रति हेक्टेयर अवश्य डालें।"
        ),
        "hinglish": (
            "**Paddy Fertilizer & Nutrition Schedule:**\n\n"
            "• **Recommended NPK:** 120 kg Nitrogen, 30 kg Phosphorus, 30 kg Potash per hectare.\n"
            "• **Transplanting ke time (Basal dose):** Poora Phosphorus (DAP), poora Potash (MOP) aur 1/3rd Urea field prepare karte waqt dalein.\n"
            "• **21 din baad (Tillering stage):** Dusra 1/3rd Urea top dressing karein.\n"
            "• **42 din baad (Panicle initiation):** Bacha hua 1/3rd Urea dalein.\n"
            "• **Zinc alert:** Khaira disease se bachne ke liye 25 kg Zinc Sulphate (21%) per hectare puddling ke waqt zaroor dalein."
        )
    }
}


def process_kisaanbot_query(
    query: str,
    language: str = "en",
    farm_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates query intent and returns contextual multilingual response.
    """
    lang = language.lower()
    if lang in ["hi", "hindi", "हिन्दी"]:
        lang_key = "hi"
    elif lang in ["hinglish", "hi-en"]:
        lang_key = "hinglish"
    else:
        lang_key = "en"
        
    q = query.lower().strip()
    
    # 1. Matching intent
    if "why" in q and ("rice" in q or "recommend" in q or "paddy" in q or "dhan" in q or "kyun" in q):
        content = KNOWLEDGE_BASE["why_rice"][lang_key]
        intent = "why_rice"
    elif "water" in q or "pani" in q or "irrigation" in q or "paani" in q or "sinchai" in q or "सिंचाई" in q or "पानी" in q:
        content = KNOWLEDGE_BASE["water_needs"][lang_key]
        intent = "water_needs"
    elif "ph" in q or "soil" in q or "mitti" in q or "acidic" in q or "मिट्टी" in q:
        content = KNOWLEDGE_BASE["soil_ph"][lang_key]
        intent = "soil_ph"
    elif "scheme" in q or "pm-kisan" in q or "kisan credit" in q or "kcc" in q or "yojana" in q or "योजना" in q or "subsidy" in q or "bima" in q:
        content = KNOWLEDGE_BASE["schemes"][lang_key]
        intent = "schemes"
    elif "disease" in q or "blast" in q or "rust" in q or "fungus" in q or "pesticide" in q or "keeda" in q or "rog" in q or "रोग" in q or "spray" in q or "dawai" in q:
        content = KNOWLEDGE_BASE["disease_treatment"][lang_key]
        intent = "disease_treatment"
    elif "fertilizer" in q or "urea" in q or "dap" in q or "khat" in q or "khaad" in q or "खाद" in q or "npk" in q:
        content = KNOWLEDGE_BASE["fertilizer_guide"][lang_key]
        intent = "fertilizer_guide"
    else:
        # Generic helpful agricultural answer tailored to farmer context
        farmer_name = farm_context.get("farmer_name", "Gurpreet") if farm_context else "Gurpreet"
        if lang_key == "hi":
            content = (
                f"नमस्ते {farmer_name} जी! मैं किसानसुविधा का AI सहायक KisaanBot हूँ।\n\n"
                "मैं आपके खेत (लुधियाना, पंजाब - 4.5 एकड़, जलोढ़ मिट्टी) के लिए निम्नलिखित विषयों में सहायता कर सकता हूँ:\n"
                "• **फसल सिफारिश:** कौन सी फसल और किस्म आपके खेत के लिए सबसे लाभप्रद रहेगी।\n"
                "• **मौसम एवं सिंचाई:** आने वाले 7 दिनों का मौसम और सिंचाई योजना।\n"
                "• **रोग निदान:** पत्तों के रोग (जैसे राइस ब्लास्ट, गेहूं का रतुआ) और उनके उपचार।\n"
                "• **खाद एवं मिट्टी प्रबंधन:** NPK खाद का सटीक अनुपात और समय।\n"
                "• **सरकारी योजनाएं:** PM-KISAN, PMFBY फसल बीमा और KCC लोन।\n\n"
                "आप नीचे दिए गए त्वरित प्रश्नों पर भी क्लिक कर सकते हैं।"
            )
        elif lang_key == "hinglish":
            content = (
                f"Sat Sri Akal {farmer_name} ji! Main KisaanBot hoon — aapka personal agricultural AI companion.\n\n"
                "Main aapke 4.5 acre farm (Ludhiana, Alluvial soil) ke liye in cheezon mein help kar sakta hoon:\n"
                "• **Crop Selection:** Best Kharif & Rabi crops jo aapki soil mein highest yield dein.\n"
                "• **Fertilizer & Soil:** NPK, Urea, DAP dosage aur pH 6.5 ka sahi use.\n"
                "• **Disease Control:** Leaf upload karke instant disease diagnosis aur spray guidelines.\n"
                "• **Weather Alerts:** Rain and heatwave alerts ke hisab se field work scheduling.\n"
                "• **Sarkari Schemes:** PM-KISAN ₹6000, PMFBY crop insurance aur KCC credit card.\n\n"
                "Koi specific sawaal ho toh poochiye ya niche diye quick options par tap karein!"
            )
        else:
            content = (
                f"Hello {farmer_name}! I am KisaanBot, your smart agricultural assistant.\n\n"
                "I am tailored to your farm in Ludhiana, Punjab (4.5 acres, Alluvial soil, Canal irrigated).\n"
                "I can assist you with:\n"
                "• **Crop Recommendations & Cultivation practices** for Kharif and Rabi\n"
                "• **Soil Health & Fertilizer dosage** (NPK ratio, Urea splitting, pH 6.5)\n"
                "• **Leaf Disease Diagnosis** and targeted fungicide/biocontrol sprays\n"
                "• **7-Day Weather Suitability** and heatwave/rain scheduling\n"
                "• **Government Schemes** (PM-KISAN, PMFBY, KCC interest subvention)\n\n"
                "Feel free to ask any question or tap on the suggestion chips below!"
            )
        intent = "general_assistance"

    # Contextual suggestion chips based on intent and language
    suggestions = get_suggestions(intent, lang_key)

    return {
        "reply": content,
        "language": lang_key,
        "intent": intent,
        "suggestions": suggestions,
        "context": farm_context or DEFAULT_FARM_CONTEXT
    }


def get_suggestions(intent: str, lang: str) -> List[str]:
    """Provide intelligent prompt chips."""
    if lang == "hi":
        return [
            "धान के लिए पानी की कितनी आवश्यकता है?",
            "मेरी मिट्टी का pH क्या दर्शाता है?",
            "कौन सी सरकारी योजनाएं मेरे लिए हैं?",
            "झुलसा रोग से धान को कैसे बचाएं?"
        ]
    elif lang == "hinglish":
        return [
            "Rice ke liye kitna pani chahiye?",
            "Mera soil pH kaisa hai?",
            "Konsi schemes mere kaam ki hain?",
            "Paddy mein blast disease ka spray batao"
        ]
    else:
        return [
            "How much water does rice need?",
            "What does my soil pH mean?",
            "Which schemes can help me?",
            "Hinglish mein samjhao →"
        ]
