"""The character in force, the choice of another, and going back to an earlier
version."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.commands import ChooseCharacter, OfferCharacters, RestoreVersion
from src.domain.character import rules as character_rules
from src.domain.conversation import rules
from src.domain.events.models import EventKind
from src.domain.ports import (
    CharacterCatalogUnavailable,
    CharacterStoreFailed,
    EventLogFailed,
)

if TYPE_CHECKING:
    from src.app.core_host import CoreHost

DEFAULT_VOICE = "af_heart"


class CharacterHandler:
    handles = (OfferCharacters, ChooseCharacter, RestoreVersion)

    def __init__(self, core: CoreHost) -> None:
        self.core = core
        self.version = None
        self.prompt = ""
        self._voices: dict[str, str] = {}

    def handle(self, item) -> None:
        match item:
            case OfferCharacters():
                version = self.version
                self.show_templates(version.template_id if version else None)
            case ChooseCharacter(template_id):
                self._choose(template_id)
            case RestoreVersion(version_id):
                self._put_in_force(
                    lambda now: self.core.characters.restore(version_id, now)
                )

    def voice(self) -> str:
        """The Kokoro voice of the character in force."""
        if self.version is None:
            return DEFAULT_VOICE
        if not self._voices:
            try:
                self._voices = {t.id: t.voice for t in self.core.characters.templates()}
            except CharacterCatalogUnavailable:
                return DEFAULT_VOICE
        return self._voices.get(self.version.template_id, DEFAULT_VOICE)

    def load(self) -> None:
        """Put the version in force everywhere it shows."""
        core = self.core
        try:
            self.version = core.characters.current()
        except CharacterStoreFailed:
            self.version = None
        version = self.version
        if version is None:
            self.prompt = ""
            core.bridge.characterShown.emit(None, [], None, "")
            return
        self.prompt = (
            f"{rules.system_text(version.description)}\n\n{rules.REASONING_RULE}"
        )
        try:
            history = core.characters.history()
        except CharacterStoreFailed as error:
            core.bridge.characterShown.emit(version, [], None, str(error))
            return
        first = min(history, key=lambda v: v.number)
        earlier = [
            (v, character_rules.in_force_until(v, history))
            for v in history
            if v.id != version.id
        ]
        core.bridge.characterShown.emit(
            version, earlier, first.created_at.astimezone().date(), ""
        )

    def show_templates(self, in_force: str | None) -> None:
        try:
            templates = self.core.characters.templates()
        except CharacterCatalogUnavailable as error:
            self.core.bridge.templatesShown.emit([], in_force, str(error))
            return
        self.core.bridge.templatesShown.emit(templates, in_force, "")

    def _choose(self, template_id: str) -> None:
        first = self.version is None
        self._put_in_force(lambda now: self.core.characters.choose(template_id, now))
        if self.version is not None:
            self.core.bridge.screenRequested.emit(
                "onboarding" if first else "character"
            )

    def _put_in_force(self, add) -> None:
        """Add a version and record ``character_changed`` in one transaction."""
        core = self.core
        now = core.clock()
        try:
            with core.db.transaction():
                version = add(now)
                result = core.record(
                    EventKind.CHARACTER_CHANGED, {"version_id": version.id}, now
                )
        except (CharacterStoreFailed, EventLogFailed, ValueError) as error:
            core.bridge.characterFailed.emit(str(error))
            return
        core.commit(result)
        self.load()
        core.show_feeling(force=True)
