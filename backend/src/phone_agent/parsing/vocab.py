"""Word tables used by the phone number parser.

Every entry maps a spoken token (lower-cased) to ``(digits, language)`` where
``language`` is ``"en"`` or ``"hi"``. Hindi entries cover both romanised
(Hinglish) spellings and Devanagari, because STT engines emit either depending
on the model and on how much English the speaker mixes in.

Only *deterministic* lookups live here — no fuzzy matching, no LLM.
"""

from __future__ import annotations

EN = "en"
HI = "hi"

# ---------------------------------------------------------------------------
# Single digits (0-9)
# ---------------------------------------------------------------------------
_EN_DIGITS: dict[str, str] = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0", "naught": "0", "zeero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    # English digit names as Devanagari transliterations (Deepgram "multi"
    # sometimes writes English words spoken by Hindi speakers this way).
    "ज़ीरो": "0", "जीरो": "0", "वन": "1", "टू": "2", "थ्री": "3", "फोर": "4", "फ़ोर": "4",
    "फाइव": "5", "फ़ाइव": "5", "सिक्स": "6", "सेवन": "7", "एट": "8", "नाइन": "9",
}

_HI_DIGITS: dict[str, str] = {
    # 0
    "shunya": "0", "shoonya": "0", "shunye": "0", "sunya": "0",
    "sifar": "0", "sifr": "0", "sefar": "0",
    "शून्य": "0", "शुन्य": "0", "सिफ़र": "0", "सिफर": "0",
    # 1
    "ek": "1", "aek": "1", "एक": "1",
    # 2
    "do": "2", "doh": "2", "दो": "2",
    # 3
    "teen": "3", "tin": "3", "तीन": "3",
    # 4
    "char": "4", "chaar": "4", "chār": "4", "चार": "4",
    # 5
    "paanch": "5", "panch": "5", "paach": "5", "paanc": "5",
    "पांच": "5", "पाँच": "5", "पाच": "5",
    # 6
    "chhe": "6", "chhah": "6", "chah": "6", "che": "6", "chhai": "6", "chhey": "6",
    "chheh": "6", "chhay": "6",
    "छह": "6", "छः": "6", "छे": "6", "छै": "6", "छ": "6",
    # 7
    "saat": "7", "sat": "7", "सात": "7",
    # 8
    "aath": "8", "ath": "8", "aat": "8", "आठ": "8",
    # 9
    "nau": "9", "nao": "9", "nou": "9", "नौ": "9",
    # Urdu script (Whisper sometimes transcribes Hindi speech in it)
    "صفر": "0", "ایک": "1", "دو": "2", "تین": "3", "چار": "4", "پانچ": "5",
    "چھ": "6", "چھے": "6", "سات": "7", "آٹھ": "8", "نو": "9", "نَو": "9",
}

# ---------------------------------------------------------------------------
# Multi-digit number words.
# People often group a phone number as "ninety eight, seventy six ..." or in
# Hindi "atthaanve, chhihattar ...". Each word expands to its full digit string.
# ---------------------------------------------------------------------------
_EN_TEENS: dict[str, str] = {
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
}

# Tens can combine with a following unit ("ninety eight" -> 98). The parser
# handles that composition; on their own they expand to "x0".
EN_TENS: dict[str, str] = {
    "twenty": "2", "thirty": "3", "forty": "4", "fourty": "4", "fifty": "5",
    "sixty": "6", "seventy": "7", "eighty": "8", "ninety": "9",
}

# Romanised Hindi 10-99. Spellings follow the most common Hinglish forms.
_HI_ROMAN_10_99: dict[int, tuple[str, ...]] = {
    10: ("das",), 11: ("gyarah", "gyara"), 12: ("barah", "baarah", "bara"),
    13: ("terah", "tera"), 14: ("chaudah", "chauda"), 15: ("pandrah", "pandra"),
    16: ("solah", "sola"), 17: ("satrah", "satra"), 18: ("atharah", "athara", "attharah"),
    19: ("unnis", "unees"),
    20: ("bees", "bis"), 21: ("ikkees", "ikkis"), 22: ("baees", "bais", "baais"),
    23: ("teis",), 24: ("chaubees", "chaubis"), 25: ("pachees", "pachchis", "pachis"),
    26: ("chhabbees", "chhabbis"), 27: ("sattaees", "sattais"), 28: ("atthaees", "atthais"),
    29: ("untees", "untis"),
    30: ("tees", "tis"), 31: ("iktees", "iktis"), 32: ("battees", "battis"),
    33: ("taintees", "taintis"), 34: ("chauntees", "chauntis"), 35: ("paintees", "paintis"),
    36: ("chhattees", "chhattis"), 37: ("saintees", "saintis"), 38: ("adtees", "artees", "adtis"),
    39: ("untalees", "untalis"),
    40: ("chaalees", "chalees", "chalis"), 41: ("iktalees", "iktalis"),
    42: ("bayalees", "bayalis"), 43: ("taintalees", "taintalis"),
    44: ("chauvalees", "chauvalis", "chavalis"), 45: ("paintalees", "paintalis"),
    46: ("chhiyalees", "chhiyalis"), 47: ("saintalees", "saintalis"),
    48: ("adtalees", "adtalis", "artalis"), 49: ("unchaas", "unchas"),
    50: ("pachaas", "pachas"), 51: ("ikyavan", "ikyaavan"), 52: ("baavan", "bavan"),
    53: ("tirpan", "tirepan"), 54: ("chauvan", "chauvvan"), 55: ("pachpan",),
    56: ("chhappan",), 57: ("sattavan", "sattaavan"), 58: ("atthavan", "atthaavan"),
    59: ("unsath", "unsaath"),
    60: ("saath",), 61: ("iksath", "iksaath"), 62: ("baasath", "basath"),
    63: ("tirsath", "tiresath"), 64: ("chaunsath",), 65: ("painsath",),
    66: ("chhiyasath", "chhiyaasath"), 67: ("sadsath", "sarsath"), 68: ("adsath", "arsath"),
    69: ("unhattar",),
    70: ("sattar",), 71: ("ikhattar", "ikahattar"), 72: ("bahattar",),
    73: ("tihattar",), 74: ("chauhattar",), 75: ("pachhattar", "pachattar"),
    76: ("chhihattar", "chhehattar"), 77: ("satattar", "satahattar"),
    78: ("athhattar", "athattar"), 79: ("unaasi", "unasi", "unyasi"),
    80: ("assi",), 81: ("ikyaasi", "ikyasi"), 82: ("bayaasi", "bayasi"),
    83: ("tiraasi", "tirasi"), 84: ("chauraasi", "chaurasi"), 85: ("pachaasi", "pachasi"),
    86: ("chhiyaasi", "chhiyasi"), 87: ("sattaasi", "sattasi"), 88: ("athaasi", "athasi", "atthasi"),
    89: ("navaasi", "navasi", "nawasi"),
    90: ("nabbe", "nabbay"), 91: ("ikyaanve", "ikyanve", "ikyanbe"),
    92: ("baanve", "banve", "baanbe"), 93: ("tiraanve", "tiranve"),
    94: ("chauraanve", "chauranve"), 95: ("pachaanve", "pachanve"),
    96: ("chhiyaanve", "chhiyanve"), 97: ("sattaanve", "sattanve"),
    98: ("atthaanve", "atthanve", "athanve"), 99: ("ninyaanve", "ninyanve", "ninnyanve"),
}

# Devanagari 10-99.
_HI_DEVANAGARI_10_99: dict[int, tuple[str, ...]] = {
    10: ("दस",), 11: ("ग्यारह",), 12: ("बारह",), 13: ("तेरह",), 14: ("चौदह",),
    15: ("पंद्रह", "पन्द्रह"), 16: ("सोलह",), 17: ("सत्रह",), 18: ("अठारह",), 19: ("उन्नीस",),
    20: ("बीस",), 21: ("इक्कीस",), 22: ("बाईस",), 23: ("तेईस",), 24: ("चौबीस",),
    25: ("पच्चीस",), 26: ("छब्बीस",), 27: ("सत्ताईस",), 28: ("अट्ठाईस", "अठाईस"), 29: ("उनतीस",),
    30: ("तीस",), 31: ("इकतीस",), 32: ("बत्तीस",), 33: ("तैंतीस",), 34: ("चौंतीस",),
    35: ("पैंतीस",), 36: ("छत्तीस",), 37: ("सैंतीस",), 38: ("अड़तीस",), 39: ("उनतालीस",),
    40: ("चालीस",), 41: ("इकतालीस",), 42: ("बयालीस",), 43: ("तैंतालीस",), 44: ("चवालीस", "चौवालीस"),
    45: ("पैंतालीस",), 46: ("छियालीस",), 47: ("सैंतालीस",), 48: ("अड़तालीस",), 49: ("उनचास",),
    50: ("पचास",), 51: ("इक्यावन",), 52: ("बावन",), 53: ("तिरपन",), 54: ("चौवन",),
    55: ("पचपन",), 56: ("छप्पन",), 57: ("सत्तावन",), 58: ("अट्ठावन",), 59: ("उनसठ",),
    60: ("साठ",), 61: ("इकसठ",), 62: ("बासठ",), 63: ("तिरसठ",), 64: ("चौंसठ",),
    65: ("पैंसठ",), 66: ("छियासठ",), 67: ("सड़सठ",), 68: ("अड़सठ",), 69: ("उनहत्तर",),
    70: ("सत्तर",), 71: ("इकहत्तर",), 72: ("बहत्तर",), 73: ("तिहत्तर",), 74: ("चौहत्तर",),
    75: ("पचहत्तर",), 76: ("छिहत्तर",), 77: ("सतहत्तर",), 78: ("अठहत्तर",), 79: ("उन्यासी", "उनासी"),
    80: ("अस्सी",), 81: ("इक्यासी",), 82: ("बयासी",), 83: ("तिरासी",), 84: ("चौरासी",),
    85: ("पचासी",), 86: ("छियासी",), 87: ("सत्तासी",), 88: ("अट्ठासी",), 89: ("नवासी",),
    90: ("नब्बे",), 91: ("इक्यानवे",), 92: ("बानवे",), 93: ("तिरानवे",), 94: ("चौरानवे",),
    95: ("पचानवे",), 96: ("छियानवे",), 97: ("सत्तानवे",), 98: ("अट्ठानवे",), 99: ("निन्यानवे",),
}


def _expand(table: dict[int, tuple[str, ...]]) -> dict[str, str]:
    return {word: str(value) for value, words in table.items() for word in words}


# Final lookup: token -> (digits, language). Hindi tables are applied last so
# that a romanised Hindi spelling never gets shadowed by an English word.
NUMBER_WORDS: dict[str, tuple[str, str]] = {
    **{w: (d, EN) for w, d in _EN_DIGITS.items()},
    **{w: (d, EN) for w, d in _EN_TEENS.items()},
    **{w: (d, HI) for w, d in _HI_DIGITS.items()},
    **{w: (d, HI) for w, d in _expand(_HI_ROMAN_10_99).items()},
    **{w: (d, HI) for w, d in _expand(_HI_DEVANAGARI_10_99).items()},
}

# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------
# "double seven" -> 77, "triple nine" -> 999
MULTIPLIERS: dict[str, tuple[int, str]] = {
    "double": (2, EN), "dubble": (2, EN), "triple": (3, EN), "tripple": (3, EN),
    "quadruple": (4, EN),
    "dabal": (2, HI), "dabbal": (2, HI), "tripal": (3, HI),
    "डबल": (2, HI), "ट्रिपल": (3, HI), "ڈبل": (2, HI), "ٹرپل": (3, HI),
}

# "nine hundred" -> 900, "nine hundred eighty seven" -> 987
HUNDRED_WORDS: dict[str, str] = {"hundred": EN, "sau": HI, "सौ": HI}
THOUSAND_WORDS: dict[str, str] = {
    "thousand": EN, "hazaar": HI, "hazar": HI, "हज़ार": HI, "हजार": HI,
}

# ---------------------------------------------------------------------------
# Self-correction markers. When one of these appears, every digit spoken
# *before* it is discarded and collection restarts from what follows.
# Bare English "no" is deliberately NOT a marker: Hindi "nau" (9) is very
# often transcribed as "no".
# ---------------------------------------------------------------------------
CORRECTION_MARKERS: tuple[tuple[str, ...], ...] = (
    ("wait",), ("sorry",), ("oops",), ("actually",), ("scratch", "that"),
    ("i", "mean"), ("no", "no"), ("no", "wait"), ("let", "me", "repeat"),
    ("let", "me", "start", "again"), ("start", "again"), ("start", "over"),
    ("one", "more", "time"), ("from", "the", "start"), ("wrong",),
    ("ruko",), ("rukiye",), ("galat",), ("galti",), ("nahi",), ("nahin",),
    ("matlab",), ("phir", "se"), ("fir", "se"), ("dobara",),
    ("रुको",), ("रुकिए",), ("सॉरी",), ("गलत",), ("ग़लत",), ("नहीं",), ("मतलब",),
    ("फिर", "से"), ("दोबारा",),
)

# ---------------------------------------------------------------------------
# Yes / no detection for the confirmation step.
# ---------------------------------------------------------------------------
YES_WORDS: frozenset[str] = frozenset({
    "yes", "yeah", "yep", "yup", "ya", "correct", "right", "sure", "okay", "ok",
    "exactly", "absolutely", "perfect", "confirm", "confirmed",
    "haan", "han", "haa", "ha", "haanji", "ji", "jee", "sahi", "theek", "thik", "bilkul",
    "हाँ", "हां", "हा", "जी", "सही", "ठीक", "बिल्कुल", "बिलकुल",
})
NO_WORDS: frozenset[str] = frozenset({
    "no", "nope", "nah", "wrong", "incorrect", "not",
    "nahi", "nahin", "galat", "mat",
    "नहीं", "नही", "ना", "गलत", "ग़लत",
})
