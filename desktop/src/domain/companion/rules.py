"""How one event changes the companion's state, and the fold of a whole log.

Pure functions. The time arrives on the event and the temperament of each
character version is handed in, so the same log always gives the same state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime, tzinfo

from src.domain.companion.models import (
    Cause,
    CompanionState,
    Effect,
    FeelingExplanation,
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
    return StepResult(state, effects, next_wake=None, event=event)


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


def feeling_explanation(
    state: CompanionState,
    events: Iterable[Event],
    temperaments: Mapping[str, Temperament],
    at: datetime,
    zone: tzinfo,
) -> FeelingExplanation | None:
    """The feeling at ``at``, the last events among ``events`` that moved it with
    how far each pushed, the temperament and whether the sadness floor stopped
    the last event. ``None`` with moods off. Raises ``ValueError`` with no
    character."""
    if not state.moods_on:
        return None
    point = shown_at(state, at, temperaments)
    if point is None or state.emotion is None:
        raise ValueError("No character is in force.")
    temperament = _temperament(temperaments, state.version_id)
    pushes = [(e, emotion_rules.appraise(e)) for e in events]
    causes = tuple(
        _cause(e, push, zone) for e, push in pushes if push != _ZERO
    )[-CAUSE_LIMIT:]
    return FeelingExplanation(
        feeling=emotion_rules.name(point),
        point=point,
        rest=emotion_rules.name(temperament.rest),
        temperament=temperament,
        causes=causes,
        floor_reached=state.emotion.floor_reached,
    )


def explain_feeling(
    state: CompanionState,
    events: Iterable[Event],
    temperaments: Mapping[str, Temperament],
    at: datetime,
    zone: tzinfo,
) -> str:
    """:func:`feeling_explanation` as one sentence, for the model.

    Raises ``ValueError`` with no character."""
    found = feeling_explanation(state, events, temperaments, at, zone)
    if found is None:
        return MOODS_OFF
    if not found.causes:
        return (
            f"Nothing has moved the feeling in the last {CAUSE_DAYS} days. It is "
            f"the resting mood: {found.rest}."
        )
    point = found.point
    feeling = (
        f"Feeling now: {found.feeling} (pleasure {point.pleasure:.2f}, "
        f"arousal {point.arousal:.2f})."
    )
    moved = "; ".join(cause.text() for cause in found.causes)
    return f"{feeling} Events that moved it: {moved}. Resting mood: {found.rest}."


def _cause(event: Event, push: Pad, zone: tzinfo) -> Cause:
    when = event.occurred_at.astimezone(zone)
    day = f"{DAYS[when.weekday()][:3]} {when.day} {MONTHS[when.month - 1][:3]}"
    interpretation = ""
    if event.kind == EventKind.USER_MESSAGE:
        kind = str(event.payload.get("class", "message")).replace("_", " ")
        confidence = event.payload.get("confidence")
        if isinstance(confidence, int | float):
            interpretation = f"{kind} (confidence {confidence:.2f})"
            kind = interpretation
    else:
        kind = event.kind.value.replace("_", " ")
    return Cause(when=f"{day} {when:%H:%M}", what=kind, push=push,
                 interpretation=interpretation)


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
