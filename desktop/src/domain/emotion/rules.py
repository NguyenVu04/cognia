"""How events move the companion's feelings, and how the feelings fade.

Pure functions. The time arrives on the event and the temperament is handed
in, so the same events always give the same feelings.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from src.domain.emotion.models import EmotionState, Expression, Pad, Temperament
from src.domain.events.models import Event, EventKind, MessageClass

# Start values. Trial use with real people sets the final ones.
FLOOR_PLEASURE = -0.30
RESTORED_SHARE = 0.70
CALM_RADIUS = 0.25

_ZERO = Pad(0.0, 0.0, 0.0)
_IGNORED = Pad(-0.30, 0.0, 0.0)
_COMMITMENT_FINISHED = Pad(0.30, 0.10, 0.05)

_MESSAGE_APPRAISAL = {
    MessageClass.PRAISE: Pad(0.50, 0.20, 0.10),
    MessageClass.GOOD_NEWS: Pad(0.40, 0.20, 0.05),
    MessageClass.BAD_NEWS: Pad(-0.30, 0.10, -0.10),
    MessageClass.COMPLAINT: Pad(-0.30, 0.20, -0.15),
    MessageClass.SHARED_WORRY: Pad(-0.15, 0.10, 0.00),
}

# Being paused is never something the companion feels, so paused and resumed
# have no row.
_KIND_APPRAISAL = {
    EventKind.MESSAGE_ANSWERED: Pad(0.20, 0.10, 0.00),
    EventKind.SESSION_OPENED: Pad(0.05, 0.10, 0.00),
    EventKind.SESSION_CLOSED: Pad(0.20, 0.00, 0.05),
}

_TALK = (EventKind.USER_MESSAGE, EventKind.MESSAGE_ANSWERED)

# Name: (VRM preset, weight at the edge of calm, weight at full strength). No
# angry face, because an angry face is a reproach.
_FACES = {
    "calm": ("neutral", 1.0, 1.0),
    "pleased": ("relaxed", 0.5, 1.0),
    "lively": ("happy", 0.5, 1.0),
    "restless": ("surprised", 0.2, 0.4),
    "low": ("sad", 0.3, 0.7),
}


def at_rest(temperament: Temperament, at: datetime, seq: int) -> EmotionState:
    """The resting mood and no feeling: at the start, with moods off, and after
    everything is erased."""
    return EmotionState(
        mood=temperament.rest, feeling=_ZERO, computed_to_seq=seq, computed_at=at
    )


def decay(
    state: EmotionState, temperament: Temperament, minutes: float
) -> EmotionState:
    """``state`` after ``minutes`` with no event.

    The feeling fades towards nothing and the mood towards the resting mood.
    Each loses half of its distance in one half-life. Raises ``ValueError`` if
    ``minutes`` is negative.
    """
    if minutes < 0:
        raise ValueError(f"minutes must be 0 or more, not {minutes}")
    feeling_left = 0.5 ** (minutes / temperament.feeling_half_life_min)
    mood_left = 0.5 ** (minutes / temperament.mood_half_life_min)
    rest = temperament.rest
    return replace(
        state,
        feeling=_scale(state.feeling, feeling_left),
        mood=_add(rest, _scale(_subtract(state.mood, rest), mood_left)),
        # The loss is part of the mood's distance from rest, so it fades with it.
        ignored_loss=state.ignored_loss * mood_left,
    )


def appraise(event: Event) -> Pad:
    """How far ``event`` pushes the feeling. A kind with no row gives no push."""
    if event.kind == EventKind.USER_MESSAGE:
        return _MESSAGE_APPRAISAL.get(event.payload.get("class"), _ZERO)
    if _is_ignored(event):
        return _IGNORED
    if event.kind == EventKind.COMMITMENT_CLOSED and event.payload.get("finished"):
        return _COMMITMENT_FINISHED
    return _KIND_APPRAISAL.get(event.kind, _ZERO)


def apply(
    state: EmotionState, appraisal: Pad, temperament: Temperament
) -> EmotionState:
    """``state`` after one push: the feeling takes all of it and the mood
    ``reactivity`` of it. Each axis stays within -1 to 1."""
    return replace(
        state,
        feeling=_limit(_add(state.feeling, appraisal)),
        mood=_limit(_add(state.mood, _scale(appraisal, temperament.reactivity))),
        floor_reached=False,
    )


def sadden(
    state: EmotionState, appraisal: Pad, temperament: Temperament
) -> EmotionState:
    """``state`` after being ignored while the user was at the desk to see it.

    Only the mood moves, so no passing feeling takes the shown point below the
    floor. Pleasure stops at :data:`FLOOR_PLEASURE`, and a mood already below
    it does not fall further. The pleasure lost is kept, so that talking again
    can give most of it back.
    """
    mood = _limit(_add(state.mood, _scale(appraisal, temperament.reactivity)))
    before = state.mood.pleasure
    floor = min(before, FLOOR_PLEASURE)
    pleasure = max(mood.pleasure, floor)
    return replace(
        state,
        mood=replace(mood, pleasure=pleasure),
        ignored_loss=state.ignored_loss + before - pleasure,
        floor_reached=mood.pleasure < floor,
    )


def restore_after_talk(state: EmotionState) -> EmotionState:
    """``state`` when the user talks again: most of the pleasure lost to being
    ignored comes back at once."""
    pleasure = _limit_axis(state.mood.pleasure + RESTORED_SHARE * state.ignored_loss)
    return replace(state, mood=replace(state.mood, pleasure=pleasure), ignored_loss=0.0)


def feel(state: EmotionState, event: Event, temperament: Temperament) -> EmotionState:
    """``state`` after the time since the last event, and then after ``event``."""
    # A clock set back does not make old feelings stronger.
    minutes = max(0.0, (event.occurred_at - state.computed_at).total_seconds() / 60)
    state = decay(state, temperament, minutes)
    if event.kind in _TALK:
        state = restore_after_talk(state)
    appraisal = appraise(event)
    if _is_ignored(event):
        state = sadden(state, appraisal, temperament)
    else:
        state = apply(state, appraisal, temperament)
    return replace(state, computed_to_seq=event.seq, computed_at=event.occurred_at)


def name(point: Pad) -> str:
    """The name the user sees for ``point``. Dominance does not change it."""
    if _intensity(point) < CALM_RADIUS:
        return "calm"
    if point.pleasure >= 0:
        return "lively" if point.arousal > 0 else "pleased"
    return "restless" if point.arousal > 0 else "low"


def expression(point: Pad, moods_on: bool = True) -> Expression:
    """The face for ``point``, stronger the further the point is from calm.
    With moods off the face is neutral."""
    if not moods_on:
        return Expression("neutral", 1.0)
    preset, weakest, strongest = _FACES[name(point)]
    share = (_intensity(point) - CALM_RADIUS) / (1 - CALM_RADIUS)
    share = max(0.0, min(1.0, share))
    return Expression(preset, weakest + (strongest - weakest) * share)


def _is_ignored(event: Event) -> bool:
    # A message nobody was at the desk to see was not ignored.
    return event.kind == EventKind.MESSAGE_PASSED_OVER and bool(
        event.payload.get("at_desk")
    )


def _intensity(point: Pad) -> float:
    return max(abs(point.pleasure), abs(point.arousal))


def _add(a: Pad, b: Pad) -> Pad:
    return Pad(
        a.pleasure + b.pleasure, a.arousal + b.arousal, a.dominance + b.dominance
    )


def _subtract(a: Pad, b: Pad) -> Pad:
    return Pad(
        a.pleasure - b.pleasure, a.arousal - b.arousal, a.dominance - b.dominance
    )


def _scale(point: Pad, factor: float) -> Pad:
    return Pad(
        point.pleasure * factor, point.arousal * factor, point.dominance * factor
    )


def _limit(point: Pad) -> Pad:
    return Pad(
        _limit_axis(point.pleasure),
        _limit_axis(point.arousal),
        _limit_axis(point.dominance),
    )


def _limit_axis(axis: float) -> float:
    return max(-1.0, min(1.0, axis))
