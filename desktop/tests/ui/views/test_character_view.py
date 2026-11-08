from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.domain.character.models import CHOSEN, RESTORED, Version
from src.domain.emotion.models import Pad, Temperament
from src.ui.views.character import CharacterView
from src.ui.widgets.buttons import Button

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
WEDNESDAY = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)

V1 = Version(
    id="v1", number=1, template_id="yuna", name="Yuna", role="The Gentle Companion",
    description="You are Yuna.", appearance_id="yuna",
    temperament=Temperament(0.4, 30.0, 720.0, Pad(0.1, 0.0, 0.0)),
    origin=CHOSEN, created_at=MONDAY,
)
V2 = replace(V1, id="v2", number=2, template_id="rin", name="Rin",
             description="You are Rin.", created_at=TUESDAY)
V3 = replace(V1, id="v3", number=3, origin=RESTORED, created_at=WEDNESDAY)


@pytest.fixture
def view(qtbot) -> CharacterView:
    shown = CharacterView()
    qtbot.addWidget(shown)
    shown.setCharacter(V3, [(V2, WEDNESDAY), (V1, TUESDAY)])
    return shown


def test_shows_version_in_force(view: CharacterView) -> None:
    assert view.name.text() == "Yuna"
    assert "You are Yuna." in view.description.itemAt(0).widget().text()


def test_earlier_rows(view: CharacterView) -> None:
    assert view.versions.count() == 2
    assert view.none_earlier.isHidden()


def test_restore_emits_version_id(view: CharacterView, qtbot) -> None:
    (button,) = view.versions.itemAt(0).widget().findChildren(Button)

    with qtbot.waitSignal(view.restoreRequested) as signal:
        button.click()
    assert signal.args == ["v2"]


def test_history_error(view: CharacterView) -> None:
    view.showHistoryError("The saved character history cannot be read.")

    assert view.versions.count() == 0
    assert not view.history_error.isHidden()
    assert view.name.text() == "Yuna"


def test_no_earlier_versions(view: CharacterView) -> None:
    view.setCharacter(V1, [])

    assert view.versions.count() == 0
    assert not view.none_earlier.isHidden()


def test_portrait_from_the_vrm(view: CharacterView) -> None:
    pixmap = view.picture.pixmap()

    assert pixmap is not None and not pixmap.isNull()
