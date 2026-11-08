from datetime import datetime, timezone

from src.domain.tools.models.tool_server import HTTP, STDIO, ToolServer
from src.infrastructure.ai.mcp_tools import FAILED, McpTools, connections, tool_name

AT = datetime(2026, 11, 9, tzinfo=timezone.utc)
NOTES = ToolServer("1", "my notes", STDIO, "uvx", ("notes",), "", AT, AT)
WEB = ToolServer("2", "web", HTTP, "", (), "http://127.0.0.1:9/mcp", AT, AT)


class FakeTool:
    def __init__(self, name: str, answer=None, error: bool = False) -> None:
        self.name = name
        self.description = "Search the notes."
        self.args_schema = {"type": "object", "properties": {"q": {"type": "string"}}}
        self._answer, self._error = answer, error

    async def ainvoke(self, arguments):
        if self._error:
            raise RuntimeError("boom")
        return self._answer


class FakeClient:
    def __init__(self, tools=None, error: bool = False) -> None:
        self._tools, self._error = tools or [], error

    async def get_tools(self):
        if self._error:
            raise ConnectionError
        return self._tools


def test_tool_names_are_safe_and_namespaced() -> None:
    assert tool_name("my notes", "search.all") == "my_notes__search_all"


def test_connections_by_transport() -> None:
    found = connections([NOTES, WEB])

    assert found["my notes"] == {
        "transport": "stdio",
        "command": "uvx",
        "args": ["notes"],
    }
    assert found["web"]["transport"] == "streamable_http"


def test_specs_and_call() -> None:
    tools = McpTools(
        [NOTES], client_factory=lambda c: FakeClient([FakeTool("search", "3 notes")])
    )

    (spec,) = tools.specs()

    assert spec.name == "my_notes__search"
    assert spec.description.startswith("From the add-on my notes")
    assert tools.handles(spec.name)
    assert tools.call(spec.name, {"q": "cats"}) == "3 notes"


def test_failed_server_gives_no_tools() -> None:
    tools = McpTools([NOTES], client_factory=lambda c: FakeClient(error=True))

    assert tools.specs() == []


def test_tool_error_becomes_a_plain_sentence() -> None:
    tools = McpTools(
        [NOTES], client_factory=lambda c: FakeClient([FakeTool("x", error=True)])
    )
    (spec,) = tools.specs()

    assert tools.call(spec.name, {}) == FAILED
    assert tools.call("unknown", {}) == FAILED
