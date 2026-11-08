"""The settings row, and the switches of each kind of message.

A failure to save a choice the user made raises :class:`SettingNotSaved`. A
failure to read falls back to the default, and a lost value the application
chose itself, such as the GPU, is not reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from src.domain.speech.models import MessageKind, SpeechSettings
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database

settings = orm.Settings.__table__
kinds = orm.MessageKind.__table__

NOT_SAVED = "The setting could not be saved. Nothing was changed."
DEFAULT_HOTKEY = "Ctrl+Alt+Space"


class SettingNotSaved(Exception):
    """A setting the user chose could not be saved, with a sentence saying so."""


@dataclass(frozen=True)
class Placement:
    """Where the companion was left, and whether it is hidden."""

    x: int | None
    y: int | None
    screen: str | None
    hidden: bool


class SqliteSettings:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ── reading ───────────────────────────────────────────────────────────

    def _row(self):
        try:
            with self._db.transaction() as db:
                return db.execute(select(settings)).one_or_none()
        except SQLAlchemyError:
            return None

    def chat_device(self) -> str | None:
        row = self._row()
        return row.chat_device if row else None

    def awareness_on(self) -> bool:
        row = self._row()
        return bool(row.awareness_on) if row else False

    def speech(self) -> SpeechSettings:
        row = self._row()
        if row is None:
            return SpeechSettings.defaults()
        quiet = None
        if row.quiet_start and row.quiet_end:
            quiet = (
                time.fromisoformat(row.quiet_start),
                time.fromisoformat(row.quiet_end),
            )
        return SpeechSettings(
            ceiling=row.daily_ceiling,
            quiet=quiet,
            enabled=self._enabled(),
            moods_on=bool(row.moods_on),
            break_threshold_min=row.break_threshold_min,
        )

    def _enabled(self) -> frozenset[MessageKind]:
        known = {kind.value for kind in MessageKind}
        try:
            with self._db.transaction() as db:
                rows = db.execute(select(kinds.c.id).where(kinds.c.enabled == 1)).all()
        except SQLAlchemyError:
            return frozenset(MessageKind)
        return frozenset(MessageKind(r.id) for r in rows if r.id in known)

    def speak_aloud(self) -> bool:
        row = self._row()
        return bool(row.speak_aloud) if row else True

    def talk_hotkey(self) -> str:
        row = self._row()
        return row.talk_hotkey if row else DEFAULT_HOTKEY

    def placement(self) -> Placement:
        row = self._row()
        if row is None:
            return Placement(None, None, None, False)
        return Placement(
            row.companion_x,
            row.companion_y,
            row.companion_screen,
            bool(row.companion_hidden),
        )

    def paused_until(self) -> tuple[datetime | None, datetime | None, bool]:
        """When the pause began, when it ends, and whether one is in force.
        A pause until the user resumes has no end."""
        row = self._row()
        if row is None or row.paused_at is None:
            return None, None, False
        until = datetime.fromisoformat(row.paused_until) if row.paused_until else None
        return datetime.fromisoformat(row.paused_at), until, True

    def close_hint_shown(self) -> bool:
        row = self._row()
        return bool(row.close_hint_shown) if row else False

    # ── writing ───────────────────────────────────────────────────────────

    def _write(self, **values) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(update(settings).values(**values))
        except SQLAlchemyError as error:
            raise SettingNotSaved(NOT_SAVED) from error

    def set_awareness_on(self, on: bool) -> None:
        self._write(awareness_on=int(on))

    def set_speech(self, chosen: SpeechSettings) -> None:
        """Keep every speech setting at once, or none of them."""
        start, end = chosen.quiet if chosen.quiet else (None, None)
        try:
            with self._db.transaction() as db:
                db.execute(
                    update(settings).values(
                        daily_ceiling=chosen.ceiling,
                        quiet_start=start.strftime("%H:%M") if start else None,
                        quiet_end=end.strftime("%H:%M") if end else None,
                        break_threshold_min=chosen.break_threshold_min,
                        moods_on=int(chosen.moods_on),
                    )
                )
                for kind in MessageKind:
                    db.execute(
                        update(kinds)
                        .where(kinds.c.id == kind.value)
                        .values(enabled=int(kind in chosen.enabled))
                    )
        except SQLAlchemyError as error:
            raise SettingNotSaved(NOT_SAVED) from error

    def set_kind(self, kind: MessageKind, enabled: bool) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(
                    update(kinds)
                    .where(kinds.c.id == kind.value)
                    .values(enabled=int(enabled))
                )
        except SQLAlchemyError as error:
            raise SettingNotSaved(NOT_SAVED) from error

    def set_speak_aloud(self, on: bool) -> None:
        self._write(speak_aloud=int(on))

    def set_talk_hotkey(self, sequence: str) -> None:
        self._write(talk_hotkey=sequence)

    def set_placement(self, x: int, y: int, screen: str) -> None:
        self._write(companion_x=x, companion_y=y, companion_screen=screen)

    def set_hidden(self, hidden: bool) -> None:
        self._write(companion_hidden=int(hidden))

    def set_paused(self, at: datetime | None, until: datetime | None) -> None:
        """A pause from ``at`` to ``until``; ``at`` ``None`` ends it."""
        self._write(
            paused_at=at.isoformat() if at else None,
            paused_until=until.isoformat() if at and until else None,
        )

    def set_close_hint_shown(self) -> None:
        self._write(close_hint_shown=1)

    def set_chat_device(self, name: str) -> None:
        try:
            self._write(chat_device=name)
        except SettingNotSaved:
            pass
