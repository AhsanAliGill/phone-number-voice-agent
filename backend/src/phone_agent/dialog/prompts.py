"""Every sentence the agent can say, in English and Hindi.

Prompts without placeholders are *static*: they are synthesised once and
served from the TTS cache (see ``agent/tts_cache.py``).
"""

from __future__ import annotations

from typing import Literal

PromptLang = Literal["en", "hi"]

_DIGIT_NAMES: dict[PromptLang, tuple[str, ...]] = {
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
    "hi": ("शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"),
}

PROMPTS: dict[str, dict[PromptLang, str]] = {
    "greeting": {
        "en": "Hello! Please tell me your 10-digit mobile number.",
        "hi": "नमस्ते! कृपया अपना 10 अंकों का मोबाइल नंबर बताइए।",
    },
    "ask_number": {
        "en": "Please tell me your 10-digit mobile number.",
        "hi": "कृपया अपना 10 अंकों का मोबाइल नंबर बताइए।",
    },
    "ask_again": {
        "en": "No problem. Please tell me your full mobile number again.",
        "hi": "कोई बात नहीं। कृपया अपना पूरा मोबाइल नंबर फिर से बताइए।",
    },
    "too_few": {
        "en": "I only got {count} digits. Could you repeat your full number?",
        "hi": "मुझे सिर्फ़ {count} अंक मिले। क्या आप अपना पूरा नंबर दोबारा बता सकते हैं?",
    },
    "too_many": {
        "en": "I got {count} digits, which is more than ten. Please say your 10-digit number again.",
        "hi": "मुझे {count} अंक मिले, जो दस से ज़्यादा हैं। कृपया अपना 10 अंकों का नंबर फिर से बताइए।",
    },
    "invalid": {
        "en": "That doesn't look like a valid mobile number. Please try again.",
        "hi": "यह सही मोबाइल नंबर नहीं लगता। कृपया फिर से कोशिश करें।",
    },
    "unclear_segment": {
        "en": "Sorry, I couldn't hear that last part clearly. Please repeat just that part.",
        "hi": "माफ़ कीजिए, आखिरी हिस्सा साफ़ सुनाई नहीं दिया। कृपया सिर्फ़ वह हिस्सा दोहराइए।",
    },
    "unclear_number": {
        "en": "Sorry, it's a bit noisy and I couldn't hear that clearly. Please say your mobile number again.",
        "hi": "माफ़ कीजिए, आवाज़ साफ़ नहीं आई। कृपया अपना मोबाइल नंबर फिर से बताइए।",
    },
    "confirm": {
        "en": "Let me confirm — your number is {spoken}. Is that correct?",
        "hi": "मैं कन्फ़र्म कर लूँ — आपका नंबर है {spoken}। क्या यह सही है?",
    },
    "confirm_yes_no": {
        "en": "Please say yes or no. Is your number {spoken}?",
        "hi": "कृपया हाँ या ना में बताइए। क्या आपका नंबर {spoken} है?",
    },
    "saved": {
        "en": "Thank you! Your number has been saved.",
        "hi": "धन्यवाद! आपका नंबर सेव हो गया है।",
    },
    "save_failed": {
        "en": "Sorry, I couldn't save your number right now. Please try again later.",
        "hi": "माफ़ कीजिए, अभी आपका नंबर सेव नहीं हो पाया। कृपया बाद में कोशिश करें।",
    },
}


def render(key: str, lang: PromptLang, **kwargs: object) -> str:
    return PROMPTS[key][lang].format(**kwargs)


def is_static(key: str) -> bool:
    return "{" not in PROMPTS[key]["en"]


def static_prompts(langs: tuple[PromptLang, ...] = ("en", "hi")) -> list[str]:
    """All texts that never change — these are pre-synthesised at startup."""
    return [PROMPTS[key][lang] for key in PROMPTS if is_static(key) for lang in langs]


def spell_digits(digits: str, lang: PromptLang) -> str:
    """Read a number back digit by digit, never as one word.

    "9876543210" -> "nine, eight, seven, six, five... four, three, two, one, zero"
    The pause between the two halves mirrors how Indian numbers are grouped.
    """
    names = [_DIGIT_NAMES[lang][int(d)] for d in digits]
    half = len(names) // 2
    return ", ".join(names[:half]) + "... " + ", ".join(names[half:])
