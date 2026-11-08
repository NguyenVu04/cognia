"""What a step asks the outside to do. The caller carries each effect out after
the step is committed, so nothing reaches the screen with no record."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.emotion.models import Expression


@dataclass(frozen=True)
class ShowExpression:
    """Show this face on the companion."""

    expression: Expression


@dataclass(frozen=True)
class ShowGesture:
    """Play this gesture once, as part of the reply to the message."""

    name: str


@dataclass(frozen=True)
class ShowAmbient:
    """Show the companion waiting, dozing or active. Ambient motion is not
    speech, so it passes no gate."""

    state: str


# Every kind of effect. A new kind joins this union.
Effect = ShowExpression | ShowGesture | ShowAmbient
