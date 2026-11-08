"""Why the companion feels as it does, in the figures it was computed from."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from src.domain.companion.models import FeelingExplanation
from src.ui import theme
from src.ui.dialogs.base import DialogWindow
from src.ui.widgets.buttons import Button
from src.ui.widgets.typography import kicker

MOODS_OFF = "My moods are switched off, so I'm just calm."


def temperament_text(found: FeelingExplanation) -> str:
    temperament = found.temperament
    return (
        f"How strongly things move me: {temperament.reactivity:.2f}. A feeling "
        f"fades by half in {temperament.feeling_half_life_min:g} minutes, a mood "
        f"in {temperament.mood_half_life_min:g} minutes."
    )


class FeelingDialog(DialogWindow):
    def __init__(
        self, name: str, found: FeelingExplanation | None, parent: QWidget | None = None
    ) -> None:
        super().__init__("Why I feel this way", width=500, parent=parent)
        self.title(f"Why {name or 'I'} feel{'s' if name else ''} this way")
        if found is None:
            self.text(MOODS_OFF)
        else:
            point = found.point
            self.text(
                f"I feel {found.feeling} now: warmth {point.pleasure:+.2f}, "
                f"energy {point.arousal:+.2f}. With nothing new I come back to "
                f"{found.rest}."
            )
            self.content.addSpacing(6)
            self.content.addWidget(kicker("What moved it"))
            self.content.addSpacing(4)
            if not found.causes:
                self.text("Nothing in the last 7 days.")
            for cause in found.causes:
                self.text(
                    f"{cause.when}, {cause.what}: warmth {cause.push.pleasure:+.2f}, "
                    f"energy {cause.push.arousal:+.2f}",
                    colour=theme.TEXT,
                )
            self.content.addSpacing(6)
            self.content.addWidget(kicker("My temperament"))
            self.content.addSpacing(4)
            self.text(temperament_text(found))
            if found.floor_reached:
                self.text("I didn't let myself get any sadder.")
        self.buttons.addStretch(1)
        self.add_button(Button("Close", variant="primary"), self.close)
