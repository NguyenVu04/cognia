"""A tool server the user added, which runs outside Cognia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

STDIO = "stdio"
HTTP = "http"


@dataclass(frozen=True)
class ToolServer:
    """A server reached by a command it starts (``stdio``) or by a URL
    (``http``). ``consented_at`` is when the user agreed that it may send data
    off the machine.

    Raises ``ValueError`` for a server that cannot be reached.
    """

    id: str
    name: str
    transport: str
    command: str
    args: tuple[str, ...]
    url: str
    added_at: datetime
    consented_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A tool server needs a name.")
        if self.transport == STDIO and not self.command.strip():
            raise ValueError("A tool server that runs a command needs the command.")
        if self.transport == HTTP and not self.url.startswith(("http://", "https://")):
            raise ValueError("A tool server on the network needs an http or https URL.")
        if self.transport not in (STDIO, HTTP):
            raise ValueError(f"transport must be stdio or http, not {self.transport!r}")
