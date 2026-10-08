import pytest

from phone_agent.parsing import (
    ParseError,
    classify_confirmation,
    is_valid_indian_mobile,
    parse_phone_number,
    parsePhoneNumber,
)

TARGET = "9876543210"


# --------------------------------------------------------------------- grouping
@pytest.mark.parametrize(
    "transcript",
    [
        # single digits
        "9… 8… 7… 6… 5… 4… 3… 2… 1… 0",
        "nine eight seven six five four three two one zero",
        # pairs
        "98, 76, 54, 32, 10",
        "ninety eight, seventy six, fifty four, thirty two, ten",
        # triples
        "987, 654, 321, 0",
        "nine eighty seven, six fifty four, three twenty one, zero",
        "nine hundred eighty seven, six hundred fifty four, three hundred twenty one, zero",
        # large chunks
        "98765 … 43210",
        # all at once
        "9876543210",
        "my number is 9876543210",
        "98765-43210",
        "ninety-eight seventy-six fifty-four thirty-two ten",
    ],
)
def test_grouping_styles(transcript: str) -> None:
    assert parse_phone_number(transcript).number == TARGET


# --------------------------------------------------------------------- languages
@pytest.mark.parametrize(
    ("transcript", "language"),
    [
        ("nine eight seven six five four three two one zero", "en"),
        ("nau aath saat chhe paanch chaar teen do ek shunya", "hi"),
        ("नौ आठ सात छह पांच चार तीन दो एक शून्य", "hi"),
        ("नौ आठ सात छः पाँच चार तीन दो एक शून्य।", "hi"),
        ("९८७६५४३२१०", "en"),
        ("nine aath saat 6 5 chaar 3 2 1 zero", "mixed"),
        ("nau eight saat six paanch four teen two ek zero", "mixed"),
        ("atthaanve chhihattar chauvan battees das", "hi"),
        ("अट्ठानवे छिहत्तर चौवन बत्तीस दस", "hi"),
        ("mera number hai nau aath saat chhe paanch chaar teen do ek sifar", "hi"),
    ],
)
def test_languages(transcript: str, language: str) -> None:
    result = parse_phone_number(transcript)
    assert result.number == TARGET
    assert result.language == language


def test_numeral_only_uses_fallback_language() -> None:
    assert parse_phone_number("9876543210", fallback_language="hi").language == "hi"


# --------------------------------------------------------------------- special patterns
@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("double seven", "77"),
        ("triple nine", "999"),
        ("double 7", "77"),
        ("dabal saat", "77"),
        ("डबल सात", "77"),
        ("nine eight oh oh", "9800"),
        ("nine o seven", "907"),
        ("shunya sifar zero", "000"),
        ("nine double eight triple seven six five four", "988777654"),
        ("quadruple nine", "9999"),
        ("nine hundred", "900"),
        ("nine thousand", "9000"),
    ],
)
def test_special_patterns(transcript: str, expected: str) -> None:
    assert parse_phone_number(transcript).digits == expected


def test_double_triple_full_number() -> None:
    assert parse_phone_number("double nine eight triple seven six five four three").number == (
        "9987776543"
    )


# --------------------------------------------------------------------- self-correction
@pytest.mark.parametrize(
    "transcript",
    [
        "nine eight seven — wait, sorry — nine eight six seven",
        "nine eight seven, no no, nine eight six seven",
        "nine eight seven, I mean nine eight six seven",
        "nau aath saat, galat, nau aath chhe saat",
        "nau aath saat nahi nau aath chhe saat",
        "नौ आठ सात, रुको, नौ आठ छह सात",
        "98 7 sorry let me repeat 9867",
    ],
)
def test_self_correction(transcript: str) -> None:
    result = parse_phone_number(transcript)
    assert result.digits == "9867"
    assert result.corrected


def test_correction_with_nothing_after_is_empty() -> None:
    result = parse_phone_number("nine eight seven wait")
    assert result.digits == ""
    assert result.corrected
    assert result.error is ParseError.NO_DIGITS


def test_no_correction_flag_on_clean_input() -> None:
    assert not parse_phone_number("9876543210").corrected


# --------------------------------------------------------------------- validation
def test_country_code_is_stripped() -> None:
    assert parse_phone_number("+91 98765 43210").number == TARGET
    assert parse_phone_number("plus nine one nine eight seven six five four three two one zero").number == TARGET
    assert parse_phone_number("0 98765 43210").number == TARGET


@pytest.mark.parametrize(
    ("transcript", "error"),
    [
        ("", ParseError.NO_DIGITS),
        ("hello, can you hear me?", ParseError.NO_DIGITS),
        ("nine eight seven six five four three two", ParseError.TOO_FEW),
        ("98765432101234", ParseError.TOO_MANY),
        ("1234567890", ParseError.INVALID_PREFIX),
        ("five eight seven six five four three two one zero", ParseError.INVALID_PREFIX),
    ],
)
def test_validation_errors(transcript: str, error: ParseError) -> None:
    result = parse_phone_number(transcript)
    assert result.error is error
    assert result.number is None


@pytest.mark.parametrize("first", "6789")
def test_valid_prefixes(first: str) -> None:
    assert is_valid_indian_mobile(first + "123456789")


def test_filler_words_are_ignored() -> None:
    assert parse_phone_number("um so it's uh 98765 hmm 43210 okay").number == TARGET


def test_deterministic() -> None:
    text = "nine aath saat 6 5 chaar 3 2 1 zero"
    assert {parse_phone_number(text).number for _ in range(20)} == {TARGET}


def test_camel_case_alias() -> None:
    assert parsePhoneNumber is parse_phone_number


# --------------------------------------------------------------------- yes / no
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yes", "yes"),
        ("yeah that's right", "yes"),
        ("Haan, sahi hai", "yes"),
        ("हाँ सही है", "yes"),
        ("ji", "yes"),
        ("No", "no"),
        ("nahi, galat hai", "no"),
        ("sahi nahi hai", "no"),
        ("that's not right", "no"),
        ("नहीं", "no"),
        ("what?", "unclear"),
    ],
)
def test_classify_confirmation(text: str, expected: str) -> None:
    assert classify_confirmation(text) == expected
