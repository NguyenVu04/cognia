"""How one event changes the companion's state, and the fold of a whole log.

Pure functions. The time arrives on the event and the temperament of each
character version is handed in, so the same log always gives the same state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace

from src.domain.companion.models import CompanionState, ShowExpression, StepResult
from src.domain.emotion import rules as emotion_rules
from src.domain.emotion.models import Expression, Temperament
from src.domain.events.models import Event, EventKind

MOODS_ON = "moods_on"


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
    effects = (ShowExpression(after),) if after and after != before else ()
    return StepResult(state, effects, next_wake=None)


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


def _face(state: CompanionState) -> Expression | None:
    if state.emotion is None:
        return None
    return emotion_rules.expression(state.emotion.shown(), state.moods_on)
