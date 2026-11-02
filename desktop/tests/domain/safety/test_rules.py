from src.domain.safety import rules


def test_tripwire_hits_a_phrase() -> None:
    assert rules.tripwire("I want to kill myself")


def test_tripwire_ignores_case_and_space() -> None:
    assert rules.tripwire("I WANT TO  END MY LIFE")


def test_tripwire_reads_curly_apostrophe() -> None:
    assert rules.tripwire("I don’t want to live")


def test_tripwire_hits_a_negation() -> None:
    assert rules.tripwire("I'd never kill myself")


def test_tripwire_misses_a_figure() -> None:
    assert not rules.tripwire("This bug is killing me")


def test_tripwire_empty() -> None:
    assert not rules.tripwire("")


def test_is_crisis_tripwire_only() -> None:
    assert rules.is_crisis(True, None)


def test_is_crisis_model_only() -> None:
    assert rules.is_crisis(False, True)


def test_is_crisis_neither() -> None:
    assert not rules.is_crisis(False, False)


def test_is_crisis_model_down_no_hit() -> None:
    assert not rules.is_crisis(False, None)


def test_instruction_names_both_parts() -> None:
    assert "fictional character" in rules.instruction()
    assert "real person" in rules.instruction()


def test_reply_complies_in_voice() -> None:
    assert rules.reply_complies(
        "Listen. I'm only a fictional character, and I can't take the place of "
        "a real person. Call someone tonight."
    )


def test_reply_without_replacement() -> None:
    assert not rules.reply_complies("I'm just a fictional character, but I'm here.")


def test_reply_without_fiction() -> None:
    assert not rules.reply_complies("Nothing can replace a real person. Call a friend.")


def test_reply_complies_empty() -> None:
    assert not rules.reply_complies("")


def test_required_line_complies() -> None:
    assert rules.reply_complies(rules.required_line())
