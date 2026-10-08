from phone_agent.dialog import PhoneCollector, State, TurnQuality
from phone_agent.dialog.prompts import spell_digits


def test_happy_path_with_pause() -> None:
    c = PhoneCollector()
    assert "10-digit" in c.greeting().text

    reply = c.on_user_turn("Nine eight seven six...")
    assert reply.text is None and reply.wait_for_more  # waits silently

    reply = c.on_user_turn("...five four three two one zero")
    assert c.state is State.CONFIRMING
    assert "nine, eight, seven, six, five... four, three, two, one, zero" in reply.text
    assert reply.text.endswith("Is that correct?")

    reply = c.on_user_turn("Haan, sahi hai")
    assert c.state is State.DONE
    assert reply.text == "Thank you! Your number has been saved."
    assert reply.save is not None
    assert reply.save.parsed_number == "9876543210"
    assert reply.save.raw_transcript == "Nine eight seven six... ...five four three two one zero"
    assert reply.save.language == "en"
    assert reply.end_call


def test_many_small_groups() -> None:
    c = PhoneCollector()
    for part in ["98", "76", "54", "32"]:
        assert c.on_user_turn(part).wait_for_more
    c.on_user_turn("10")
    assert c.state is State.CONFIRMING


def test_silence_timeout_reports_digit_count_and_resets() -> None:
    c = PhoneCollector()
    c.on_user_turn("nine eight seven six five four three two")
    reply = c.on_silence_timeout()
    assert reply.text == "I only got 8 digits. Could you repeat your full number?"
    assert c.digits_so_far == ""


def test_silence_timeout_without_digits_is_silent() -> None:
    assert PhoneCollector().on_silence_timeout().text is None


def test_self_correction_across_turns() -> None:
    c = PhoneCollector()
    c.on_user_turn("nine eight seven")
    c.on_user_turn("wait, sorry")
    assert c.digits_so_far == ""
    c.on_user_turn("nine eight six seven five four three two one zero")
    assert c.state is State.CONFIRMING
    assert c.candidate.digits == "9867543210"


def test_invalid_prefix() -> None:
    c = PhoneCollector()
    reply = c.on_user_turn("one two three four five six seven eight nine zero")
    assert reply.text == "That doesn't look like a valid mobile number. Please try again."
    assert c.state is State.COLLECTING and c.digits_so_far == ""


def test_too_many_digits() -> None:
    c = PhoneCollector()
    reply = c.on_user_turn("98765432101")
    assert "11 digits" in reply.text
    assert c.digits_so_far == ""


def test_user_rejects_confirmation() -> None:
    c = PhoneCollector()
    c.on_user_turn("9876543210")
    reply = c.on_user_turn("no")
    assert c.state is State.COLLECTING
    assert "again" in reply.text


def test_user_corrects_during_confirmation() -> None:
    c = PhoneCollector()
    c.on_user_turn("9876543210")
    reply = c.on_user_turn("no, it's 9876543211")
    assert c.state is State.CONFIRMING
    assert c.candidate.digits == "9876543211"
    assert "one" in reply.text


def test_oh_no_is_a_rejection_not_a_number() -> None:
    c = PhoneCollector()
    c.on_user_turn("9876543210")
    c.on_user_turn("oh no")
    assert c.state is State.COLLECTING


def test_unclear_confirmation_repeats_number() -> None:
    c = PhoneCollector()
    c.on_user_turn("9876543210")
    reply = c.on_user_turn("hmm")
    assert reply.text.startswith("Please say yes or no.")
    assert c.state is State.CONFIRMING


def test_hindi_speaker_gets_hindi_prompts() -> None:
    c = PhoneCollector()
    c.on_user_turn("nau aath saat chhe paanch")
    reply = c.on_user_turn("chaar teen do ek shunya")
    assert "आपका नंबर है" in reply.text
    assert "नौ, आठ, सात, छह, पाँच... चार, तीन, दो, एक, शून्य" in reply.text
    reply = c.on_user_turn("haan")
    assert reply.save.language == "hi"
    assert reply.text == "धन्यवाद! आपका नंबर सेव हो गया है।"


def test_mixed_language_saved_as_mixed() -> None:
    c = PhoneCollector()
    c.on_user_turn("nine aath saat 6 5 chaar 3 2 1 zero")
    assert c.on_user_turn("yes").save.language == "mixed"


def test_low_snr_segment_is_rejected_and_only_that_part_reasked() -> None:
    c = PhoneCollector(min_snr_db=10)
    c.on_user_turn("98765", TurnQuality(snr_db=25))
    reply = c.on_user_turn("43 2 1 0", TurnQuality(snr_db=3))
    assert "last part" in reply.text
    assert c.digits_so_far == "98765"  # earlier digits kept
    c.on_user_turn("43210", TurnQuality(snr_db=20))
    assert c.candidate.digits == "9876543210"


def test_low_confidence_first_segment_asks_for_number() -> None:
    c = PhoneCollector(min_stt_confidence=0.6)
    reply = c.on_user_turn("nine eight", TurnQuality(stt_confidence=0.2))
    assert "noisy" in reply.text
    assert c.digits_so_far == ""


def test_non_number_speech_reprompts() -> None:
    reply = PhoneCollector().on_user_turn("hello who is this")
    assert reply.text == "Please tell me your 10-digit mobile number."


def test_static_prompts_are_cacheable() -> None:
    c = PhoneCollector()
    assert c.greeting().cacheable
    assert not c.on_user_turn("9876543210").cacheable  # confirmation has digits


def test_spell_digits() -> None:
    assert spell_digits("9876543210", "en") == (
        "nine, eight, seven, six, five... four, three, two, one, zero"
    )


def test_english_only_tts_keeps_english_prompts_for_hindi_speakers() -> None:
    c = PhoneCollector(hindi_prompts=False)
    reply = c.on_user_turn("nau aath saat chhe paanch chaar teen do ek shunya")
    assert reply.text.startswith("Let me confirm")
    assert "nine, eight" in reply.text
    assert c.on_user_turn("haan").save.language == "hi"  # still recorded as Hindi


def test_lead_in_phrase_waits_for_digits() -> None:
    c = PhoneCollector()
    for lead_in in ("मेरा phone number", "my number is", "mera number hai"):
        c = PhoneCollector()
        reply = c.on_user_turn(lead_in)
        assert reply.text is None and reply.wait_for_more
    reply = c.on_user_turn("nine eight seven six five four three two one zero")
    assert c.state is State.CONFIRMING
    assert c.candidate.digits == "9876543210"


def test_lead_in_then_silence_asks_for_number_once() -> None:
    c = PhoneCollector()
    c.on_user_turn("my number is")
    assert c.on_silence_timeout().text == "Please tell me your 10-digit mobile number."
    assert c.on_silence_timeout().text is None  # doesn't nag repeatedly


def test_greeting_without_lead_in_still_reprompts() -> None:
    assert PhoneCollector().on_user_turn("Hi.").text == "Please tell me your 10-digit mobile number."
