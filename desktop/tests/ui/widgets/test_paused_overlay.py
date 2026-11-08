from src.ui.widgets.paused_overlay import PausedOverlay


def test_overlay_names_the_character(qtbot) -> None:
    overlay = PausedOverlay()
    qtbot.addWidget(overlay)

    overlay.setCharacterName("Rin")

    assert "Rin is taking a break too" in overlay.blurb.text()


def test_overlay_without_a_character(qtbot) -> None:
    overlay = PausedOverlay()
    qtbot.addWidget(overlay)

    overlay.setCharacterName("")

    assert "Your companion is taking a break too" in overlay.blurb.text()


def test_overlay_says_until_when(qtbot) -> None:
    overlay = PausedOverlay()
    qtbot.addWidget(overlay)

    overlay.setPause("until 15:40")

    assert overlay.title.text() == "Paused until 15:40"


def test_resume_emits(qtbot) -> None:
    overlay = PausedOverlay()
    qtbot.addWidget(overlay)

    with qtbot.waitSignal(overlay.resumed):
        overlay.resume.click()
