"""The core thread: the one reader of the one queue, and the one connection.

Everything that reads or writes data happens here, one command at a time and
in the order the commands arrived, so a slow write never stops the window from
drawing. Each command goes to the handler of its feature in ``app/core/``. The
host holds what they share: the stores, the companion's state, and the record
of each event, which also steps the initiative and the learning rules. Effects
leave only after the data they show is committed. Between commands, the host
sleeps until the next time a rule wants to run.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from src.app.bridge import Bridge
from src.app.commands import Command, Stop
from src.app.core.character import CharacterHandler
from src.app.core.chat import ChatHandler
from src.app.core.desk import DeskHandler
from src.app.core.erasure import ErasureHandler
from src.app.core.learning import LearningHandler
from src.app.core.memory import MemoryHandler
from src.app.core.proactive import ProactiveHandler
from src.app.core.settings import SettingsHandler
from src.domain.awareness.awareness_service import AwarenessService
from src.domain.character.character_service import CharacterService
from src.domain.companion import rules as companion_rules
from src.domain.companion.companion_service import CompanionService
from src.domain.companion.models import (
    CompanionState,
    ShowAmbient,
    ShowExpression,
    ShowGesture,
    StepResult,
)
from src.domain.emotion import rules as emotion_rules
from src.domain.emotion.emotion_service import EmotionService
from src.domain.erasure.erasure_service import ErasureService
from src.domain.events.models import EventKind, Payload
from src.domain.memory.memory_service import MemoryService
from src.domain.memory.models import Calibration
from src.domain.ports import CharacterStoreFailed, EventLogFailed
from src.domain.speech.speech_service import SpeechService
from src.infrastructure.storage.app_usage_store import SqliteAppUsage
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.infrastructure.storage.character_store import SqliteCharacterStore
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.decision_store import SqliteDecisionStore
from src.infrastructure.storage.erasure_store import SqliteErasureStore
from src.infrastructure.storage.event_log import SqliteEventLog
from src.infrastructure.storage.memory_store import SqliteMemoryStore
from src.infrastructure.storage.pattern_store import SqlitePatternStore
from src.infrastructure.storage.settings_store import SqliteSettings
from src.infrastructure.storage.sqlite_store import SqliteConversationStore
from src.infrastructure.storage.tool_server_store import SqliteToolServerStore
from src.utils import paths

STEP_FAILED = "Something went wrong, and nothing from that step was saved. Try again."
NOT_OPENED = (
    "Cognia could not open its data file, so nothing can be shown or saved. "
    "Restarting Cognia may help."
)


def offset(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)


def now() -> datetime:
    return datetime.now().astimezone()


class CoreHost(threading.Thread):
    """Holds the database, the services and the companion's state.

    ``embedding_identity`` names the embedding model file, or ``None`` if it is
    missing. ``device_loaded`` receives the stored GPU name, or ``None``, on this
    thread at start, before any model request. A command that fails in a way
    nobody expected is reported through ``Bridge.coreFailed`` with the command
    itself, and the next command is handled as usual.
    """

    def __init__(
        self,
        database_path: Path,
        bridge: Bridge,
        *,
        calibration: Calibration,
        history_max_chars: int,
        embedding_identity: str | None,
        device_loaded: Callable[[str | None], None],
        clock: Callable[[], datetime] = now,
    ) -> None:
        super().__init__(name="cognia-core", daemon=True)
        self._database_path = database_path
        self.bridge = bridge
        self.calibration = calibration
        self.history_max_chars = history_max_chars
        self.embedding_identity = embedding_identity
        self._device_loaded = device_loaded
        self.clock = clock
        self.db: Database | None = None
        self.state: CompanionState = companion_rules.initial_state()
        self._feeling = None
        self.chat = ChatHandler(self)
        self.memory_handler = MemoryHandler(self)
        self.character = CharacterHandler(self)
        self.desk = DeskHandler(self)
        self.proactive = ProactiveHandler(self)
        self.learning = LearningHandler(self)
        self.settings_handler = SettingsHandler(self)
        self.erasure_handler = ErasureHandler(self)
        self._routes: dict[type, Callable[[Command], None]] = {}
        for handler in (
            self.chat, self.memory_handler, self.character, self.desk,
            self.proactive, self.learning, self.settings_handler,
            self.erasure_handler,
        ):
            for kind in handler.handles:
                self._routes[kind] = handler.handle

    # ── the loop ──────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._open()
            self._show_everything()
        except Exception:  # noqa: BLE001 - the window must learn why it is empty
            self.bridge.coreFailed.emit(NOT_OPENED, None)
        self.bridge.ready.emit()
        while True:
            try:
                item = self.bridge.commands.get(timeout=self._sleep())
            except queue.Empty:
                self._guard(self._wake, None)
                continue
            if isinstance(item, Stop):
                break
            handle = self._routes.get(type(item))
            if handle is not None:
                self._guard(lambda item=item: handle(item), item)
        if self.db is not None:
            self.db.close()

    def _guard(self, step: Callable[[], None], item: Command | None) -> None:
        try:
            step()
        except Exception:  # noqa: BLE001 - one broken step must not end the core
            self.bridge.coreFailed.emit(STEP_FAILED, item)

    def _sleep(self) -> float | None:
        """Seconds until the next rule wants to run, or ``None`` to wait for
        the next command only."""
        if self.db is None:
            return None
        wake = self.proactive.next_wake()
        if wake is None:
            return None
        return max(0.0, (wake - self.clock()).total_seconds())

    def _wake(self) -> None:
        if self.db is not None:
            self.proactive.wake(self.clock())

    # ── opening ───────────────────────────────────────────────────────────

    def _open(self) -> None:
        """Open the database on this thread: its one connection lives here."""
        db = self.db = Database.open(self._database_path)
        self.conversations = SqliteConversationStore(db)
        character_store = SqliteCharacterStore(db)
        self.characters = CharacterService(
            character_store, TomlCharacterCatalog(paths.resource("characters.toml"))
        )
        self.memory = MemoryService(SqliteMemoryStore(db))
        self.erasure = ErasureService(SqliteErasureStore(db))
        self.settings = SqliteSettings(db)
        self.log = SqliteEventLog(db)
        self.companion = CompanionService(self.log, EmotionService(character_store))
        self.awareness = AwarenessService(self.log)
        self.app_usage = SqliteAppUsage(db)
        self.speech = SpeechService(SqliteDecisionStore(db))
        self.patterns = SqlitePatternStore(db)
        self.tool_servers = SqliteToolServerStore(db)
        self.fold()
        self._device_loaded(self.settings.chat_device())

    def fold(self) -> None:
        """Compute every state from the whole log, once."""
        try:
            events = list(self.log.read_from(1))
        except EventLogFailed:
            events = []
        try:
            temperaments = self.companion.temperaments()
            self.state = companion_rules.fold(
                companion_rules.initial_state(), events, temperaments
            )
        except (CharacterStoreFailed, ValueError):
            self.state = companion_rules.initial_state()
        self.proactive.fold(events)
        self.learning.fold(events)

    def _show_everything(self) -> None:
        self.character.load()
        self.show_feeling(force=True)
        self.desk.start()
        self.chat.start()
        self.memory_handler.start()
        self.learning.show()
        self.settings_handler.start()
        self.proactive.start()
        if self.character.version is None:
            self.character.show_templates(None)

    # ── events ────────────────────────────────────────────────────────────

    def record(
        self,
        kind: EventKind,
        payload: Payload,
        at: datetime | None = None,
        importance: int | None = None,
    ) -> StepResult:
        """Record one event against the state in force. Call it inside a
        transaction, then :meth:`commit` the result after it."""
        at = at or self.clock()
        return self.companion.record(
            self.state, at, offset(at), kind, payload, importance
        )

    def record_now(
        self, kind: EventKind, payload: Payload, at: datetime | None = None
    ) -> StepResult | None:
        """Record and commit one event on its own. ``None`` if it could not be
        recorded."""
        try:
            with self.db.transaction():
                result = self.record(kind, payload, at)
        except (EventLogFailed, ValueError):
            return None
        self.commit(result)
        return result

    def commit(self, result: StepResult, *, gestures: bool = True) -> None:
        """After the commit: keep the state, carry out the effects, and let
        the other rules see the event."""
        self.state = result.state
        self.show(result.effects, gestures=gestures)
        if result.event is not None:
            self.learning.observe(result.event)
            self.proactive.observe(result.event)
        self.show_feeling()

    def show(self, effects, *, gestures: bool = True) -> None:
        """No gesture on a crisis turn: nothing should look playful there."""
        for effect in effects:
            match effect:
                case ShowExpression(expression):
                    self.bridge.expressionChanged.emit(
                        expression.preset, expression.weight
                    )
                case ShowGesture(name) if gestures:
                    self.bridge.gestureShown.emit(name)
                case ShowAmbient(state):
                    self.bridge.ambientChanged.emit(state)

    def feeling_point(self, at: datetime | None = None):
        try:
            return self.companion.shown_at(self.state, at or self.clock())
        except (CharacterStoreFailed, ValueError):
            return None

    def feeling_name(self) -> str:
        point = self.feeling_point()
        if point is None or not self.state.moods_on:
            return "calm"
        return emotion_rules.name(point)

    def show_feeling(self, *, force: bool = False) -> None:
        """Tell the window the feeling now when it changed, with the face and
        the speed of the voice."""
        point = self.feeling_point()
        if point is None:
            if force:
                self.bridge.feelingShown.emit("", "")
            return
        name = emotion_rules.name(point) if self.state.moods_on else ""
        rest = ""
        version = self.character.version
        if version is not None:
            rest = emotion_rules.name(version.temperament.rest)
        if force or name != self._feeling:
            self._feeling = name
            self.bridge.feelingShown.emit(name, rest)
            face = emotion_rules.expression(point, self.state.moods_on)
            self.bridge.expressionChanged.emit(face.preset, face.weight)
            speed = emotion_rules.speech_speed(point, self.state.moods_on)
            self.bridge.voiceChanged.emit(self.character.voice(), speed)
