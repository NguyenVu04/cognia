"""What a tool is, what the model asks of it, and what it gave back."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolSpec:
    """One tool as the model sees it. ``parameters`` is a JSON Schema object;
    ``working`` is what the chat says while it runs. A ``data`` tool gives
    figures, so the numbers of the reply are checked against it."""

    name: str
    description: str
    parameters: Mapping[str, object]
    working: str
    data: bool


@dataclass(frozen=True)
class ToolCall:
    """The model asks for ``name`` with ``arguments``."""

    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """What one call gave back, as the model read it."""

    name: str
    text: str


@dataclass(frozen=True)
class ToolStarted:
    """A tool began to run, so the chat can say what is happening."""

    name: str


@dataclass(frozen=True)
class ActivityStep:
    """One step of an exercise done together, as the companion shows it."""

    label: str
    seconds: int
