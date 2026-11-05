from src.ui.widgets.paused_overlay import PausedOverlay


def test_overlay_names_the_character(qtbot) -> None:
    overlay = PausedOverlay()
    qtbot.addWidget(overlay)

    overlay.setCharacterName("Rin")

    assert "and Rin is off the screen" in overlay._blurb.text()


def test_overlay_without_a_character(qtbot) -> None:
    overlay = PausedOverlay()
    qtbot.addWidget(overlay)

    overlay.setCharacterName("")

    assert "the companion is off the screen" in overlay._blurb.text()
