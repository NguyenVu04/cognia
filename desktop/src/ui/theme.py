"""Visual tokens for the Cognia interface.

Single source of truth for every colour, type size and stylesheet in the
presentation layer. Two rules follow from it:

* **A literal colour anywhere else is a bug.** Widgets read the constants and
  helpers here; ``.qss`` files carry ``$TOKEN`` placeholders substituted by
  :func:`stylesheet`.
* **Font sizes never appear in QSS.** Qt style sheets accept whole pixels only
  and the design is built on fractional sizes (9.5, 12.5, 13.8, 14.5 …), so
  every size goes through :func:`font`, which carries the fraction through
  ``setPointSizeF``.
"""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont

from src.utils.paths import resource

# ── families ───────────────────────────────────────────────────────────────

SANS = "Inter"
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "Menlo", "monospace"]

# ── surfaces ───────────────────────────────────────────────────────────────

BG_WINDOW = QColor("#1b1d2b")
BG_TITLEBAR = QColor("#191b28")
BG_SIDEBAR = QColor("#171927")
BG_CARD = QColor("#1f2130")
BG_INSET = QColor("#141625")
BG_BUBBLE = QColor("#232532")

# ── lines ──────────────────────────────────────────────────────────────────

HAIRLINE = QColor("#232634")
BORDER_SUBTLE = QColor("#2b2e3d")
BORDER = QColor("#3f424d")

# ── accent ─────────────────────────────────────────────────────────────────

ACCENT = QColor("#9184d9")
ACCENT_TEXT = QColor("#d2cefd")
ACCENT_LINK = QColor("#b5abfc")

# ── text and parts ─────────────────────────────────────────────────────────

TEXT = QColor("#e9e9ed")
KNOB_OFF = QColor("#75798c")
OVERLAY = QColor(16, 18, 32, 235)  # rgba(16,18,32,.92)
SHADOW = QColor(0, 0, 0, 179)  # rgba(0,0,0,.7)


def muted(alpha: float) -> QColor:
    """Body text at partial opacity — the design's ``rgba(233,233,237,a)``."""
    return QColor(233, 233, 237, round(alpha * 255))


def wash(alpha: float) -> QColor:
    """Accent at partial opacity — the design's ``rgba(145,132,217,a)``."""
    return QColor(145, 132, 217, round(alpha * 255))


def css(colour: QColor) -> str:
    """Render a colour for a style sheet, keeping its alpha."""
    return (
        f"rgba({colour.red()}, {colour.green()}, {colour.blue()}, {colour.alpha()})"
    )


# ── type ───────────────────────────────────────────────────────────────────

# Qt sizes type in points; the design is in CSS pixels at 96 dpi.
_PX_TO_PT = 72 / 96


def font(
    px: float,
    weight: int = 400,
    spacing_em: float = 0.0,
    tabular: bool = False,
    mono: bool = False,
) -> QFont:
    """Build a font from a CSS pixel size.

    ``spacing_em`` mirrors CSS ``letter-spacing`` and ``tabular`` mirrors
    ``font-variant-numeric: tabular-nums``, which the design uses for every
    figure that sits in a column.
    """
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else [SANS])
    f.setPointSizeF(px * _PX_TO_PT)
    f.setWeight(QFont.Weight(weight))
    if spacing_em:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + spacing_em * 100)
    if tabular:
        # OpenType tabular figures, so the elapsed time and the session
        # lengths line up in their columns. Qt wants a QFont.Tag, not a str.
        f.setFeature(QFont.Tag("tnum"), 1)
    return f


# ── style sheets ───────────────────────────────────────────────────────────

# One resource sheet, holding what is genuinely global. Component looks are
# built by the factories in ``src/ui/widgets/`` from the tokens above, because
# the design varies radius and padding per instance and a style sheet cannot
# parameterise either.
_SHEETS = ("app",)


def _tokens() -> dict[str, str]:
    return {
        "BG_WINDOW": css(BG_WINDOW),
        "BG_TITLEBAR": css(BG_TITLEBAR),
        "BG_SIDEBAR": css(BG_SIDEBAR),
        "BG_CARD": css(BG_CARD),
        "BG_INSET": css(BG_INSET),
        "BG_BUBBLE": css(BG_BUBBLE),
        "HAIRLINE": css(HAIRLINE),
        "BORDER_SUBTLE": css(BORDER_SUBTLE),
        "BORDER": css(BORDER),
        "ACCENT": css(ACCENT),
        "ACCENT_TEXT": css(ACCENT_TEXT),
        "ACCENT_LINK": css(ACCENT_LINK),
        "TEXT": css(TEXT),
        "KNOB_OFF": css(KNOB_OFF),
        "WASH_06": css(wash(0.06)),
        "WASH_09": css(wash(0.09)),
        "WASH_10": css(wash(0.10)),
        "WASH_12": css(wash(0.12)),
        "WASH_14": css(wash(0.14)),
        "WASH_22": css(wash(0.22)),
        "WASH_28": css(wash(0.28)),
        "WASH_30": css(wash(0.30)),
        "WASH_45": css(wash(0.45)),
        "MUTED_40": css(muted(0.40)),
        "MUTED_45": css(muted(0.45)),
        "MUTED_50": css(muted(0.50)),
        "MUTED_55": css(muted(0.55)),
        "MUTED_60": css(muted(0.60)),
        "MUTED_62": css(muted(0.62)),
        "MUTED_70": css(muted(0.70)),
        "MUTED_72": css(muted(0.72)),
        "MUTED_82": css(muted(0.82)),
        "TRANSPARENT": "transparent",
    }


def stylesheet() -> str:
    """The whole application style sheet, tokens substituted."""
    tokens = _tokens()
    parts = []
    for name in _SHEETS:
        text = resource("qss", f"{name}.qss").read_text(encoding="utf-8")
        parts.append(Template(text).substitute(tokens))
    return "\n".join(parts)
