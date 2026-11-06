"""How one event changes the companion's state, and the fold of a whole log.

Pure functions. The time arrives on the event and the temperament of each
character version is handed in, so the same log always gives the same state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime, tzinfo

from src.domain.companion.models import (
    CompanionState,
    Effect,
    ShowExpression,
    ShowGesture,
    StepResult,
)
from src.domain.conversation.rules import DAYS, MONTHS
from src.domain.emotion import rules as emotion_rules
from src.domain.emotion.models import Expression, Pad, Temperament
from src.domain.events.models import Event, EventKind

MOODS_ON = "moods_on"
# How far back, and how many of the events that moved the feeling, an answer to
# "why do you feel this way" names.
CAUSE_DAYS = 7
CAUSE_LIMIT = 5
MOODS_OFF = "Moods are switched off, so there is no feeling to explain."
_ZERO = Pad(0.0, 0.0, 0.0)


def initial_state() -> CompanionState:
    """The state before the first event: no character yet, and moods on, as
    in a new installation."""
    return CompanionState(version_id=None, moods_on=True, emotion=None)


def step(
    state: CompanionState, event: Event, temperaments: Mapping[str, Temperament]
) -> StepResult:
    """``state`` after ``event``, what to do outside, and the next wake.

    ``temperaments`` holds the temperament of each character version by its ID.
    Raises ``ValueError`` if ``event`` names a version that is not in it.
    """
    before = _face(state)
    if event.kind == EventKind.CHARACTER_CHANGED:
        # The time up to the change passed under the old character.
        state = _feel(state, event, temperaments)
        state = _change_character(state, event, temperaments)
    else:
        if _is_moods_setting(event):
            state = replace(state, moods_on=bool(event.payload.get("value")))
        state = _feel(state, event, temperaments)
    after = _face(state)
    effects: tuple[Effect, ...] = ()
    if after and after != before:
        effects += (ShowExpression(after),)
    chosen = _gesture(state, event)
    if chosen is not None:
        effects += (ShowGesture(chosen),)
    return StepResult(state, effects, next_wake=None)


def shown_at(
    state: CompanionState, at: datetime, temperaments: Mapping[str, Temperament]
) -> Pad | None:
    """The point the user sees at ``at``, after the decay since the last event.
    The resting point with moods off, and ``None`` with no character. A clock
    set back decays nothing."""
    if state.version_id is None or state.emotion is None:
        return None
    temperament = _temperament(temperaments, state.version_id)
    if not state.moods_on:
        return temperament.rest
    minutes = max(0.0, (at - state.emotion.computed_at).total_seconds() / 60)
    return emotion_rules.decay(state.emotion, temperament, minutes).shown()


def fold(
    state: CompanionState,
    events: Iterable[Event],
    temperaments: Mapping[str, Temperament],
) -> CompanionState:
    """``state`` after each of ``events`` in order. The effects are dropped,
    because they ran when the events happened."""
    for event in events:
        state = step(state, event, temperaments).state
    return state


def _feel(
    state: CompanionState, event: Event, temperaments: Mapping[str, Temperament]
) -> CompanionState:
    if state.version_id is None or state.emotion is None:
        return state
    temperament = _temperament(temperaments, state.version_id)
    if state.moods_on:
        emotion = emotion_rules.feel(state.emotion, event, temperament)
    else:
        emotion = emotion_rules.at_rest(temperament, event.occurred_at, event.seq)
    return replace(state, emotion=emotion)


def _change_character(
    state: CompanionState, event: Event, temperaments: Mapping[str, Temperament]
) -> CompanionState:
    version_id = event.payload.get("version_id")
    temperament = _temperament(temperaments, version_id)
    emotion = state.emotion
    # A change does not reset the mood: it moves towards the new resting mood.
    if emotion is None or not state.moods_on:
        emotion = emotion_rules.at_rest(temperament, event.occurred_at, event.seq)
    return replace(state, version_id=version_id, emotion=emotion)


def _temperament(
    temperaments: Mapping[str, Temperament], version_id: object
) -> Temperament:
    temperament = temperaments.get(version_id)
    if temperament is None:
        raise ValueError(f"No character version has the id {version_id!r}.")
    return temperament


def _is_moods_setting(event: Event) -> bool:
    return (
        event.kind == EventKind.SETTING_CHANGED
        and event.payload.get("name") == MOODS_ON
    )


def explain_feeling(
    state: CompanionState,
    events: Iterable[Event],
    temperaments: Mapping[str, Temperament],
    at: datetime,
    zone: tzinfo,
) -> str:
    """The feeling at ``at``, the last events among ``events`` that moved it with
    how far each pushed, and the resting mood, from the recorded figures only.
    Raises ``ValueError`` with no character."""
    if not state.moods_on:
        return MOODS_OFF
    point = shown_at(state, at, temperaments)
    if point is None:
        raise ValueError("No character is in force.")
    rest = emotion_rules.name(_temperament(temperaments, state.version_id).rest)
    causes = [(e, emotion_rules.appraise(e)) for e in events]
    causes = [(e, push) for e, push in causes if push != _ZERO][-CAUSE_LIMIT:]
    if not causes:
        return (
            f"Nothing has moved the feeling in the last {CAUSE_DAYS} days. It is "
            f"the resting mood: {rest}."
        )
    feeling = (
        f"Feeling now: {emotion_rules.name(point)} (pleasure {point.pleasure:.2f}, "
        f"arousal {point.arousal:.2f})."
    )
    moved = "; ".join(_cause(e, push, zone) for e, push in causes)
    return f"{feeling} Events that moved it: {moved}. Resting mood: {rest}."


def _cause(event: Event, push: Pad, zone: tzinfo) -> str:
    when = event.occurred_at.astimezone(zone)
    day = f"{DAYS[when.weekday()][:3]} {when.day} {MONTHS[when.month - 1][:3]}"
    if event.kind == EventKind.USER_MESSAGE:
        kind = str(event.payload.get("class", "message")).replace("_", " ")
        confidence = event.payload.get("confidence")
        if isinstance(confidence, int | float):
            kind = f"{kind} (confidence {confidence:.2f})"
    else:
        kind = event.kind.value.replace("_", " ")
    return (
        f"{day} {when:%H:%M}, {kind}: pleasure {push.pleasure:+.2f}, "
        f"arousal {push.arousal:+.2f}"
    )


def _gesture(state: CompanionState, event: Event) -> str | None:
    if event.kind != EventKind.USER_MESSAGE or not state.moods_on:
        return None
    if state.emotion is None:
        return None
    feeling = emotion_rules.name(state.emotion.shown())
    return emotion_rules.gesture(event.payload.get("class"), feeling)


def _face(state: CompanionState) -> Expression | None:
    if state.emotion is None:
        return None
    return emotion_rules.expression(state.emotion.shown(), state.moods_on)
