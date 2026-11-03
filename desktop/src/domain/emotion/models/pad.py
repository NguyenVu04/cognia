"""A point in pleasure, arousal and dominance: where a feeling sits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pad:
    pleasure: float
    arousal: float
    dominance: float
