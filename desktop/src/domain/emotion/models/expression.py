"""A facial expression for the companion: a VRM preset and how strongly to show it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Expression:
    """Raises ``ValueError`` if ``weight`` is outside 0 to 1."""

    preset: str
    weight: float

    def __post_init__(self) -> None:
        if not 0 <= self.weight <= 1:
            raise ValueError(f"weight must be 0 to 1, not {self.weight}")
