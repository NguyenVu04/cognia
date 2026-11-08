"""Desk awareness: switching it on and off, the facts the sampler reports, and
the applications that are not counted."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.app.commands import ExcludeApp, IncludeApp, PresenceReported, SetAwareness
from src.domain.awareness import rules as awareness_rules
from src.domain.awareness.models import PresenceChange
from src.domain.events.models import EventKind
from src.domain.ports import EventLogFailed
from src.infrastructure.storage.app_usage_store import AppListNotChanged
from src.infrastructure.storage.settings_store import SettingNotSaved

if TYPE_CHECKING:
    from src.app.core_host import CoreHost

# The changes that move the time at the desk shown in the settings.
_SHOWN = (EventKind.PRESENCE, EventKind.FOREGROUND_APP, EventKind.APP_HOUR_CLOSED)


class DeskHandler:
    handles = (SetAwareness, PresenceReported, ExcludeApp, IncludeApp)

    def __init__(self, core: CoreHost) -> None:
        self.core = core
        self.awareness_on = False
        self.excluded: set[str] = set()
        self.locked = False
        self.presenting = False

    def start(self) -> None:
        self.awareness_on = self.core.settings.awareness_on()
        self.excluded = set(self.core.app_usage.excluded())
        self.core.bridge.awarenessChanged.emit(self.awareness_on, "")
        self.show()

    def handle(self, item) -> None:
        match item:
            case SetAwareness(on, error):
                self._set(on, error)
            case PresenceReported(change):
                self._presence(change)
            case ExcludeApp(name):
                self._exclude(name)
            case IncludeApp(name):
                self._include(name)

    def _set(self, on: bool, error: str) -> None:
        """Keep the user's choice and record it, so a replay sees it too."""
        core = self.core
        if on == self.awareness_on:
            core.bridge.awarenessChanged.emit(on, error)
            return
        payload = {"name": awareness_rules.AWARENESS_ON, "value": on}
        try:
            with core.db.transaction():
                core.settings.set_awareness_on(on)
                result = core.record(EventKind.SETTING_CHANGED, payload)
        except (SettingNotSaved, EventLogFailed) as failure:
            core.bridge.awarenessChanged.emit(self.awareness_on, str(failure))
            return
        self.awareness_on = on
        core.commit(result)
        core.bridge.awarenessChanged.emit(on, error)
        self.show()

    def _presence(self, change: PresenceChange) -> None:
        """Record a change the sampler saw. A report that arrives after desk
        awareness went off is dropped: nothing is read while it is off."""
        if not self.awareness_on:
            return
        payload = change.payload
        if (
            change.kind == EventKind.FOREGROUND_APP
            and payload.get("app") in self.excluded
        ):
            payload = {**payload, "app": ""}
        if change.kind == EventKind.PRESENCE:
            self.locked = bool(payload.get("locked"))
            self.presenting = bool(payload.get("presenting"))
        core = self.core
        try:
            with core.db.transaction():
                result = core.record(change.kind, payload, change.at)
                if change.kind == EventKind.APP_HOUR_CLOSED:
                    self._close_hour(change)
        except (EventLogFailed, ValueError):
            return  # the next change is reported as usual
        core.commit(result)
        if change.kind in _SHOWN:
            self.show()

    def _close_hour(self, change: PresenceChange) -> None:
        """Keep the minutes of each application in the hour that ended, as the
        day it belongs to and its local hour."""
        start = datetime.fromisoformat(str(change.payload["hour_start"]))
        minutes = self.core.awareness.app_minutes(start, start + timedelta(hours=1))
        day = awareness_rules.day_start(start).date().isoformat()
        self.core.app_usage.put(day, start.hour, minutes)

    def _exclude(self, name: str) -> None:
        """Stop counting ``name``, and delete its totals and its recorded
        changes."""
        core = self.core
        try:
            seqs = [
                e.seq
                for e in core.log.read_from(1)
                if e.kind == EventKind.FOREGROUND_APP and e.payload.get("app") == name
            ]
            with core.db.transaction():
                core.app_usage.exclude(name)
                if seqs:
                    core.log.delete(seqs)
        except (AppListNotChanged, EventLogFailed) as error:
            core.bridge.deskShown.emit(None, None, sorted(self.excluded))
            core.bridge.noticeShown.emit(str(error))
            return
        self.excluded.add(name)
        self.show()

    def _include(self, name: str) -> None:
        try:
            self.core.app_usage.include(name)
        except AppListNotChanged as error:
            self.core.bridge.noticeShown.emit(str(error))
            return
        self.excluded.discard(name)
        self.show()

    def show(self) -> None:
        """Today's time at the machine and in each application."""
        core = self.core
        excluded = sorted(self.excluded)
        if not self.awareness_on:
            core.bridge.deskShown.emit(None, None, excluded)
            return
        now = core.clock()
        try:
            desk = core.awareness.desk_time(now)
            minutes = core.awareness.app_minutes(awareness_rules.day_start(now), now)
        except EventLogFailed:
            return
        minutes = {
            app: count
            for app, count in minutes.items()
            if app and app not in self.excluded and count > 0
        }
        core.bridge.deskShown.emit(desk, minutes, excluded)
