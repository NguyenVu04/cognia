from datetime import date

import pytest

from src.ui.views.chat import NO_EMOJI, NO_INVISIBLE, ChatView, refusal


@pytest.fixture
def view(qtbot) -> ChatView:
    shown = ChatView()
    qtbot.addWidget(shown)
    shown.setMaxChars(1200)
    return shown


def test_no_counter_below_80_percent(view: ChatView) -> None:
    view.draft.setText("x" * 959)

    assert view.counter.isHidden()
    assert view.send.isEnabled()


def test_counter_from_80_percent(view: ChatView) -> None:
    view.draft.setText("x" * 960)

    assert not view.counter.isHidden()
    assert view.counter.text() == "960 / 1,200"


def test_over_the_limit_stops_send(view: ChatView, qtbot) -> None:
    sent: list[str] = []
    view.messageSent.connect(sent.append)
    view.draft.setText("x" * 1201)

    view.draft.returnPressed.emit()

    assert not view.send.isEnabled()
    assert sent == []
    assert view.draft.text() == "x" * 1201  # nothing is cut


def test_at_the_limit_sends(view: ChatView) -> None:
    sent: list[str] = []
    view.messageSent.connect(sent.append)
    view.draft.setText("x" * 1200)

    view.draft.returnPressed.emit()

    assert sent == ["x" * 1200]


def test_character_header(view: ChatView) -> None:
    view.setCharacter("Rin", "The Teasing Companion", date(2026, 11, 2))

    assert view.name.text() == "Rin"
    assert view.role.text() == "The Teasing Companion · together since 2 November"


def test_reply_note(view: ChatView) -> None:
    view.beginReply()
    view.appendChunk("Noted.")
    row = view._reply_row

    view.endReply("Noted.", "Stored — you told me · 5 Nov")

    assert row._note is not None


@pytest.mark.parametrize(
    "text",
    [
        "I’m tired — really…",
        "a café near the lab",
        "© 2026 and ™",
        "plain ASCII, with (brackets) & 50%",
    ],
)
def test_refusal_allows_ordinary_text(text: str) -> None:
    assert refusal(text) == ""


@pytest.mark.parametrize(
    "text",
    [
        "great \U0001F389",
        "\u2764 you",
        "\u2b50 star",
        "1\ufe0f\u20e3",
        "\U0001F1FB\U0001F1F3",
        "\U0001F469\u200d\U0001F4BB",
    ],
)
def test_refusal_blocks_emoji(text: str) -> None:
    assert refusal(text) == NO_EMOJI


@pytest.mark.parametrize("text", ["a\u200bb", "\u202eevil", "tab\there", "\ue000"])
def test_refusal_blocks_invisible(text: str) -> None:
    assert refusal(text) == NO_INVISIBLE


def test_emoji_shows_notice_and_stops_send(view: ChatView) -> None:
    sent: list[str] = []
    view.messageSent.connect(sent.append)
    view.draft.setText("great \U0001F389")

    view.draft.returnPressed.emit()

    assert not view.counter.isHidden()
    assert view.counter.text() == NO_EMOJI
    assert not view.send.isEnabled()
    assert sent == []
    assert view.draft.text() == "great \U0001F389"


def test_removing_the_emoji_allows_send(view: ChatView) -> None:
    view.draft.setText("great \U0001F389")
    view.draft.setText("great")

    assert view.counter.isHidden()
    assert view.send.isEnabled()


def test_header_locked_while_replying(view) -> None:
    view.beginReply()
    assert not view.picker.isEnabled()
    assert not view.new_button.isEnabled()

    view.endReply("Hello.")
    assert view.picker.isEnabled()
    assert view.new_button.isEnabled()


def test_header_unlocked_after_error(view) -> None:
    view.beginReply()
    view.showError("No model.")

    assert view.picker.isEnabled()


def test_plus_requests_new(view) -> None:
    caught: list[bool] = []
    view.newConversationRequested.connect(lambda: caught.append(True))

    view.new_button.click()

    assert caught == [True]


def test_working_label(view) -> None:
    view.beginReply()
    view.showWorking("checking the date")

    assert view.typing.text() == "checking the date…"
    assert not view.typing_row.isHidden()


def test_working_label_resets_on_the_next_reply(view) -> None:
    view.beginReply()
    view.showWorking("checking the date")
    view.endReply("Friday.")
    view.beginReply()

    assert view.typing.text() == "writing…"


def test_check_chip_shown(view) -> None:
    view.beginReply()
    view.appendChunk("It's 85.")
    row = view._reply_row
    view.endReply("It's 85.", "", "Not from what I checked: 85 · I found: 12*7 = 84")

    assert row.checkText() == "Not from what I checked: 85 · I found: 12*7 = 84"
