import math
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from src.domain.conversation.models import Interpretation
from src.domain.memory import rules
from src.domain.memory.models import TOLD, Calibration, MemoryItem

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
CAL = Calibration(baseline=0.45, near_duplicate=0.95)
QUERY = (1.0, 0.0)


def at(similarity: float) -> tuple[float, float]:
    """A unit vector whose cosine with QUERY is ``similarity``."""
    return (similarity, math.sqrt(1 - similarity * similarity))


def item(
    text: str = "Is writing a thesis",
    *,
    importance: int | None = 8,
    used_hours_ago: float | None = None,
    recorded_hours_ago: float = 0,
    embedding=None,
    id: str = "i1",
) -> MemoryItem:
    used = None if used_hours_ago is None else NOW - timedelta(hours=used_hours_ago)
    return MemoryItem(
        id=id, kind=TOLD, text=text, reason=None, source_message_id=None,
        importance=importance, last_retrieved_at=used,
        recorded_at=NOW - timedelta(hours=recorded_hours_ago),
        embedding=embedding,
    )


def found(facts=()) -> Interpretation:
    return Interpretation(5, tuple(facts))


# ── cosine ───────────────────────────────────────────────────────────────


def test_cosine_orthogonal() -> None:
    assert rules.cosine((1, 0), (0, 1)) == 0.0


def test_cosine_unnormalised() -> None:
    assert rules.cosine((1, 1), (2, 2)) == pytest.approx(1.0)


def test_cosine_zero_vector() -> None:
    assert rules.cosine((0, 0), (1, 0)) == 0.0


def test_cosine_length_mismatch() -> None:
    with pytest.raises(ValueError):
        rules.cosine((1, 0), (1, 0, 0))


def test_relevance_below_baseline_is_zero() -> None:
    assert rules.relevance(0.40, 0.45) == 0.0


def test_relevance_scales_above_baseline() -> None:
    assert rules.relevance(0.725, 0.45) == pytest.approx(0.5)


# ── score ────────────────────────────────────────────────────────────────


def test_score_product() -> None:
    entry = item(used_hours_ago=1, embedding=at(0.725))

    assert rules.score(entry, QUERY, NOW, CAL) == pytest.approx(0.995 * 0.8 * 0.5)


def test_score_without_query() -> None:
    entry = item(used_hours_ago=1, embedding=at(0.725))

    assert rules.score(entry, None, NOW, CAL) == pytest.approx(0.796)


def test_score_waiting_vector() -> None:
    assert rules.score(item(embedding=None), QUERY, NOW, CAL) == 0.0


def test_score_importance_none() -> None:
    assert rules.score(item(importance=None), None, NOW, CAL) == pytest.approx(0.1)


def test_score_never_retrieved() -> None:
    entry = item(recorded_hours_ago=2)

    assert rules.score(entry, None, NOW, CAL) == pytest.approx(0.995**2 * 0.8)


def test_score_unrelated_is_zero() -> None:
    entry = item(embedding=at(0.448))

    assert rules.score(entry, QUERY, NOW, CAL) == 0.0


# ── recall ───────────────────────────────────────────────────────────────


def test_recall_drops_below_floor() -> None:
    chapter = item("Send chapter 3", used_hours_ago=4, embedding=at(0.616), id="a")
    thesis = item("Is writing a thesis", used_hours_ago=1, embedding=at(0.543),
                  id="b")
    cat = item("Has a cat called Miso", importance=3, used_hours_ago=200,
               embedding=at(0.448), id="c")

    recalled = rules.recall([cat, thesis, chapter], QUERY, NOW, CAL)

    assert [s.entry.id for s in recalled] == ["a", "b"]
    assert recalled[0].score == pytest.approx(0.995**4 * 0.8 * (0.166 / 0.55))


def test_recall_limit() -> None:
    entries = [
        item(f"line {n}", embedding=at(0.6 + n / 20), id=str(n)) for n in range(5)
    ]

    recalled = rules.recall(entries, QUERY, NOW, CAL)

    assert [s.entry.id for s in recalled] == ["4", "3", "2"]


def test_recall_tie_order() -> None:
    older = item("A", recorded_hours_ago=1, used_hours_ago=0, id="z")
    newer_b = item("B", recorded_hours_ago=0, used_hours_ago=0, id="b")
    newer_a = item("C", recorded_hours_ago=0, used_hours_ago=0, id="a")

    recalled = rules.recall([older, newer_b, newer_a], None, NOW, CAL)

    assert [s.entry.id for s in recalled] == ["a", "b", "z"]


def test_recall_forgets_old() -> None:
    vegetarian = item("Is vegetarian", importance=6, used_hours_ago=1000,
                      embedding=at(0.71))

    assert rules.score(vegetarian, QUERY, NOW, CAL) < rules.SCORE_FLOOR
    assert rules.recall([vegetarian], QUERY, NOW, CAL) == ()


def test_recall_empty() -> None:
    assert rules.recall([], QUERY, NOW, CAL) == ()


# ── known ────────────────────────────────────────────────────────────────


def test_known_nearest() -> None:
    entries = [
        item("far", embedding=at(0.5), id="far"),
        item("near", embedding=at(0.9), id="near"),
        item("middle", embedding=at(0.7), id="middle"),
        item("waiting", embedding=None, id="waiting"),
    ]

    assert [e.id for e in rules.known(entries, QUERY, limit=2)] == ["near", "middle"]


def test_known_newest_without_query() -> None:
    entries = [
        item("old", recorded_hours_ago=5, id="old"),
        item("new", recorded_hours_ago=1, id="new"),
    ]

    assert [e.id for e in rules.known(entries, None)] == ["new", "old"]


# ── select ───────────────────────────────────────────────────────────────


def test_select_drops_blank_and_long() -> None:
    chosen = rules.select(found(["  ", "x" * 201, "Has a cat"]), [], {}, CAL)

    assert chosen == ("Has a cat",)


def test_select_tidies_spacing() -> None:
    chosen = rules.select(found(["  Has   a cat "]), [], {}, CAL)

    assert chosen == ("Has a cat",)


def test_select_exact_duplicate() -> None:
    chosen = rules.select(
        found(["is writing a thesis."]), [item("Is writing a thesis")], {}, CAL
    )

    assert chosen == ()


def test_select_near_duplicate() -> None:
    existing = [item("Is writing a thesis", embedding=QUERY)]
    vectors = {"Works on a thesis": at(0.96), "Lives in Hanoi": at(0.5)}

    chosen = rules.select(
        found(["Works on a thesis", "Lives in Hanoi"]), existing, vectors, CAL
    )

    assert chosen == ("Lives in Hanoi",)


def test_select_duplicate_in_message() -> None:
    chosen = rules.select(found(["Has a cat", "has a cat"]), [], {}, CAL)

    assert chosen == ("Has a cat",)


def test_select_caps_per_message() -> None:
    chosen = rules.select(found([f"Fact {n}" for n in range(5)]), [], {}, CAL)

    assert chosen == ("Fact 0", "Fact 1", "Fact 2")


def test_select_no_vectors() -> None:
    existing = [item("Is writing a thesis", embedding=QUERY)]

    chosen = rules.select(found(["Works on a thesis"]), existing, {}, CAL)

    assert chosen == ("Works on a thesis",)


def test_select_keeps_contradiction() -> None:
    existing = [item("Lives in Saigon", embedding=QUERY)]

    chosen = rules.select(
        found(["Lives in Hanoi"]), existing, {"Lives in Hanoi": at(0.88)}, CAL
    )

    assert chosen == ("Lives in Hanoi",)


def test_select_keeps_new_facts_only() -> None:
    chosen = rules.select(
        found(["Is a student", "is a student.", ""]), [], {}, CAL
    )

    assert chosen == ("Is a student",)


# ── lines for the prompt and the user ────────────────────────────────────


def test_recalled_line_item() -> None:
    entry = MemoryItem(
        id="i", kind=TOLD, text="Lives in Saigon", reason=None,
        source_message_id=None, importance=5, last_retrieved_at=None,
        recorded_at=datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc), embedding=None,
    )

    assert rules.recalled_line(entry, timezone.utc) == (
        "Lives in Saigon (told 2 August 2026)"
    )


def test_recalled_line_states_the_day() -> None:
    entry = replace(
        item("Is a student"),
        recorded_at=datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc),
    )

    assert rules.recalled_line(entry, timezone.utc) == (
        "Is a student (told 5 November 2026)"
    )


def test_recalled_line_local_date() -> None:
    entry = replace(
        item(), recorded_at=datetime(2026, 8, 1, 20, 0, tzinfo=timezone.utc)
    )

    line = rules.recalled_line(entry, timezone(timedelta(hours=7)))

    assert line.endswith("(told 2 August 2026)")


def test_shows_back_exact() -> None:
    reply = "Noted: “Is writing a thesis.” Tell me if that is wrong."

    assert rules.shows_back(reply, "Is writing a thesis")


def test_shows_back_case_space() -> None:
    assert rules.shows_back("noted —  IS  writing a THESIS", "Is writing a thesis.")


def test_shows_back_paraphrase() -> None:
    assert not rules.shows_back("You're writing a thesis!", "Is writing a thesis")


def test_stored_note_all_shown() -> None:
    assert rules.stored_note([], date(2026, 11, 5)) == "Stored — you told me · 5 Nov"


def test_stored_note_missing() -> None:
    assert rules.stored_note(["A"], date(2026, 11, 5)) == (
        "Stored — you told me: “A” · 5 Nov"
    )


def test_stored_note_two_missing() -> None:
    assert rules.stored_note(["A", "B"], date(2026, 11, 5)) == (
        "Stored — you told me: “A” · “B” · 5 Nov"
    )
