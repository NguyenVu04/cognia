"""A tiny tool server for trying add-ons by hand: one tool that repeats text.

Run it as an add-on with the command ``uv run python tests/fixtures/echo_mcp_server.py``
from ``desktop/``. It reaches nothing outside this computer.
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("echo")


@server.tool()
def echo(text: str) -> str:
    """Repeat the text back, so the add-on path can be checked."""
    return f"Echo: {text}"


if __name__ == "__main__":
    server.run()
