from datetime import datetime, timezone

from src.domain.conversation.models import Conversation
from src.ui.dialogs.conversation_menu import MAX_LIST_HEIGHT, ConversationMenu
from src.ui.widgets.buttons import TextButton

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def conversations(n: int) -> list[Conversation]:
    return [Conversation(f"c{i}", f"Talk {i}", NOW) for i in range(n)]


def test_lists_all_conversations(qtbot) -> None:
    menu = ConversationMenu()
    qtbot.addWidget(menu)

    menu.setConversations(conversations(25), "c0")

    assert menu.rows() == 25
    assert menu._scroll.height() <= MAX_LIST_HEIGHT


def test_delete_emits_id(qtbot) -> None:
    menu = ConversationMenu()
    qtbot.addWidget(menu)
    menu.setConversations(conversations(3), "c0")
    caught: list[str] = []
    menu.deleteRequested.connect(caught.append)

    deletes = menu.findChildren(TextButton, "delete")
    deletes[1].click()

    assert caught == ["c1"]
