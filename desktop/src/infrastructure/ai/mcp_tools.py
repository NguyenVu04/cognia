"""The tools of the add-ons the user added: tool servers reached through the
Model Context Protocol.

Each server runs outside Cognia, by a command it starts or at a URL. Its tools
join a reply under the name ``<server>__<tool>``. A server that cannot be
reached gives no tools; a tool that fails gives a plain sentence.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence

from src.domain.tools.models import ToolSpec
from src.domain.tools.models.tool_server import STDIO, ToolServer

FAILED = "Could not find out: the add-on did not answer."
_SEPARATOR = "__"
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def tool_name(server: str, tool: str) -> str:
    """A name the model can call, unique across servers."""
    return f"{_SAFE.sub('_', server)}{_SEPARATOR}{_SAFE.sub('_', tool)}"[:64]


def connections(servers: Sequence[ToolServer]) -> dict[str, dict]:
    """The connection of each server, as ``langchain-mcp-adapters`` reads it."""
    result = {}
    for server in servers:
        if server.transport == STDIO:
            result[server.name] = {
                "transport": "stdio",
                "command": server.command,
                "args": list(server.args),
            }
        else:
            result[server.name] = {"transport": "streamable_http", "url": server.url}
    return result


class McpTools:
    """Lists and calls the tools of ``servers``. Runs on the model thread."""

    def __init__(
        self,
        servers: Sequence[ToolServer],
        *,
        timeout_s: float = 20,
        client_factory: Callable[[dict], object] | None = None,
    ) -> None:
        self._servers = list(servers)
        self._timeout = timeout_s
        self._factory = client_factory or _client
        self._tools: dict[str, object] = {}
        self._specs: list[ToolSpec] = []
        self._loaded = False

    def specs(self) -> list[ToolSpec]:
        """The tools of every server that answered. Loaded once."""
        if not self._loaded:
            self._loaded = True
            for server in self._servers:
                self._load(server)
        return list(self._specs)

    def handles(self, name: str) -> bool:
        return name in self._tools

    def call(self, name: str, arguments: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return FAILED
        try:
            result = asyncio.run(
                asyncio.wait_for(tool.ainvoke(arguments), self._timeout)
            )
        except Exception:  # noqa: BLE001 - an add-on can fail in any way
            return FAILED
        text = result if isinstance(result, str) else str(result)
        return text.strip() or FAILED

    def _load(self, server: ToolServer) -> None:
        try:
            client = self._factory(connections([server]))
            tools = asyncio.run(asyncio.wait_for(client.get_tools(), self._timeout))
        except Exception:  # noqa: BLE001 - a server that does not answer gives nothing
            return
        for tool in tools:
            name = tool_name(server.name, tool.name)
            self._tools[name] = tool
            schema = getattr(tool, "args_schema", None) or {}
            if not isinstance(schema, dict):
                schema = schema.model_json_schema()
            self._specs.append(
                ToolSpec(
                    name=name,
                    description=f"From the add-on {server.name}: "
                    f"{tool.description or ''}",
                    parameters=schema or {"type": "object", "properties": {}},
                    working=f"Asking {server.name}",
                    data=True,
                )
            )


def _client(connection: dict) -> object:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    return MultiServerMCPClient(connection)
