from src.ui.dialogs.delete_conversation_dialog import (
    DeleteConversationDialog,
    deletion_text,
)


def test_states_counts() -> None:
    assert deletion_text("Cats", 4, 2) == (
        "“Cats” has 4 messages. 2 lines I remember come from it, and they go too."
    )


def test_singular() -> None:
    assert deletion_text("Cats", 1, 1) == (
        "“Cats” has 1 message. 1 line I remember comes from it, and it goes too."
    )


def test_no_lines() -> None:
    assert deletion_text("Cats", 3, 0) == (
        "“Cats” has 3 messages. Nothing I remember comes from it."
    )


def test_confirm_emits_and_closes(qtbot) -> None:
    dialog = DeleteConversationDialog("Cats", 4, 2)
    qtbot.addWidget(dialog)
    dialog.show()
    caught: list[bool] = []
    dialog.confirmed.connect(lambda: caught.append(True))

    dialog.delete.click()

    assert caught == [True]
    assert not dialog.isVisible()
