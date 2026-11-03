"""One complete version of the character: who it is, how it speaks, how it looks
and how it feels things.

A version is never changed. A change of character or a restore makes a new one,
so every earlier version stays available to go back to. It is a full copy, not a
reference to its template, because a template can change between releases and
an old version must not. The version with the highest ``number`` is in force.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.emotion.models import Temperament

CHOSEN = "chosen"
RESTORED = "restored"


@dataclass(frozen=True)
class Version:
    id: str
    number: int
    template_id: str
    name: str
    role: str
    description: str
    appearance_id: str
    temperament: Temperament
    origin: str
    created_at: datetime
