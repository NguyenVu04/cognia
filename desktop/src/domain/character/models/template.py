"""One ready-made character, as it ships.

``card_line`` and ``sample_answer`` exist for the picker only; a version keeps
neither. ``voice`` names the Kokoro voice the character speaks with.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.emotion.models import Temperament


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    role: str
    description: str
    appearance_id: str
    temperament: Temperament
    card_line: str
    sample_answer: str
    voice: str = "af_heart"
