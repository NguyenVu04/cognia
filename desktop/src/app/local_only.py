"""Switched off before anything gets the chance to switch it on.

NFR-01 promises zero outbound connections the user did not ask for, and C-02
says there is no account and no server. LangChain does not breach that on its
own, but it ships with hosted tracing that turns itself on from an environment
variable — and ``langsmith`` is a hard dependency of ``langchain-core``, so it
is installed whether or not anything imports it.

Leaving that to chance would make the promise depend on the machine Cognia
happens to be running on. Setting the variables outright, before the first
LangChain import reads them, makes it a property of the program instead.

This module does its work on import and exports nothing. It must be imported
before anything under ``src/infrastructure/ai/``.
"""

from __future__ import annotations

import os

#: Every switch LangChain reads to decide whether to send traces anywhere.
_TRACING = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_OTEL_ENABLED",
)

for _switch in _TRACING:
    os.environ[_switch] = "false"
