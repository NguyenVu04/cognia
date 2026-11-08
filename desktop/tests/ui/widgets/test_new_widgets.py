import json
import struct
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from PySide6.QtGui import QColor, QImage

from src.domain.speech.models import MessageKind, ProactiveMessage
from src.ui import theme
from src.ui.views.onboarding import DeskStep, TipsStep
from src.ui.widgets.companion_stage import allowed, call_script
from src.ui.widgets.portrait import thumbnail_bytes
from src.ui.widgets.speech_bubble import SpeechBubble
from src.ui.widgets.typography import paragraph

AT = datetime(2026, 11, 9, tzinfo=timezone.utc)


def message(kind: MessageKind) -> ProactiveMessage:
    return ProactiveMessage(
        "d1",
        kind,
        "Time for a short break?",
        ("You've been here for 1 hour 35 minutes.",),
        AT,
        "p1",
    )


def collect(signal) -> list:
    caught: list = []
    signal.connect(lambda *args: caught.append(args))
    return caught


def test_break_bubble_actions(qtbot) -> None:
    bubble = SpeechBubble()
    qtbot.addWidget(bubble)
    bubble.showMessage(message(MessageKind.BREAK))
    responded, activity = collect(bubble.responded), collect(bubble.activityRequested)

    labels = [
        bubble.actions.itemAt(i).widget().text()
        for i in range(bubble.actions.count() - 1)
    ]
    bubble.actions.itemAt(1).widget().click()

    assert labels == ["Take a break", "Breathe with me", "Later", "Not today"]
    assert responded == [("d1", "taken")]
    assert activity == [("breathing",)]


def test_why_shows_the_reasons(qtbot) -> None:
    bubble = SpeechBubble()
    qtbot.addWidget(bubble)
    bubble.showMessage(message(MessageKind.BREAK))

    bubble.why.click()

    texts = [
        bubble.reasons.itemAt(i).widget().text() for i in range(bubble.reasons.count())
    ]
    assert any("1 hour 35 minutes" in text for text in texts)


def test_dont_send_this_kind(qtbot) -> None:
    bubble = SpeechBubble()
    qtbot.addWidget(bubble)
    bubble.showMessage(message(MessageKind.REMARK))
    caught = collect(bubble.dontSendRequested)

    bubble.dont_send.click()

    assert caught == [("remark",)]


def test_adjustment_offers_undo(qtbot) -> None:
    bubble = SpeechBubble()
    qtbot.addWidget(bubble)
    bubble.showMessage(message(MessageKind.ADJUSTMENT))
    caught = collect(bubble.undoRequested)

    bubble.actions.itemAt(0).widget().click()

    assert caught == [("p1",)]


def test_desk_step_answers(qtbot) -> None:
    step = DeskStep()
    qtbot.addWidget(step)
    caught = collect(step.decided)

    step.yes.click()
    step.no.click()

    assert caught == [(True,), (False,)]


def test_tips_mention_the_talk_key(qtbot) -> None:
    step = TipsStep()
    qtbot.addWidget(step)

    step.setHotkey("Ctrl+Shift+K")

    assert "Ctrl+Shift+K" in step.talk.text()


def _glb(path: Path, with_thumbnail: bool) -> None:
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    png = bytes(buffer.data())
    meta = {"thumbnailImage": 0} if with_thumbnail else {}
    document = {
        "images": [{"bufferView": 0}],
        "bufferViews": [{"byteOffset": 0, "byteLength": len(png)}],
        "extensions": {"VRMC_vrm": {"meta": meta}},
    }
    text = json.dumps(document).encode()
    text += b" " * (-len(text) % 4)
    blob = png + b"\x00" * (-len(png) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text
    chunks += struct.pack("<II", len(blob), 0x004E4942) + blob
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)


def test_reads_the_thumbnail_from_a_glb(tmp_path: Path, qapp) -> None:
    path = tmp_path / "x.vrm"
    _glb(path, True)

    image = QImage.fromData(QByteArray(thumbnail_bytes(path)))

    assert image.width() == 4


def test_no_thumbnail_or_no_file(tmp_path: Path) -> None:
    path = tmp_path / "x.vrm"
    _glb(path, False)

    assert thumbnail_bytes(path) is None
    assert thumbnail_bytes(tmp_path / "none.vrm") is None


def test_page_loads_only_its_own_files(tmp_path: Path) -> None:
    inside = QUrl.fromLocalFile(str(tmp_path / "page" / "index.html"))
    outside = QUrl.fromLocalFile(str(tmp_path.parent / "secret.txt"))

    assert allowed(inside, tmp_path)
    assert allowed(QUrl("qrc:///qtwebchannel/qwebchannel.js"), tmp_path)
    assert not allowed(outside, tmp_path)
    assert not allowed(QUrl("https://example.com/three.js"), tmp_path)


def test_call_quotes_its_arguments() -> None:
    script = call_script("setExpression", 'happy"); alert(1); ("', 0.5)

    assert script == (
        'window.cognia && window.cognia.setExpression('
        '"happy\\"); alert(1); (\\"", 0.5);'
    )


def test_text_colours_reach_aa(qapp) -> None:
    for surface in (
        theme.BG_WINDOW,
        theme.BG_SIDEBAR,
        theme.BG_CARD,
        theme.BG_BUBBLE,
        theme.BG_INSET,
    ):
        for text in (
            theme.TEXT,
            theme.TEXT_SECONDARY,
            theme.TEXT_FAINT,
            theme.ACCENT,
            theme.ACCENT_TEXT,
            theme.DANGER,
        ):
            assert theme.contrast(text, surface) >= 4.5
    assert theme.contrast(theme.ON_ACCENT, theme.ACCENT) >= 4.5
    assert round(theme.contrast(QColor("black"), QColor("white")), 1) == 21.0


def test_stylesheet_has_no_placeholder_left(qapp) -> None:
    assert "$" not in theme.stylesheet()


def test_paragraph_fill(qapp) -> None:
    assert paragraph("Hi", font=theme.font(14), fill=True).wordWrap()
