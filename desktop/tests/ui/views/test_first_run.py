import pytest

from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.ui.views.first_run import FirstRunView
from src.utils.paths import resource


@pytest.fixture
def templates():
    return TomlCharacterCatalog(resource("characters.toml")).templates()


@pytest.fixture
def view(qtbot, templates) -> FirstRunView:
    shown = FirstRunView()
    qtbot.addWidget(shown)
    shown.setTemplates(templates, None)
    return shown


def card(view: FirstRunView, template_id: str):
    return next(c for c in view._cards if c.template.id == template_id)


def test_four_cards_and_nothing_picked(view: FirstRunView) -> None:
    assert [c.template.id for c in view._cards] == ["yuna", "rin", "mira", "shiori"]
    assert not view.confirm.isEnabled()
    assert view.sample.isHidden()
    assert view.eyebrow.text() == "First run"
    assert view.back.isHidden()


def test_pick_shows_answer_and_confirms(view: FirstRunView, qtbot) -> None:
    card(view, "rin").click()

    assert view.confirm.isEnabled()
    assert not view.sample.isHidden()
    assert view.sample_lines.count() > 1
    with qtbot.waitSignal(view.confirmed) as signal:
        view.confirm.click()
    assert signal.args == ["rin"]


def test_change_mode(view: FirstRunView, templates, qtbot) -> None:
    view.setTemplates(templates, "yuna")

    assert not card(view, "yuna").isEnabled()
    assert card(view, "rin").isEnabled()
    assert view.eyebrow.text() == "Change character"
    assert not view.back.isHidden()
    with qtbot.waitSignal(view.backRequested):
        view.back.click()


def test_show_error(view: FirstRunView) -> None:
    view.showError("The character could not be saved.")

    assert not view.error.isHidden()
    assert view.error.text() == "The character could not be saved."
