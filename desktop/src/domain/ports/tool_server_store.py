"""The port that keeps the tool servers the user added."""

from __future__ import annotations

from typing import Protocol

from src.domain.tools.models.tool_server import ToolServer


class ToolServerStoreFailed(Exception):
    """A tool server could not be read or written. Carries user-facing text."""


class ToolServerStore(Protocol):
    """Each method raises :class:`ToolServerStoreFailed` if it cannot do its work."""

    def add(self, server: ToolServer) -> None:
        ...

    def all(self) -> list[ToolServer]:
        ...

    def remove(self, server_id: str) -> None:
        ...
