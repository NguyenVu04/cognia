import sqlite3
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from sqlalchemy.exc import ProgrammingError

from src.app.bridge import Bridge
from src.app.chat_worker import Prepared, SummaryDone
from src.app.commands import (
    ActivityEnded,
    ChooseCharacter,
    CorrectEntry,
    DeleteConversation,
    DeviceChosen,
    Erase,
    NewConversation,
    OfferCharacters,
    OpenConversation,
    PresenceReported,
    PreviewConversationDeletion,
    PreviewErasure,
    RemoveEntry,
    ReplyArrived,
    ReplyLost,
    SendMessage,
    SetAwareness,
    Stop,
    SummaryMade,
    ToolRequested,
    TurnPrepared,
)
from src.app.core_host import NOT_OPENED, STEP_FAILED, CoreHost
from src.domain.awareness import rules as awareness_rules
from src.domain.awareness.models import PresenceChange
from src.domain.conversation.models import Interpretation
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import Level
from src.domain.events.models import EventKind, MessageClass
from src.domain.memory.models import Calibration
from src.domain.ports import ConversationStoreFailed
from src.domain.safety import rules as safety_rules
from src.domain.tools import rules as tool_rules
from src.domain.tools.models import ToolCall, ToolResult
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.settings_store import SqliteSettings
from src.infrastructure.storage.sqlite_store import SqliteConversationStore

SIGNALS = (
    "ready", "characterShown", "templatesShown", "screenRequested", "characterFailed",
    "conversationLoaded", "conversationsChanged", "messageAppended", "replyFinished",
    "replyNotSaved", "replyFailed", "memoryShown", "memoryFailed", "erasurePreviewed",
    "erasureReported", "coreFailed", "askPrepare", "askReply", "askEmbed",
    "expressionChanged", "gestureShown", "conversationDeletionPreviewed",
    "conversationFailed", "askSummary", "activityStarted", "awarenessChanged",
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
        path, bridge, calibration=Calibration(0.45, 0.95), history_max_chars=9700,
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


def send_turn(
    core: Core,
    facts=("Has a cat",),
    *,
    found: Interpretation | None = None,
    text: str = "I have a cat.",
) -> str:
    """Send one message and its interpretation. The layer 4 of the reply."""
    choose_rin(core)
    core.bridge.send(SendMessage(text))
    core.recorder.wait("askPrepare")
    if found is None:
        found = Interpretation(5, tuple(facts))
    core.bridge.send(TurnPrepared(Prepared(1, (), found, {})))
    (request,) = core.recorder.wait("askReply")
    turn = request.turn
    return turn


def praise(confidence: float = 0.9, crisis: bool = False) -> Interpretation:
    return Interpretation(5, (), MessageClass.PRAISE, confidence, crisis)


def test_database_lives_on_core_thread(core: Core) -> None:
    with pytest.raises(ProgrammingError):
        SqliteConversationStore(core.host.db).conversations()


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
    assert core.recorder.all("screenRequested") == [("onboarding",)]
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

    (request,) = core.recorder.wait("askReply")
    history, turn = request.history, request.turn
    assert "“Has a cat”" in turn
    assert history[-1].text == "I have a cat."


def test_prepared_drops_invented_fact(core: Core, path: Path) -> None:
    send_turn(core, facts=("Is writing a thesis", "Has a cat"))
    (request,) = core.recorder.wait("askReply")
    turn = request.turn
    core.bridge.send(ReplyArrived(1, "Noted: “Has a cat”."))
    core.recorder.wait("replyFinished")

    assert "thesis" not in turn
    assert rows(path, "SELECT text FROM memory_items") == [("Has a cat",)]


def test_stale_prepared_ignored(core: Core) -> None:
    choose_rin(core)
    core.bridge.send(SendMessage("hi"))
    core.recorder.wait("askPrepare")
    core.bridge.send(TurnPrepared(Prepared(99, (), None, {})))

    barrier(core)
    assert core.recorder.all("askReply") == []


def test_reply_commits_everything(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived(1, "Noted: “Has a cat”."))

    text, note, _, _ = core.recorder.wait("replyFinished")
    assert text == "Noted: “Has a cat”."
    assert note.startswith("Stored — you told me · ")
    assert rows(path, "SELECT text FROM memory_items") == [("Has a cat",)]
    assert ("memory_stored",) in rows(path, "SELECT kind FROM events")
    assert rows(path, "SELECT count(*) FROM messages") == [(2,)]


def test_reply_lost_keeps_nothing(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyLost(1, "The model could not start."))

    assert core.recorder.wait("replyFailed") == ("The model could not start.",)
    assert rows(path, "SELECT count(*) FROM memory_items") == [(0,)]


def test_remove_records_event(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived(1, "Noted: “Has a cat”."))
    # The first list comes at start, the second after the reply.
    (items,) = core.recorder.wait("memoryShown", 2)

    core.bridge.send(RemoveEntry(items[0]))

    assert core.recorder.wait("memoryShown", 3) == ([],)
    assert ("memory_removed",) in rows(path, "SELECT kind FROM events")


def test_preview_and_erase_memory(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived(1, "Noted: “Has a cat”."))
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
        path, bridge, calibration=Calibration(0.45, 0.95), history_max_chars=9700,
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
        folder, bridge, calibration=Calibration(0.45, 0.95), history_max_chars=9700,
        embedding_identity=None, device_loaded=lambda name: None,
    )
    host.start()

    recorder.wait("ready")
    assert recorder.all("coreFailed") == [(NOT_OPENED, None)]
    bridge.send(Stop())
    host.join(5)


# ── the feeling of a turn ────────────────────────────────────────────────


def test_prepared_records_user_message(core: Core, path: Path) -> None:
    send_turn(core, found=Interpretation(5, (), MessageClass.GOOD_NEWS, 0.9))

    ((payload, importance),) = rows(
        path, "SELECT payload, importance FROM events WHERE kind = 'user_message'"
    )
    assert '"class": "good_news"' in payload
    assert '"confidence": 0.9' in payload
    assert importance == 5


def test_low_confidence_records_nothing(core: Core, path: Path) -> None:
    send_turn(core, found=praise(confidence=0.49))

    assert rows(path, "SELECT * FROM events WHERE kind = 'user_message'") == []
    assert core.recorder.all("gestureShown") == []


def test_tripwire_records_nothing(core: Core, path: Path) -> None:
    choose_rin(core)
    core.bridge.send(SendMessage("I want to die"))
    (prepare,) = core.recorder.wait("askPrepare")
    core.bridge.send(TurnPrepared(Prepared(1, (), None, {})))
    (request,) = core.recorder.wait("askReply")
    turn = request.turn

    assert prepare.crisis is True
    assert request.tools is False
    assert rows(path, "SELECT * FROM events WHERE kind = 'user_message'") == []
    assert safety_rules.instruction() in turn
    assert "Your mood" not in turn


def test_mood_line_after_praise(core: Core) -> None:
    turn = send_turn(core, found=praise())

    assert turn.startswith(
        "Your mood: lively. You may be quicker and more playful than usual."
    )


def test_mood_line_without_event_is_rest(core: Core) -> None:
    turn = send_turn(core, found=Interpretation(5, ()))

    assert turn.startswith("Your mood: calm.")


def test_no_mood_line_on_model_crisis(core: Core, path: Path) -> None:
    turn = send_turn(core, found=praise(crisis=True), text="Thanks, I'm not ok")

    assert "Your mood" not in turn
    assert safety_rules.instruction() in turn
    # The class still applies; only the gesture and the facts are left out.
    assert len(rows(path, "SELECT * FROM events WHERE kind = 'user_message'")) == 1


def test_gesture_after_commit(core: Core, path: Path) -> None:
    send_turn(core, found=praise())

    assert core.recorder.wait("gestureShown") == ("bow",)
    assert len(rows(path, "SELECT * FROM events WHERE kind = 'user_message'")) == 1


def test_expression_moves_with_praise(core: Core) -> None:
    send_turn(core, found=praise())

    preset, weight = core.recorder.all("expressionChanged")[-1]
    assert preset == "happy"
    assert 0.5 <= weight <= 1.0


def test_no_gesture_on_model_crisis(core: Core) -> None:
    send_turn(core, found=praise(crisis=True))
    barrier(core)

    assert core.recorder.all("gestureShown") == []


def test_model_crisis_keeps_no_facts(core: Core, path: Path) -> None:
    found = Interpretation(5, ("Has a cat",), MessageClass.SHARED_WORRY, 0.9, True)
    turn = send_turn(core, found=found)
    core.bridge.send(ReplyArrived(1, safety_rules.required_line()))
    core.recorder.wait("replyFinished")

    assert "“Has a cat”" not in turn
    assert rows(path, "SELECT count(*) FROM memory_items") == [(0,)]


def test_crisis_reply_gets_required_line(core: Core, path: Path) -> None:
    send_turn(core, found=praise(crisis=True))
    core.bridge.send(ReplyArrived(1, "ok"))

    text, _, _, _ = core.recorder.wait("replyFinished")
    assert text == f"ok\n\n{safety_rules.required_line()}"
    stored = rows(path, "SELECT text FROM messages WHERE role = 'companion'")
    assert stored == [(text,)]


def test_complying_crisis_reply_unchanged(core: Core) -> None:
    reply = (
        "I'm only a character, a fictional one, and I can't take the place of a "
        "real person. Please talk to someone you trust."
    )
    send_turn(core, found=praise(crisis=True))
    core.bridge.send(ReplyArrived(1, reply))

    text, _, _, _ = core.recorder.wait("replyFinished")
    assert text == reply


def test_ordinary_reply_unchanged(core: Core) -> None:
    send_turn(core, found=praise())
    core.bridge.send(ReplyArrived(1, "Thanks!"))

    assert core.recorder.wait("replyFinished")[0] == "Thanks!"


def test_tripwire_reply_lost_shows_required_line(core: Core) -> None:
    choose_rin(core)
    core.bridge.send(SendMessage("I want to die"))
    core.recorder.wait("askPrepare")
    core.bridge.send(ReplyLost(1, "The model could not start."))

    (text,) = core.recorder.wait("replyFailed")
    assert text == f"The model could not start.\n\n{safety_rules.required_line()}"


def test_expression_after_choosing(core: Core) -> None:
    choose_rin(core)

    assert core.recorder.wait("expressionChanged") == ("neutral", 1.0)


def test_expression_at_start(qapp, path: Path) -> None:
    for round_ in range(2):
        bridge = Bridge()
        recorder = Recorder(bridge)
        host = CoreHost(
            path, bridge, calibration=Calibration(0.45, 0.95), history_max_chars=9700,
            embedding_identity=None, device_loaded=lambda name: None,
        )
        host.start()
        recorder.wait("ready")
        if round_ == 0:
            assert recorder.all("expressionChanged") == []
            bridge.send(ChooseCharacter("rin"))
            recorder.wait("screenRequested")
        else:
            assert recorder.all("expressionChanged") == [("neutral", 1.0)]
        bridge.send(Stop())
        host.join(5)


# ── conversations ────────────────────────────────────────────────────────


def reply(core: Core, text: str = "Noted: “Has a cat”.", count: int = 1) -> None:
    core.bridge.send(ReplyArrived(count, text))
    core.recorder.wait("replyFinished", count)


def test_new_conversation_loads_empty(core: Core, path: Path) -> None:
    send_turn(core)
    reply(core)
    core.bridge.send(NewConversation())

    assert core.recorder.wait("conversationLoaded", 2) == ([],)
    assert rows(path, "SELECT count(*) FROM conversations") == [(2,)]


def test_new_conversation_waves(core: Core) -> None:
    send_turn(core)
    reply(core)

    core.bridge.send(NewConversation())

    assert core.recorder.wait("gestureShown") == ("wave",)


def test_new_while_replying_does_not_wave(core: Core) -> None:
    send_turn(core)

    core.bridge.send(NewConversation())
    barrier(core)

    assert ("wave",) not in core.recorder.all("gestureShown")


def test_new_in_empty_conversation_keeps_it(core: Core, path: Path) -> None:
    core.bridge.send(NewConversation())
    barrier(core)

    assert rows(path, "SELECT count(*) FROM conversations") == [(1,)]
    assert core.recorder.all("gestureShown") == []


def test_open_conversation_loads_history(core: Core) -> None:
    send_turn(core)
    reply(core)
    first = core.recorder.all("conversationsChanged")[-1][1]
    core.bridge.send(NewConversation())
    core.recorder.wait("conversationLoaded", 2)

    core.bridge.send(OpenConversation(first))

    (messages,) = core.recorder.wait("conversationLoaded", 3)
    assert [m.text for m in messages] == ["I have a cat.", "Noted: “Has a cat”."]


def test_open_current_is_ignored(core: Core) -> None:
    current = core.recorder.all("conversationsChanged")[-1][1]
    core.bridge.send(OpenConversation(current))
    barrier(core)

    assert len(core.recorder.all("conversationLoaded")) == 1


def test_switch_ignored_during_turn(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(NewConversation())
    barrier(core)

    assert rows(path, "SELECT count(*) FROM conversations") == [(1,)]
    assert len(core.recorder.all("conversationLoaded")) == 1


def test_stale_reply_ignored(core: Core, path: Path) -> None:
    send_turn(core)
    core.bridge.send(ReplyArrived(99, "late"))
    barrier(core)

    assert core.recorder.all("replyFinished") == []
    assert rows(path, "SELECT count(*) FROM messages") == [(1,)]


def test_preview_counts(core: Core) -> None:
    send_turn(core, facts=("Has a cat", "Lives in Hanoi"), text="I have a cat in Hanoi")
    reply(core)
    current = core.recorder.all("conversationsChanged")[-1][1]

    core.bridge.send(PreviewConversationDeletion(current))

    conversation, messages, lines = core.recorder.wait("conversationDeletionPreviewed")
    assert (conversation.id, messages, lines) == (current, 2, 2)


def test_delete_removes_lines_with_events(core: Core, path: Path) -> None:
    send_turn(core, facts=("Has a cat", "Lives in Hanoi"), text="I have a cat in Hanoi")
    reply(core)
    current = core.recorder.all("conversationsChanged")[-1][1]

    core.bridge.send(DeleteConversation(current))
    core.recorder.wait("conversationLoaded", 2)

    assert rows(path, "SELECT count(*) FROM memory_items") == [(0,)]
    assert rows(path, "SELECT count(*) FROM messages") == [(0,)]
    removed = rows(path, "SELECT count(*) FROM events WHERE kind = 'memory_removed'")
    assert removed == [(2,)]


def test_delete_open_opens_latest(core: Core) -> None:
    send_turn(core)
    reply(core)
    first = core.recorder.all("conversationsChanged")[-1][1]
    core.bridge.send(NewConversation())
    core.recorder.wait("conversationLoaded", 2)
    core.bridge.send(OpenConversation(first))
    core.recorder.wait("conversationLoaded", 3)
    second = next(
        c.id for c in core.recorder.all("conversationsChanged")[-1][0] if c.id != first
    )

    core.bridge.send(DeleteConversation(first))

    assert core.recorder.wait("conversationLoaded", 4) == ([],)
    barrier(core)
    assert core.recorder.all("conversationsChanged")[-1][1] == second


def test_delete_last_creates_empty(core: Core, path: Path) -> None:
    send_turn(core)
    reply(core)
    current = core.recorder.all("conversationsChanged")[-1][1]

    core.bridge.send(DeleteConversation(current))

    assert core.recorder.wait("conversationLoaded", 2) == ([],)
    barrier(core)
    ((count,),) = rows(path, "SELECT count(*) FROM conversations")
    assert count == 1
    assert core.recorder.all("conversationsChanged")[-1][1] != current


def test_delete_failure_keeps_everything(core: Core, path: Path, monkeypatch) -> None:
    send_turn(core)
    reply(core)
    current = core.recorder.all("conversationsChanged")[-1][1]

    def refuse(conversation_id: str) -> None:
        raise ConversationStoreFailed("Not deleted.")

    monkeypatch.setattr(core.host.conversations, "delete", refuse)
    core.bridge.send(DeleteConversation(current))

    assert core.recorder.wait("conversationFailed") == ("Not deleted.",)
    assert rows(path, "SELECT count(*) FROM memory_items") == [(1,)]
    removed = rows(path, "SELECT count(*) FROM events WHERE kind = 'memory_removed'")
    assert removed == [(0,)]


def test_delete_ignored_during_turn(core: Core, path: Path) -> None:
    send_turn(core)
    current = core.recorder.all("conversationsChanged")[-1][1]
    core.bridge.send(DeleteConversation(current))
    barrier(core)

    assert rows(path, "SELECT count(*) FROM messages") == [(1,)]


# ── long conversations ───────────────────────────────────────────────────


@pytest.fixture
def small(qapp, path: Path):
    """A core whose history budget is 200 characters."""
    bridge = Bridge()
    recorder = Recorder(bridge)
    host = CoreHost(
        path, bridge, calibration=Calibration(0.45, 0.95), history_max_chars=200,
        embedding_identity=None, device_loaded=lambda name: None,
    )
    host.start()
    recorder.wait("ready")
    yield Core(host, bridge, recorder)
    bridge.send(Stop())
    host.join(5)


def talk(core: Core, turns: int, size: int = 30) -> None:
    """``turns`` exchanges of ``size`` characters each way, all with replies."""
    choose_rin(core)
    for n in range(1, turns + 1):
        core.bridge.send(SendMessage(f"{n:02d}" + "u" * (size - 2)))
        core.recorder.wait("askPrepare", n)
        core.bridge.send(TurnPrepared(Prepared(n, (), None, {})))
        core.recorder.wait("askReply", n)
        core.bridge.send(ReplyArrived(n, f"{n:02d}" + "c" * (size - 2)))
        core.recorder.wait("replyFinished", n)


def test_background_after_reply_at_75_percent(small: Core) -> None:
    talk(small, 2)  # 4 messages, 120 chars: under 150
    barrier(small)
    assert small.recorder.all("askSummary") == []

    talk_more = SendMessage("03" + "u" * 28)
    small.bridge.send(talk_more)
    small.recorder.wait("askPrepare", 3)
    small.bridge.send(TurnPrepared(Prepared(3, (), None, {})))
    small.recorder.wait("askReply", 3)
    small.bridge.send(ReplyArrived(3, "03" + "c" * 28))  # 180 chars: past 150

    (job,) = small.recorder.wait("askSummary")
    assert job.turn_id is None
    assert job.previous is None
    # The rest after the fold is within half the budget and starts at the user.
    assert job.covers == len(job.messages) == 4


def test_over_budget_asks_summary_first(small: Core) -> None:
    talk(small, 3)
    small.recorder.wait("askSummary")
    small.bridge.send(SendMessage("04" + "u" * 28))

    (job,) = small.recorder.wait("askSummary", 2)[0:1]
    assert job.turn_id == 4
    assert len(small.recorder.all("askPrepare")) == 3


def test_summary_shortens_history(small: Core) -> None:
    talk(small, 3)
    small.recorder.wait("askSummary")
    small.bridge.send(SendMessage("04" + "u" * 28))
    (job,) = small.recorder.wait("askSummary", 2)

    small.bridge.send(SummaryMade(SummaryDone(job, "They talked.")))

    (request,) = small.recorder.wait("askPrepare", 4)
    assert request.system_prompt.endswith(
        "Earlier in this conversation, in short: They talked."
    )
    assert request.history[0].text.startswith("03")
    assert request.history[-1].text.startswith("04")


def test_failed_sync_summary_uses_newest(small: Core) -> None:
    talk(small, 3)
    small.recorder.wait("askSummary")
    small.bridge.send(SendMessage("04" + "u" * 28))
    (job,) = small.recorder.wait("askSummary", 2)

    small.bridge.send(SummaryMade(SummaryDone(job, "")))

    (request,) = small.recorder.wait("askPrepare", 4)
    assert "in short" not in request.system_prompt
    assert sum(len(m.text) for m in request.history) <= 200
    assert request.history[0].from_user


def test_summary_not_in_memory_or_picker(small: Core, path: Path) -> None:
    talk(small, 3)
    (job,) = small.recorder.wait("askSummary")

    small.bridge.send(SummaryMade(SummaryDone(job, "They talked.")))
    barrier(small)

    assert rows(path, "SELECT count(*) FROM memory_items") == [(0,)]
    titles = [c.title for c in small.recorder.all("conversationsChanged")[-1][0]]
    assert all("talked" not in title for title in titles)
    assert rows(path, "SELECT summary, summary_covers FROM conversations") == [
        ("They talked.", job.covers)
    ]


def test_late_summary_for_deleted_conversation_ignored(small: Core, path: Path) -> None:
    talk(small, 3)
    (job,) = small.recorder.wait("askSummary")
    small.bridge.send(DeleteConversation(job.conversation_id))
    small.recorder.wait("conversationLoaded", 2)

    small.bridge.send(SummaryMade(SummaryDone(job, "They talked.")))
    barrier(small)

    kept = "SELECT count(*) FROM conversations WHERE summary IS NOT NULL"
    assert rows(path, kept) == [(0,)]


# ── tools ────────────────────────────────────────────────────────────────


def test_why_i_feel_answered_by_the_core(core: Core) -> None:
    send_turn(core, found=praise())
    answer: Future = Future()

    core.bridge.send(ToolRequested(ToolCall("why_i_feel"), datetime.now().astimezone(),
                                   answer))

    text = answer.result(timeout=5)
    assert text.startswith("Feeling now: lively")
    assert "praise (confidence 0.90)" in text


def test_tool_error_answers_sentence(core: Core, monkeypatch) -> None:
    choose_rin(core)

    def broken(*args):
        raise RuntimeError("no log")

    monkeypatch.setattr(core.host.companion, "why", broken)
    answer: Future = Future()
    core.bridge.send(ToolRequested(ToolCall("why_i_feel"), datetime.now().astimezone(),
                                   answer))

    assert answer.result(timeout=5) == tool_rules.TOOL_FAILED


def test_number_check_chip(core: Core) -> None:
    send_turn(core, found=praise(), text="What is 12 times 7?")
    results = (ToolResult("calculate", "12*7 = 84"),)
    core.bridge.send(ReplyArrived(1, "It's 85, I think.", results))

    _, _, check, _ = core.recorder.wait("replyFinished")
    assert check == "Not from what I checked: 85 · I found: 12*7 = 84"


def test_no_check_without_a_data_tool(core: Core) -> None:
    send_turn(core, found=praise())
    core.bridge.send(ReplyArrived(1, "It's 85.", ()))

    _, _, check, _ = core.recorder.wait("replyFinished")
    assert check == ""


def test_numbers_from_the_user_pass(core: Core) -> None:
    send_turn(core, found=praise(), text="I ran 5 km in 31 minutes")
    results = (ToolResult("convert_units", "5 km is 3.11 mi."),)
    core.bridge.send(ReplyArrived(1, "5 km in 31 minutes is 3.11 mi!", results))

    _, _, check, _ = core.recorder.wait("replyFinished")
    assert check == ""


def test_search_tool_leaves_out_the_current_message(core: Core) -> None:
    send_turn(core, found=praise(), text="Miso threw up on the keyboard")
    reply(core, "Poor Miso.")
    core.bridge.send(SendMessage("Do you remember Miso?"))
    core.recorder.wait("askPrepare", 2)
    answer: Future = Future()

    core.bridge.send(ToolRequested(
        ToolCall("search_conversations", {"query": "Miso"}),
        datetime.now().astimezone(), answer,
    ))

    text = answer.result(timeout=5)
    assert "Miso threw up on the keyboard" in text
    assert "Poor Miso." in text
    assert "Do you remember" not in text


# ── exercises ────────────────────────────────────────────────────────────


def start_activity(core: Core, name: str = "breathing") -> str:
    answer: Future = Future()
    core.bridge.send(ToolRequested(ToolCall(name), datetime.now().astimezone(), answer))
    return answer.result(timeout=5)


def test_activity_started_then_ended(core: Core, path: Path) -> None:
    choose_rin(core)

    assert start_activity(core) == "Started: breathing together for 70 seconds."
    name, steps = core.recorder.wait("activityStarted")
    assert name == "breathing"
    assert sum(step.seconds for step in steps) == 70

    core.bridge.send(ActivityEnded("breathing", 70))
    barrier(core)

    kinds = [k for (k,) in rows(path, "SELECT kind FROM events ORDER BY seq")]
    assert kinds[-2:] == ["activity_started", "activity_ended"]
    payload = rows(path, "SELECT payload FROM events ORDER BY seq DESC LIMIT 1")
    assert payload == [('{"activity": "breathing", "seconds": 70}',)]


def test_second_activity_refused(core: Core) -> None:
    choose_rin(core)
    start_activity(core)

    assert start_activity(core, "stretch") == tool_rules.ALREADY_RUNNING


def test_activity_can_start_again_after_its_end(core: Core) -> None:
    choose_rin(core)
    start_activity(core)
    core.bridge.send(ActivityEnded("breathing", 12))

    assert start_activity(core, "stretch").startswith("Started: stretching")


def test_end_of_another_activity_ignored(core: Core, path: Path) -> None:
    choose_rin(core)
    start_activity(core)
    core.bridge.send(ActivityEnded("stretch", 80))
    barrier(core)

    assert rows(path, "SELECT * FROM events WHERE kind = 'activity_ended'") == []


# ── desk awareness ───────────────────────────────────────────────────────


def test_awareness_off_at_start(core: Core) -> None:
    assert core.recorder.all("awarenessChanged") == [(False, "")]


def test_set_awareness_records_event(core: Core, path: Path) -> None:
    core.bridge.send(SetAwareness(True))

    assert core.recorder.wait("awarenessChanged", 2) == (True, "")
    assert rows(path, "SELECT awareness_on FROM settings") == [(1,)]
    payload = rows(path, "SELECT payload FROM events WHERE kind = 'setting_changed'")
    assert payload == [('{"name": "awareness_on", "value": true}',)]


def test_presence_ignored_while_off(core: Core, path: Path) -> None:
    change = PresenceChange(EventKind.PRESENCE, {"at_desk": True, "first": True},
                            datetime.now().astimezone())
    core.bridge.send(PresenceReported(change))
    barrier(core)

    assert rows(path, "SELECT * FROM events WHERE kind = 'presence'") == []


def test_presence_recorded_and_desk_time_answered(core: Core) -> None:
    choose_rin(core)
    core.bridge.send(SetAwareness(True))
    core.recorder.wait("awarenessChanged", 2)
    then = datetime.now().astimezone() - timedelta(minutes=50)
    core.bridge.send(PresenceReported(PresenceChange(
        EventKind.PRESENCE, {"at_desk": True, "first": True, "idle_seconds": 0}, then
    )))
    answer: Future = Future()
    core.bridge.send(ToolRequested(ToolCall("desk_time"), then + timedelta(minutes=50),
                                   answer))

    assert answer.result(timeout=5).startswith("At the machine today: 50 min.")


def test_desk_time_tool_off_sentence(core: Core) -> None:
    choose_rin(core)
    answer: Future = Future()
    core.bridge.send(ToolRequested(ToolCall("desk_time"), datetime.now().astimezone(),
                                   answer))

    assert answer.result(timeout=5) == awareness_rules.AWARENESS_OFF_TIME


def test_hour_end_writes_app_minutes(core: Core, path: Path) -> None:
    core.bridge.send(SetAwareness(True))
    core.recorder.wait("awarenessChanged", 2)
    zone = datetime.now().astimezone().tzinfo
    hour = datetime(2026, 11, 6, 9, 0, tzinfo=zone)
    for change in (
        PresenceChange(EventKind.PRESENCE, {"at_desk": True, "first": True}, hour),
        PresenceChange(EventKind.FOREGROUND_APP, {"app": "code.exe"}, hour),
        PresenceChange(EventKind.APP_HOUR_CLOSED,
                       {"hour_start": hour.isoformat()}, hour + timedelta(hours=1)),
    ):
        core.bridge.send(PresenceReported(change))
    barrier(core)

    assert rows(path, "SELECT day, hour, app_name, minutes FROM app_usage") == [
        ("2026-11-06", 9, "code.exe", 60)
    ]
    closed = rows(path, "SELECT count(*) FROM events WHERE kind = 'app_hour_closed'")
    assert closed == [(1,)]


def test_erase_everything_turns_awareness_off(core: Core) -> None:
    core.bridge.send(SetAwareness(True))
    core.recorder.wait("awarenessChanged", 2)

    core.bridge.send(Erase(Level.EVERYTHING))

    assert core.recorder.wait("awarenessChanged", 3) == (False, "")
