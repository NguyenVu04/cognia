"""The shape of the mouth while the companion speaks, from the phonemes.

Kokoro reports the time of each phoneme of the audio it makes. Each vowel
selects one of the five VRM mouth shapes; the lips close on m, b and p; a
consonant keeps the shape before it at half its weight; stress marks, spaces
and punctuation change nothing. The loudness of the audio in the span of a
phoneme scales its weight, so a quiet word opens the mouth less.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

SHAPES = ("aa", "ih", "ou", "ee", "oh")
CLOSED = {name: 0.0 for name in SHAPES}

_VOWELS: dict[str, tuple[str, float]] = {
    **{p: ("aa", 0.8) for p in "ɑaæʌɐ"},
    **{p: ("aa", 0.4) for p in "əɚɜ"},
    **{p: ("ih", 0.7) for p in "iɪ"},
    **{p: ("ee", 0.7) for p in "eɛ"},
    **{p: ("ou", 0.7) for p in "uʊw"},
    **{p: ("oh", 0.8) for p in "oɔ"},
    **{p: ("ih", 0.2) for p in "fv"},
}
_LIPS_CLOSED = set("mbp")
_NO_CHANGE = set("ˈˌː ") | set(",.!?;:—-…\"'“”")
# Loudness at or above this opens the mouth fully.
_FULL_LOUDNESS = 0.12


@dataclass(frozen=True)
class Span:
    """One phoneme: from ``start`` to ``end`` seconds, a shape and its weight."""

    start: float
    end: float
    shape: str
    weight: float


def spans(timings: Sequence[tuple[str, float, float]]) -> list[Span]:
    """The shape of each phoneme, as (phoneme, start, end) triples."""
    result: list[Span] = []
    shape, weight = "", 0.0
    for phoneme, start, end in timings:
        if phoneme in _NO_CHANGE:
            if result:
                result.append(Span(start, end, shape, weight))
            continue
        if phoneme in _VOWELS:
            shape, weight = _VOWELS[phoneme]
            result.append(Span(start, end, shape, weight))
        elif phoneme in _LIPS_CLOSED:
            shape, weight = "", 0.0
            result.append(Span(start, end, "", 0.0))
        else:
            result.append(Span(start, end, shape, weight / 2))
    return result


def scaled(found: Sequence[Span], samples: Sequence[float], rate: int) -> list[Span]:
    """Each span with its weight scaled by the loudness of its audio."""
    result = []
    for span in found:
        first, last = (
            int(span.start * rate),
            max(int(span.end * rate), int(span.start * rate) + 1),
        )
        chunk = samples[first:last]
        loudness = (
            (sum(s * s for s in chunk) / len(chunk)) ** 0.5 if len(chunk) else 0.0
        )
        factor = min(1.0, loudness / _FULL_LOUDNESS)
        result.append(Span(span.start, span.end, span.shape, span.weight * factor))
    return result


def weights_at(track: Sequence[Span], seconds: float) -> dict[str, float]:
    """The target weight of each shape at ``seconds`` into the audio."""
    weights = dict(CLOSED)
    for span in track:
        if span.start <= seconds < span.end:
            if span.shape:
                weights[span.shape] = span.weight
            break
    return weights
