"""Cutting a reply into sentences as it streams, so the voice can begin before
the reply ends."""

from __future__ import annotations

import re

# An end of sentence, then a space. "Dr." and "e.g." are not ends.
_END = re.compile(
    r"(?<!\bDr)(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\be\.g)(?<!\bi\.e)([.!?…]+[\"”’)]*)\s+"
)


def split_ready(buffer: str) -> tuple[list[str], str]:
    """The finished sentences at the start of ``buffer``, and the rest."""
    sentences: list[str] = []
    start = 0
    for match in _END.finditer(buffer):
        sentence = buffer[start : match.end(1)].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    return sentences, buffer[start:]
