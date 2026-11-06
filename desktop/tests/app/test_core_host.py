import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from sqlalchemy.exc import ProgrammingError

from src.app.bridge import Bridge
from src.app.chat_worker import Prepared
from src.app.commands import (
    ChooseCharacter,
    CorrectEntry,
    DeviceChosen,
    Erase,
    OfferCharacters,
    PreviewErasure,
    RemoveEntry,
    ReplyArrived,
    ReplyLost,
    SendMessage,
    Stop,
    TurnPrepared,
)
from src.app.core_host import NOT_OPENED, STEP_FAILED, CoreHost
from src.domain.conversation.models import Interpretation
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import Level
from src.domain.memory.models import Calibration
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.settings_store import SqliteSettings
from src.infrastructure.storage.sqlite_store import SqliteConversationStore

SIGNALS = (
    "ready", "characterShown", "templatesShown", "screenRequested", "characterFailed",
    "conversationLoaded", "conversationsChanged", "messageAppended", "replyFinished",
    "replyNotSaved", "replyFailed", "memoryShown", "memoryFailed", "erasurePreviewed",
    "erasureReported", "coreFailed", "askPrepare", "askReply", "askEmbed",
)


class Recorder:
    """Every signal of the bridge, in order, as (name, args)."""

    def __init__(self, bridge: Bridge) -> None:
        self.seen: list[tuple[str, tuple]] = []
        self._changed = threading.Condition()
        # Direct, so the record happens on the core thread while this thread
        # waits; a queued call would wait for an event loop that never runs.
        for name in SIGNALS:
            getattr(bridge, name).connect(
                lambda *args, name=name: self._add(name, args),
                Qt.ConnectionType.DirectConnection,
            )

    def _add(self, name: str, args: tuple) -> None:
        with self._changed:
            self.seen.append((name, args))
            self._changed.notify_all()

    def all(self, name: str) -> list[tuple]:
        with self._changed:
            return [args for seen, args in self.seen if seen == name]

    def wait(self, name: str, count: int = 1, timeout: float = 10) -> tuple:
        """The args of the ``count``-th emission of ``name``."""
        with self._changed:
            done = self._changed.wait_for(
                lambda: len([s for s, _ in self.seen if s == name]) >= count, timeout
            )
        assert done, f"{name} #{count} never came; seen {[s for s, _ in self.seen]}"
        return self.all(name)[count - 1]


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def loaded() -> list:
    return []


@dataclass(frozen=True)
class Core:
    host: CoreHost
    bridge: Bridge
    recorder: Recorder


@pytest.fixture
def core(qapp, path: Path, loaded: list):
    bridge = Bridge()
    recorder = Recorder(bridge)
    host = CoreHost(
        path, bridge, calibration=Calibration(0.45, 0.95), history_messages=40,
        embedding_identity=None, device_loaded=loaded.append,
    )
    host.start()
    recorder.wait("ready")
    yield Core(host, bridge, recorder)
    bridge.send(Stop())
    host.join(5)


def rows(path: Path, sql: str) -> list[tuple]:
    connection = sqlite3.connect(path)
    result = connection.execute(sql).fetchall()
    connection.close()
    return result


def barrier(core: Core) -> None:
    """Wait until the core has handled everything sent before this."""
    count = len(core.recorder.all("templatesShown")) + 1
    core.bridge.send(OfferCharacters())
    core.recorder.wait("templatesShown", count)


def choose_rin(core: Core) -> None:
    core.bridge.send(ChooseCharacter("rin"))
    core.recorder.wait("screenRequested")


def send_turn(core: Core, facts=("Has a cat",)) -> None:
    choose_rin(core)
    core.bridge.send(SendMessage("I have a cat."))
    core.recorder.wait("askPrepare")
    found = Interpretation(5, tuple(facts))
    core.bridge.send(TurnPrepared(Prepared(1, (), found, {})))
    core.recorder.wait("askReply")


def test_database_lives_on_core_thread(core: Core) -> None:
    with pytest.raises(ProgrammingError):
        SqliteConversationStore(core.host._db).conversations()


def test_start_without_character(core: Core) -> None:
    version, earlier, since, error = core.recorder.wait("characterShown")
    templates, in_force, catalog_error = core.recorder.wait("templatesShown")

    assert version is None
    assert [t.id for t in templates] == ["yuna", "rin", "mira", "shiori"]
    assert (in_force, catalog_error) == (None, "")


def test_choose_records_character_changed(core: Core, path: Path) -> None:
    choose_rin(core)

    version, _, since, _ = core.recorder.wait("characterShown", 2)
    assert version.name == "Rin"
    assert core.recorder.all("screenRequested") == [("chat",)]
    assert rows(path, "SELECT kind FROM events") == [("character_changed",)]


def test_send_without_character(core: Core, path: Path) -> None:
    core.bridge.send(SendMessage("hi"))

    core.recorder.wait("templatesShown", 2)
    assert rows(path, "SELECT count(*) FROM messages") == [(0,)]


def test_send_appends_and_asks_prepare(core: Core) -> None:
    choose_rin(core)
    core.bridge.send(SendMessage("hi"))

    (message,) = core.recorder.wait("messageAppended")
    (request,) = core.recorder.wait("askPrepare")
    assert message.text == "hi"
    assert request.turn_id == 1
    assert request.history[-1].text == "hi"
    assert "You are Rin" in request.system_prompt


def test_prepared_asks_reply_with_quote(core: Core) -> None:
    send_turn(core)

    _, history, turn = core.recorder.wait("askReply")
    assert "“Has a cat”" in turn
    assert history[-1].text == "I have a cat."


def test_stale_prepared_ignored(core: Core) -> None:
    choose_rin(core)
    core.bridge.send(SendMessage("hi"))
    core.recorder.wait("askPrepare")
    core.bridge.send(TurnPrepared(Prepared(99, (), None, {})))

    barrier(core)
    assert core.recorder.all("askReply") == []


def test_reply_commits_everything(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived("Noted: “Has a cat”."))

    text, note = core.recorder.wait("replyFinished")
    assert text == "Noted: “Has a cat”."
    assert note.startswith("Stored — you told me · ")
    assert rows(path, "SELECT text FROM memory_items") == [("Has a cat",)]
    assert ("memory_stored",) in rows(path, "SELECT kind FROM events")
    assert rows(path, "SELECT count(*) FROM messages") == [(2,)]


def test_reply_lost_keeps_nothing(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyLost("The model could not start."))

    assert core.recorder.wait("replyFailed") == ("The model could not start.",)
    assert rows(path, "SELECT count(*) FROM memory_items") == [(0,)]


def test_remove_records_event(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived("Noted: “Has a cat”."))
    # The first list comes at start, the second after the reply.
    (items,) = core.recorder.wait("memoryShown", 2)

    core.bridge.send(RemoveEntry(items[0]))

    assert core.recorder.wait("memoryShown", 3) == ([],)
    assert ("memory_removed",) in rows(path, "SELECT kind FROM events")


def test_preview_and_erase_memory(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived("Noted: “Has a cat”."))
    core.recorder.wait("replyFinished")

    core.bridge.send(PreviewErasure(Level.MEMORY))
    level, counts, name = core.recorder.wait("erasurePreviewed")
    core.bridge.send(Erase(Level.MEMORY))
    (report,) = core.recorder.wait("erasureReported")

    assert (level, name) == (Level.MEMORY, "Rin")
    assert sum(c.rows for c in counts) > 0
    assert report.complete
    assert rows(path, "SELECT kind FROM events") == [("character_changed",)]
    assert rows(path, "SELECT count(*) FROM character_versions") == [(1,)]


def test_handler_error_continues(core: Core) -> None:
    core.bridge.send(CorrectEntry(None, "not an entry"))

    assert core.recorder.wait("coreFailed") == (
        STEP_FAILED, CorrectEntry(None, "not an entry")
    )
    barrier(core)


def test_preview_error_names_the_command(core: Core, monkeypatch) -> None:
    def broken(self, level):
        raise RuntimeError("preview broke")

    monkeypatch.setattr(ErasureService, "preview", broken)
    core.bridge.send(PreviewErasure(Level.MEMORY))

    assert core.recorder.wait("coreFailed") == (
        STEP_FAILED, PreviewErasure(Level.MEMORY)
    )
    assert core.recorder.all("erasurePreviewed") == []


def test_stop_closes_and_ends(core: Core) -> None:
    core.bridge.send(Stop())
    core.host.join(5)

    assert not core.host.is_alive()


def test_device_loaded_at_start(core: Core, loaded: list) -> None:
    assert loaded == [None]


def test_stored_device_loaded(qapp, path: Path) -> None:
    db = Database.open(path)
    SqliteSettings(db).set_chat_device("GPU")
    db.close()
    loaded: list = []
    bridge = Bridge()
    recorder = Recorder(bridge)
    host = CoreHost(
        path, bridge, calibration=Calibration(0.45, 0.95), history_messages=40,
        embedding_identity=None, device_loaded=loaded.append,
    )
    host.start()
    recorder.wait("ready")
    bridge.send(Stop())
    host.join(5)

    assert loaded == ["GPU"]


def test_device_chosen_saved(core: Core, path: Path) -> None:
    core.bridge.send(DeviceChosen("GPU"))
    barrier(core)

    assert rows(path, "SELECT chat_device FROM settings") == [("GPU",)]


def test_unopened_database_reports(qapp, tmp_path: Path) -> None:
    folder = tmp_path / "a folder, not a file"
    folder.mkdir()
    bridge = Bridge()
    recorder = Recorder(bridge)
    host = CoreHost(
        folder, bridge, calibration=Calibration(0.45, 0.95), history_messages=40,
        embedding_identity=None, device_loaded=lambda name: None,
    )
    host.start()

    recorder.wait("ready")
    assert recorder.all("coreFailed") == [(NOT_OPENED, None)]
    bridge.send(Stop())
    host.join(5)
