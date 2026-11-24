"""
services/intent_classifier.py - Intent classification and language detection
for KisaanBot.

Classifies user messages into:
- Language: en / hi / hinglish
- Greeting vs application query vs follow-up vs unrelated
- Relevant module: recommendation, suitability, disease_detection,
  cultivation_guide, history, navigation, account, kisaanbot, general_app

Uses rule-based pattern matching combined with keyword signals.  No external
LLM call is made for classification — this keeps greetings and invalid
queries cheap.
"""

from typing import Dict, Any, Optional, Tuple, List
import re

# ---------------------------------------------------------------------------
# Language detection patterns
# ---------------------------------------------------------------------------
HINDI_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
HINGLISH_HINDI_WORDS = {
    "kya", "kaise", "kyun", "kyunki", "hai", "hain", "hoon", "hota", "hoti",
    "hotay", "kar", "karte", "karta", "karti", "kiye", "karna", "mein", "mera",
    "meri", "mere", "aap", "aapka", "aapki", "mujhe", "main", "mai", "nahi",
    "nhi", "nahin", "nahiin", "haan", "han", "theek", "accha", "bura", "se",
    "ko", "ka", "ki", "ke", "par", "lekin", "magar", "parantu", "ya", "yaa",
    "aur", "le", "liye", "liya", "liye", "de", "diye", "dena", "diya", "di",
    "ja", "jao", "jaana", "jaana", "raha", "rahi", "rahe", "rahay", "tho",
    "tab", "ab", "abhi", "pehle", "baad", "saath", "sath", "kis", "kaun",
    "kahan", "kahaan", "kab", "kyon", "kyun", "kaise", "kitna", "kitne",
    "kuch", "kahi", "kuchhi", "sab", "sabhi", "kuchh", "koi", "kohi",
    "kahan", "wahan", "yahin", "vahan", "usne", "usne", "usne", "unhone",
    "unke", "unka", "unki", "unko", "nehi", "nahin", "na", "mat", "matlab",
    "bata", "batate", "batana", "bataya", "sun", "suno", "sunna", "suna",
    "dekh", "dekho", "dekhna", "dekha", "samajh", "samajho", "samajhna",
    "samajha", "pooch", "poocho", "poochna", "poocha", "kare", "karen",
    "karna", "kiya", "kiye", "kariya", "karega", "karegi", "karenge",
    "hoga", "hogi", "honge", "hongi", "tha", "thi", "the", "raha", "rahi",
    "rahe", "rahega", "rahegi", "rahenge", "lekin", "lekin", "agar", "to",
    "then", "tabhi", "tab tak", "tak", "se", "ko", "ka", "ki", "ke",
    "mera", "meri", "mere", "mera", "apna", "apni", "apne", "aapka", "aapki",
    "aapke", "tumhara", "tumhari", "tumhare", "uska", "uski", "uske",
    "unka", "unki", "unke", "iska", "iski", "iske", "yahaan", "wahaan",
    "kahan", "kahan se", "kahan tak", "kahan tak", "kahan se kahan tak",
    "aage", "peeche", "upar", "neeche", "andar", "bahar", "bheetar",
    "bahar", "pass", "ke paas", "ke saath", "ke bina", "ke liye",
    "ke baare mein", "ke liye", "ke against", "ke viruddh",
    "namaste", "sat sri akal", "ram ram", "namaskar",
}

HINGLISH_INDICATORS = {
    "hai", "hain", "hoon", "hota", "hoti", "kar", "karte", "karta", "karti",
    "kiye", "karna", "mein", "mera", "meri", "mere", "aap", "aapka", "aapki",
    "mujhe", "main", "nahi", "nhi", "theek", "accha", "se", "ko", "ka", "ki",
    "ke", "par", "lekin", "ya", "aur", "le", "liye", "liya", "de", "diye",
    "dena", "diya", "di", "ja", "jao", "raha", "rahi", "rahe", "tho", "tab",
    "ab", "abhi", "pehle", "baad", "saath", "kis", "kaun", "kahan", "kab",
    "kyun", "kaise", "kitna", "kitne", "kuch", "sab", "koi", "wahan", "yahin",
    "vahan", "usne", "unhone", "unke", "unka", "unki", "unko", "na", "mat",
    "matlab", "bata", "batate", "batana", "bataya", "sun", "suno", "sunna",
    "suna", "dekh", "dekho", "dekhna", "dekha", "samajh", "samajho", "samajhna",
    "samajha", "pooch", "poocho", "poochna", "poocha", "kare", "karen",
    "karna", "kiya", "kiye", "karega", "karegi", "karenge", "hoga", "hogi",
    "honge", "hongi", "tha", "thi", "the", "raha", "rahi", "rahe",
    "rahega", "rahegi", "rahenge", "agar", "to", "tabhi", "tak", "se", "ko",
    "ka", "ki", "ke", "mera", "meri", "mere", "apna", "apni", "apne",
    "aapka", "aapki", "aapke", "tumhara", "tumhari", "tumhare", "uska", "uski",
    "uske", "unka", "unki", "unke", "iska", "iski", "iske", "yahaan", "wahaan",
    "kahan", "kahan se", "kahan tak", "aage", "peeche", "upar", "neeche",
    "andar", "bahar", "bheetar", "pass", "ke paas", "ke saath", "ke bina",
    "ke liye", "ke baare mein", "ke against", "ke viruddh", "namaste",
    "sat sri akal", "ram ram", "namaskar",
}

# ---------------------------------------------------------------------------
# Greeting patterns (per language)
# ---------------------------------------------------------------------------
GREETING_PATTERNS: Dict[str, List[str]] = {
    "en": [
        r"\bhi\b", r"\bhello\b", r"\bhey\b", r"\bgood morning\b",
        r"\bgood afternoon\b", r"\bgood evening\b", r"\bgood night\b",
        r"\bthank you\b", r"\bthanks\b", r"\bwho are you\b",
    ],
    "hi": [
        r"\bnamaste\b", r"\bnamaskar\b", r"\bram ram\b",
        r"\bnamaste\b", r"\bnamsTe\b",
        r"\bshukriya\b", r"\bdhanyavad\b",
    ],
    "hinglish": [
        r"\bnamaste\b", r"\bnamaskar\b", r"\bhi\b", r"\bhello\b",
        r"\bgood morning\b", r"\bgood afternoon\b", r"\bgood evening\b",
        r"\bthank you\b", r"\bthanks\b", r"\bwho are you\b",
    ],
}


# ---------------------------------------------------------------------------
# Module / activity keyword patterns
# ---------------------------------------------------------------------------
MODULE_PATTERNS: Dict[str, List[str]] = {
    "recommendation": [
        r"\brecommend\w*", r"\brecommendation\b", r"\bcrop recommendation\b",
        r"\bwhy.*recommend\w*", r"\balternative crop\b", r"\btop crop\b",
        r"\brecommended crop\b", r"\bcrop name\b",
    ],
    "suitability": [
        r"\bsuitability\b", r"\bsuitable\b", r"\bsoil.*suit\b",
        r"\bsuitability score\b", r"\bsoil score\b", r"\bcrop suitability\b",
    ],
    "disease_detection": [
        r"\bdisease\b", r"\bplant disease\b", r"\bleaf\b", r"\blast\b",
        r"\brust\b", r"\bdetect\b.*disease", r"\bdiagnos\b", r"\bimage\b.*upload",
        r"\bupload.*image\b", r"\bleaf image\b",
    ],
    "cultivation_guide": [
        r"\bcultivation\b", r"\bguide\b", r"\birrigation\b", r"\bfertilizer\b",
        r"\bsowing\b", r"\bharvest\b", r"\bkhet\b", r"\bkheti\b",
    ],
    "history": [
        r"\bprevious\b", r"\bhistory\b", r"\bsaved\b", r"\bpast\b",
        r"\blast.*recommend\b", r"\brecord\b", r"\bearlier\b",
    ],
    "navigation": [
        r"\bnavigat\b", r"\bhow do i\b.*use\b", r"\bwhere\b.*find\b",
        r"\bwhere\b.*locat\b", r"\bmenu\b", r"\bpage\b", r"\bsection\b",
        r"\bgo to\b", r"\bopen\b", r"\baccess\b",
    ],
    "account": [
        r"\baccount\b", r"\bprofile\b", r"\blogin\b", r"\blogout\b",
        r"\bregister\b", r"\bverify\b", r"\bpassword\b", r"\bmobile\b",
    ],
    "kisaanbot": [
        r"\bkisaanbot\b", r"\bwho are you\b", r"\bwhat can you do\b",
        r"\byour function\b", r"\bwhat is kisaanbot\b",
    ],
    "general_app": [
        r"\bkisaan suvidha\b", r"\bapplication\b", r"\bapp\b",
        r"\bfeature\b", r"\bmodule\b", r"\bhelp\b", r"\bwork\b",
    ],
}

# Unrelated / out-of-scope keywords
UNRELATED_PATTERNS: List[str] = [
    r"\bpython\b", r"\bjava\b", r"\bprogramming\b", r"\bcode\b", r"\bjavascript\b",
    r"\bprime minister\b", r"\bpresident\b", r"\bpolitics\b", r"\bjoke\b",
    r"\bmathematics\b", r"\bmath\b", r"\balgebra\b", r"\bgeometry\b",
    r"\bcollege project\b", r"\bessay\b", r"\bstory\b", r"\bpoem\b",
    r"\bmovie\b", r"\bsong\b", r"\bmusic\b", r"\bsports\b", r"\bcricket\b",
    r"\bweather forecast\b", r"\btemperature\b.*\btoday\b",  # general weather, not app-specific
]


# ---------------------------------------------------------------------------
# Follow-up detection (short references to previous context)
# ---------------------------------------------------------------------------
FOLLOW_UP_PATTERNS: List[str] = [
    r"\bwhy\b", r"\bhow\b", r"\bwhat\b", r"\bwhich\b", r"\bwhere\b",
    r"\birrigation\b", r"\bfertilizer\b", r"\bsoil\b", r"\bwater\b",
    r"\bpesticide\b", r"\bdisease\b", r"\bscore\b", r"\bsuitable\b",
    r"\bguide\b", r"\bstage\b", r"\bharvest\b", r"\bsowing\b",
    r"\bexplain\b", r"\btell me\b", r"\bmore\b", r"\babout\b",
]


def detect_language(message: str) -> str:
    """Detect the language of the message: 'en', 'hi', or 'hinglish'.

    - If Devanagari script is present -> 'hi'
    - If Hinglish Hindi words are detected alongside English -> 'hinglish'
    - Otherwise -> 'en'
    """
    if not message or not message.strip():
        return "en"

    q = message.strip()

    # Devanagari script present => Hindi
    if HINDI_DEVANAGARI_RE.search(q):
        return "hi"

    # Count Hinglish Hindi words
    words = set(re.findall(r"\b[a-zA-Z]+\b", q.lower()))
    hinglish_count = len(words & HINGLISH_INDICATORS)

    if hinglish_count >= 2:
        return "hinglish"

    return "en"


def is_greeting(message: str, language: str = "en") -> Tuple[bool, Optional[str]]:
    """Check if the message is a greeting.

    Returns (is_greeting, matched_key) where matched_key can be used to
    retrieve a predefined response.
    """
    if not message or not message.strip():
        return False, None

    q = message.lower().strip()
    patterns = GREETING_PATTERNS.get(language, GREETING_PATTERNS["en"])
    # Also check other language patterns for cross-language greetings
    for lang_patterns in GREETING_PATTERNS.values():
        for pat in lang_patterns:
            if re.search(pat, q):
                # Extract a usable key
                key = pat.replace(r"\b", "").replace("\\", "").strip()
                return True, key

    return False, None


def classify_intent(
    message: str,
    language: str = "en",
    has_farmer_history: bool = False,
    last_discussed_crop: Optional[str] = None,
    conversation_context: str = "",
) -> Dict[str, Any]:
    """Classify the user's message into an intent and module.

    Returns a dict with:
      - language: detected language
      - is_greeting: bool
      - greeting_key: str | None
      - is_follow_up: bool
      - is_unrelated: bool
      - intent: str (one of the module keys or 'general_app' / 'unrelated')
      - module: str
      - confidence: float (0-1)
      - referenced_crop: str | None (crop name mentioned in the message)
    """
    if not message or not message.strip():
        return {
            "language": language,
            "is_greeting": False,
            "greeting_key": None,
            "is_follow_up": False,
            "is_unrelated": True,
            "intent": "unrelated",
            "module": "general_app",
            "confidence": 0.0,
            "referenced_crop": None,
        }

    q = message.strip().lower()

    # 1. Detect language
    detected_lang = detect_language(message)

    # 2. Check greeting
    is_greet, greet_key = is_greeting(message, detected_lang)
    if is_greet:
        return {
            "language": detected_lang,
            "is_greeting": True,
            "greeting_key": greet_key,
            "is_follow_up": False,
            "is_unrelated": False,
            "intent": "greeting",
            "module": "general_app",
            "confidence": 1.0,
            "referenced_crop": None,
        }

    # 3. Check for referenced crop names in the message
    referenced_crop = _extract_crop_reference(message, last_discussed_crop)

    # 4. Check if it's a short follow-up (no clear module keywords, but
    #    references previous context or uses follow-up words)
    has_module_keyword = False
    matched_module = "general_app"
    best_confidence = 0.0

    for module, patterns in MODULE_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                has_module_keyword = True
                matched_module = module
                best_confidence = max(best_confidence, 0.8)
                break
        if has_module_keyword:
            break

    # 5. Check for unrelated keywords
    is_unrelated = False
    for pat in UNRELATED_PATTERNS:
        if re.search(pat, q):
            is_unrelated = True
            break

    # 6. Determine follow-up status
    is_follow_up = False
    if not has_module_keyword:
        # Short message with follow-up words and prior context => follow-up
        words = q.split()
        if len(words) <= 6:
            for pat in FOLLOW_UP_PATTERNS:
                if re.search(pat, q):
                    is_follow_up = True
                    break
            # If there's conversation context and the message is short,
            # treat as follow-up even without explicit follow-up words
            if not is_follow_up and conversation_context and len(words) <= 4:
                is_follow_up = True

    # 7. Final intent determination
    if is_unrelated and not has_module_keyword:
        intent = "unrelated"
        module = "general_app"
        confidence = 0.9
    elif has_module_keyword:
        intent = matched_module
        module = matched_module
        confidence = best_confidence
    elif is_follow_up:
        # Follow-up inherits context; default to general_app or last module
        intent = "follow_up"
        module = "general_app"
        confidence = 0.6
    else:
        # No clear keywords, not unrelated, not greeting => general app query
        intent = "general_app"
        module = "general_app"
        confidence = 0.5

    return {
        "language": detected_lang,
        "is_greeting": False,
        "greeting_key": None,
        "is_follow_up": is_follow_up,
        "is_unrelated": is_unrelated and not has_module_keyword,
        "intent": intent,
        "module": module,
        "confidence": confidence,
        "referenced_crop": referenced_crop,
    }


def _extract_crop_reference(
    message: str,
    last_discussed_crop: Optional[str],
) -> Optional[str]:
    """Try to extract a crop name mentioned in the message.

    First checks for an explicit crop name in the message, then falls back
    to the last discussed crop from conversation memory.
    """
    if not message:
        return last_discussed_crop

    q = message.lower()

    # Look for crop-like words in common recommendation context
    # This is a lightweight extraction — actual crop names come from DB
    crop_indicators = [
        r"\b(rice|paddy|धान)\b",
        r"\b(wheat|गेहूं)\b",
        r"\b(maize|makka|मक्का)\b",
        r"\b(cotton|kapas|कपास)\b",
        r"\b(sugarcane|ganna|गन्ना)\b",
        r"\b(gram|chickpea|chana|चना)\b",
        r"\b(potato|aloo|आलू)\b",
        r"\b(millet|bajra|बाजरा)\b",
    ]

    for pat in crop_indicators:
        m = re.search(pat, q)
        if m:
            return m.group(1).title()

    return last_discussed_crop