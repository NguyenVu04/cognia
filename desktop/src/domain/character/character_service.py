"""Choosing the character, changing it, and going back to an earlier version."""

from __future__ import annotations

import uuid
from datetime import datetime

from src.domain.character import rules
from src.domain.character.models import Template, Version
from src.domain.ports import CharacterCatalog, CharacterStore


class CharacterService:
    """The one character of this installation and its history.

    The time of each change is handed in. Exceptions from the ports pass
    through unchanged, and a failed change leaves the version in force as it was.
    """

    def __init__(self, store: CharacterStore, catalog: CharacterCatalog) -> None:
        self._store = store
        self._catalog = catalog

    def templates(self) -> list[Template]:
        return self._catalog.templates()

    def current(self) -> Version | None:
        """The version in force, or ``None`` until the first choice is made."""
        return self._store.current()

    def history(self) -> list[Version]:
        """Every version, newest first."""
        return self._store.versions()

    def choose(self, template_id: str, now: datetime) -> Version:
        """Put a ready-made character in force: the first choice, or a change.

        Raises ``ValueError`` if no template has ``template_id`` or it is the
        one already in force.
        """
        template = next(
            (t for t in self._catalog.templates() if t.id == template_id), None
        )
        if template is None:
            raise ValueError(f"No ready-made character has the id {template_id!r}.")
        version = rules.from_template(
            template, self._store.versions(), uuid.uuid4().hex, now
        )
        return self._store.add(version)

    def restore(self, version_id: str, now: datetime) -> Version:
        """Put an earlier version back in force as a new version.

        Raises ``ValueError`` if no version has ``version_id`` or it is the one
        already in force.
        """
        history = self._store.versions()
        earlier = next((v for v in history if v.id == version_id), None)
        if earlier is None:
            raise ValueError(f"No version has the id {version_id!r}.")
        version = rules.restored(earlier, history, uuid.uuid4().hex, now)
        return self._store.add(version)
