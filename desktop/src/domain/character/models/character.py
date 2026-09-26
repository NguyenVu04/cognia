from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from ui.views.sample_data import Character


@dataclass(frozen=True)
class Trait:
    id: UUID
    name: str
    description: str
    policies: tuple[str, ...]


@dataclass(frozen=True)
class Version:
    id: UUID
    number: int
    character: Character

    traits: tuple[Trait, ...]

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    parent_version_id: UUID | None = None
    restored_from_version_id: UUID | None = None


@dataclass
class Character:
    id: UUID
    current_version: Version