"""Deterministic spoken-phone-number parser.

``parse_phone_number(transcript)`` turns raw STT text into a digit string.

Pipeline:
    1. normalise   – lower-case, Devanagari digits -> ASCII, strip punctuation
    2. tokenise    – split on whitespace, split digit runs away from letters
    3. correction  – drop everything before the last self-correction marker
    4. classify    – map each token to a typed item (unit / number / tens /
                     multiplier / hundred / thousand), ignore filler words
    5. compose     – combine items into digits ("ninety eight" -> 98,
                     "double seven" -> 77, "nine hundred" -> 900, ...)
    6. validate    – strip +91 / leading 0, check 10 digits starting with 6-9

No LLM and no fuzzy matching is involved, so the same transcript always
produces the same number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .vocab import (
    CORRECTION_MARKERS,
    EN,
    EN_TENS,
    HI,
    HUNDRED_WORDS,
    LEAD_IN_WORDS,
    MULTIPLIERS,
    NO_WORDS,
    NUMBER_WORDS,
    THOUSAND_WORDS,
    YES_WORDS,
)

Language = Literal["en", "hi", "mixed"]

PHONE_LENGTH = 10
VALID_FIRST_DIGITS = frozenset("6789")

# Devanagari, Arabic-Indic and Extended Arabic-Indic (Urdu) digits -> ASCII
_DEVANAGARI_DIGITS = str.maketrans(
    "०१२३४५६७८९٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "0123456789" * 3
)
# Keep word characters, whitespace, the Devanagari block and Arabic-script
# marks (vowel signs are not matched by \w). The danda "।" / "॥" and the Urdu
# full stop "۔" are punctuation, so they go.
_PUNCTUATION = re.compile(r"[^\w\sऀ-ॣ०-ॿً-ٰٟ]|_|۔")
_DIGIT_RUN = re.compile(r"[0-9]+|[^0-9]+")


class ParseError(str, Enum):
    NO_DIGITS = "no_digits"
    TOO_FEW = "too_few"
    TOO_MANY = "too_many"
    INVALID_PREFIX = "invalid_prefix"


@dataclass(frozen=True)
class ParseResult:
    digits: str
    """All digits recovered from the transcript (country code removed)."""
    language: Language
    corrected: bool = False
    """True when a self-correction marker caused earlier digits to be dropped."""
    error: ParseError | None = None
    tokens: tuple[str, ...] = field(default=(), repr=False)

    @property
    def digit_count(self) -> int:
        return len(self.digits)

    @property
    def is_valid(self) -> bool:
        return self.error is None

    @property
    def number(self) -> str | None:
        """The validated 10-digit number, or ``None``."""
        return self.digits if self.is_valid else None


# ---------------------------------------------------------------------------
# Step 1 + 2: normalise and tokenise
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> list[str]:
    text = text.lower().translate(_DEVANAGARI_DIGITS)
    text = _PUNCTUATION.sub(" ", text)
    tokens: list[str] = []
    for chunk in text.split():
        # "98765abc" -> ["98765", "abc"]; keeps STT numerals intact
        tokens.extend(_DIGIT_RUN.findall(chunk))
    return tokens


# ---------------------------------------------------------------------------
# Step 3: self-correction
# ---------------------------------------------------------------------------
def _apply_corrections(tokens: list[str]) -> tuple[list[str], bool]:
    """Return the tokens after the last correction marker.

    "nine eight seven wait sorry nine eight six seven" -> "nine eight six seven"
    """
    cut = -1
    for i in range(len(tokens)):
        for marker in CORRECTION_MARKERS:
            if tuple(tokens[i : i + len(marker)]) == marker:
                cut = max(cut, i + len(marker))
    if cut < 0:
        return tokens, False
    return tokens[cut:], True


# ---------------------------------------------------------------------------
# Step 4: classify tokens
# ---------------------------------------------------------------------------
@dataclass
class _Item:
    kind: Literal["unit", "number", "tens", "mult", "hundred", "thousand"]
    value: str = ""  # digits for unit/number/tens, repeat count for mult
    lang: str | None = None  # None for raw numerals ("98765")


def _classify(tokens: list[str]) -> list[_Item]:
    items: list[_Item] = []
    for tok in tokens:
        if tok.isdigit():
            # Raw numerals from STT ("98765"). A single digit behaves like a
            # spoken unit so that "double 7" and "9 hundred" still work.
            items.append(_Item("unit" if len(tok) == 1 else "number", tok))
        elif tok in NUMBER_WORDS:
            digits, lang = NUMBER_WORDS[tok]
            items.append(_Item("unit" if len(digits) == 1 else "number", digits, lang))
        elif tok in EN_TENS:
            items.append(_Item("tens", EN_TENS[tok], EN))
        elif tok in MULTIPLIERS:
            count, lang = MULTIPLIERS[tok]
            items.append(_Item("mult", str(count), lang))
        elif tok in HUNDRED_WORDS:
            items.append(_Item("hundred", lang=HUNDRED_WORDS[tok]))
        elif tok in THOUSAND_WORDS:
            items.append(_Item("thousand", lang=THOUSAND_WORDS[tok]))
        # anything else ("my", "number", "is", "mera", "hai", "um") is filler
    return items


# ---------------------------------------------------------------------------
# Step 5: compose digits
# ---------------------------------------------------------------------------
def _read_below_100(items: list[_Item], i: int) -> tuple[str | None, int]:
    """Read a value < 100 starting at ``items[i]`` (used after "hundred")."""
    if i >= len(items):
        return None, i
    item = items[i]
    if item.kind == "tens":
        if i + 1 < len(items) and items[i + 1].kind == "unit" and items[i + 1].value != "0":
            return item.value + items[i + 1].value, i + 2
        return item.value + "0", i + 1
    if item.kind in ("unit", "number") and len(item.value) <= 2:
        return item.value, i + 1
    return None, i


def _compose(items: list[_Item]) -> str:
    out: list[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        nxt = items[i + 1] if i + 1 < len(items) else None

        if item.kind == "mult":
            # "double seven" -> 77, "triple 9" -> 999. If STT already merged
            # the following digits ("double 98"), repeat only the first one.
            if nxt is not None and nxt.kind in ("unit", "number"):
                out.append(nxt.value[0] * int(item.value) + nxt.value[1:])
                i += 2
            else:
                i += 1  # dangling "double" with nothing to repeat
            continue

        if item.kind == "tens":
            # "ninety eight" -> 98, bare "ninety" -> 90
            if nxt is not None and nxt.kind == "unit" and nxt.value != "0":
                out.append(item.value + nxt.value)
                i += 2
            else:
                out.append(item.value + "0")
                i += 1
            continue

        if item.kind == "unit" and nxt is not None and nxt.kind == "hundred":
            # "nine hundred eighty seven" -> 987, "nine hundred" -> 900
            rest, j = _read_below_100(items, i + 2)
            out.append(item.value + (rest.zfill(2) if rest is not None else "00"))
            i = j if rest is not None else i + 2
            continue

        if item.kind == "unit" and nxt is not None and nxt.kind == "thousand":
            out.append(item.value + "000")
            i += 2
            continue

        if item.kind in ("unit", "number"):
            out.append(item.value)
        # a bare "hundred"/"thousand" without a leading digit is ignored
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Step 6: language + validation
# ---------------------------------------------------------------------------
def _detect_language(items: list[_Item], fallback: Language) -> Language:
    langs = {item.lang for item in items if item.lang is not None}
    if langs == {EN, HI}:
        return "mixed"
    if langs == {HI}:
        return "hi"
    if langs == {EN}:
        return "en"
    return fallback  # only raw numerals: trust the STT's language guess


def _strip_country_code(digits: str) -> str:
    """Remove a +91 / 0 prefix, but only when what remains is a full number."""
    if len(digits) == PHONE_LENGTH + 2 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == PHONE_LENGTH + 1 and digits.startswith("0"):
        return digits[1:]
    return digits


def validate_indian_mobile(digits: str) -> ParseError | None:
    """Return ``None`` if ``digits`` is a valid Indian mobile number."""
    if not digits:
        return ParseError.NO_DIGITS
    if len(digits) < PHONE_LENGTH:
        return ParseError.TOO_FEW
    if len(digits) > PHONE_LENGTH:
        return ParseError.TOO_MANY
    if not digits.isdigit() or digits[0] not in VALID_FIRST_DIGITS:
        return ParseError.INVALID_PREFIX
    return None


def is_valid_indian_mobile(digits: str) -> bool:
    return validate_indian_mobile(digits) is None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_phone_number(transcript: str, *, fallback_language: Language = "en") -> ParseResult:
    """Convert spoken text into a phone number.

    >>> parse_phone_number("nine aath saat 6 5 chaar 3 2 1 zero").number
    '9876543210'
    >>> parse_phone_number("double seven triple nine 12345").digits
    '7799912345'
    """
    tokens, corrected = _apply_corrections(_tokenize(transcript))
    items = _classify(tokens)
    digits = _strip_country_code(_compose(items))
    return ParseResult(
        digits=digits,
        language=_detect_language(items, fallback_language),
        corrected=corrected,
        error=validate_indian_mobile(digits),
        tokens=tuple(tokens),
    )


# Alias matching the name used in the assignment brief.
parsePhoneNumber = parse_phone_number


def is_lead_in(transcript: str) -> bool:
    """True for "my number is…" / "mera phone number…" style openers."""
    return bool(set(_tokenize(transcript)) & LEAD_IN_WORDS)


def classify_confirmation(transcript: str) -> Literal["yes", "no", "unclear"]:
    """Classify a reply to "Is that correct?".

    Negatives win over positives so that "sahi nahi hai" (not correct) and
    "no that's not right" are read as *no*.
    """
    tokens = set(_tokenize(transcript))
    if tokens & NO_WORDS:
        return "no"
    if tokens & YES_WORDS:
        return "yes"
    return "unclear"
