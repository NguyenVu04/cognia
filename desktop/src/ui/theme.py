"""Visual tokens for the Cognia interface.

The one source of every colour, type size and style sheet in the
presentation layer. A literal colour anywhere else is a bug: widgets read the
constants here, and ``.qss`` files carry ``$TOKEN`` placeholders that
:func:`stylesheet` fills in. Font sizes never appear in QSS, because style
sheets take whole pixels only; every size goes through :func:`font`.

Every text colour below reaches WCAG 2.2 AA (4.5:1) on every surface.
"""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont

from src.utils.paths import resource

# ── families ───────────────────────────────────────────────────────────────

SANS = "Nunito"

# ── surfaces ───────────────────────────────────────────────────────────────

BG_WINDOW = QColor("#1E1A24")
BG_TITLEBAR = QColor("#1B1721")
BG_SIDEBAR = QColor("#19151F")
BG_CARD = QColor("#262130")
BG_INSET = QColor("#16121B")
BG_BUBBLE = QColor("#2C2636")

# ── lines ──────────────────────────────────────────────────────────────────

HAIRLINE = QColor("#2A2433")
BORDER_SUBTLE = QColor("#322B3C")
BORDER = QColor("#3A3245")

# ── accents and states ─────────────────────────────────────────────────────

ACCENT = QColor("#F2A7B8")
ACCENT_2 = QColor("#B9A6F0")
ACCENT_TEXT = QColor("#FFD6DF")
ON_ACCENT = QColor("#2A1820")
DANGER = QColor("#F28B82")
SUCCESS = QColor("#8FD3B6")

# ── text ───────────────────────────────────────────────────────────────────

TEXT = QColor("#F1ECF4")
TEXT_SECONDARY = QColor("#B3A8BB")
TEXT_FAINT = QColor("#A397AB")
# Not for text: switch knobs and idle icons.
KNOB_OFF = QColor("#8E8396")
OVERLAY = QColor(22, 18, 27, 235)


def wash(alpha: float) -> QColor:
    """The accent at partial opacity, for selected and hover fills."""
    return QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), round(alpha * 255))


def css(colour: QColor) -> str:
    """Render a colour for a style sheet, keeping its alpha."""
    return (
        f"rgba({colour.red()}, {colour.green()}, {colour.blue()}, {colour.alpha()})"
    )


def contrast(foreground: QColor, background: QColor) -> float:
    """The WCAG contrast ratio of two opaque colours, from 1.0 to 21.0."""
    lighter, darker = sorted(
        (_luminance(foreground), _luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def blend(foreground: QColor, background: QColor) -> QColor:
    """The opaque colour that ``foreground`` shows on ``background``."""
    alpha = foreground.alphaF()
    return QColor(
        *(
            round(f * alpha + b * (1 - alpha))
            for f, b in (
                (foreground.red(), background.red()),
                (foreground.green(), background.green()),
                (foreground.blue(), background.blue()),
            )
        )
    )


def _luminance(colour: QColor) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(colour.redF())
        + 0.7152 * channel(colour.greenF())
        + 0.0722 * channel(colour.blueF())
    )


# ── type ───────────────────────────────────────────────────────────────────

# Qt sizes type in points; sizes here are pixels at 96 dpi.
PX_TO_PT = 72 / 96


def font(px: float, weight: int = 400, tabular: bool = False) -> QFont:
    """Build a font from a pixel size. ``tabular`` lines figures up in
    columns, for times and counts."""
    f = QFont()
    f.setFamilies([SANS])
    f.setPointSizeF(px * PX_TO_PT)
    f.setWeight(QFont.Weight(weight))
    if tabular:
        f.setFeature(QFont.Tag("tnum"), 1)
    return f


# ── style sheets ───────────────────────────────────────────────────────────

_SHEETS = ("app",)


def _tokens() -> dict[str, str]:
    return {
        "BG_CARD": css(BG_CARD),
        "BG_INSET": css(BG_INSET),
        "BORDER": css(BORDER),
        "ACCENT": css(ACCENT),
        "TEXT": css(TEXT),
        "TEXT_FAINT": css(TEXT_FAINT),
        "WASH_30": css(wash(0.30)),
    }


def stylesheet() -> str:
    """The whole application style sheet, tokens substituted."""
    tokens = _tokens()
    parts = []
    for name in _SHEETS:
        text = resource("qss", f"{name}.qss").read_text(encoding="utf-8")
        parts.append(Template(text).substitute(tokens))
    return "\n".join(parts)
