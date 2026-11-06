"""Which remembered lines a reply draws on, and which new lines are kept.

Pure functions: the time and every vector arrive as arguments. The figures are
start values; trial use sets the real ones.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, tzinfo

from src.domain.conversation.models import Interpretation
from src.domain.conversation.rules import MONTHS
from src.domain.memory.models import Calibration, MemoryItem, Scored, Vector

# Recency falls by this factor for each hour since the line was last used. A
# line unused for weeks is forgotten in conversation, by design; it stays on the
# memory page.
RECENCY_PER_HOUR = 0.995
# A line under this score stays out of the reply.
SCORE_FLOOR = 0.05
# Lines in the reply prompt. More of them make a small model drift off topic.
RECALL_LIMIT = 3
# Lines in the interpretation prompt, so the model does not extract them again.
# Chosen by similarity only: a line that recall has forgotten still counts.
KNOWN_LIMIT = 5
# A stored line is short; a longer one is a paragraph, not a fact.
LINE_LIMIT = 200
# New facts kept from one message.
PER_MESSAGE = 3

_EDGES = " .!?;:,\"'“”‘’"


def tidy(text: str) -> str:
    """The line as it is stored: runs of whitespace become one space."""
    return " ".join(text.split())


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """0.0 when either vector is all zeros. Raises ``ValueError`` when the
    lengths differ, because then the two came from different models."""
    if len(a) != len(b):
        raise ValueError(f"vectors of {len(a)} and {len(b)} numbers")
    norms = math.sqrt(math.sumprod(a, a)) * math.sqrt(math.sumprod(b, b))
    return math.sumprod(a, b) / norms if norms else 0.0


def relevance(similarity: float, baseline: float) -> float:
    """The cosine above what two unrelated lines reach, from 0 to 1."""
    return max(0.0, (similarity - baseline) / (1 - baseline))


def score(
    entry: MemoryItem,
    query: Vector | None,
    now: datetime,
    calibration: Calibration,
) -> float:
    """recency × importance × relevance, each from 0 to 1.

    With no query vector, the relevance factor is left out. An entry that waits
    for its vector scores 0 while a query vector exists. An entry with no
    importance counts as importance 1.
    """
    since = entry.last_retrieved_at or entry.recorded_at
    hours = max(0.0, (now - since).total_seconds() / 3600)
    value = RECENCY_PER_HOUR**hours * (entry.importance or 1) / 10
    if query is None:
        return value
    if entry.embedding is None:
        return 0.0
    return value * relevance(cosine(query, entry.embedding), calibration.baseline)


def recall(
    entries: Sequence[MemoryItem],
    query: Vector | None,
    now: datetime,
    calibration: Calibration,
) -> tuple[Scored, ...]:
    """The lines a reply draws on: at most ``RECALL_LIMIT``, best first, none
    under ``SCORE_FLOOR``. Equal scores put the newer line first, then the
    lower id, so the order never depends on the input order."""
    scored = [Scored(e, score(e, query, now, calibration)) for e in entries]
    kept = [s for s in scored if s.score >= SCORE_FLOOR]
    kept.sort(
        key=lambda s: (-s.score, -s.entry.recorded_at.timestamp(), s.entry.id)
    )
    return tuple(kept[:RECALL_LIMIT])


def known(
    entries: Sequence[MemoryItem], query: Vector | None, limit: int = KNOWN_LIMIT
) -> tuple[MemoryItem, ...]:
    """The stored lines closest to the query. With no query vector, the newest."""
    if query is None:
        newest = sorted(entries, key=lambda e: (-e.recorded_at.timestamp(), e.id))
        return tuple(newest[:limit])
    with_vectors = [e for e in entries if e.embedding is not None]
    nearest = sorted(
        with_vectors, key=lambda e: (-cosine(query, e.embedding), e.id)
    )
    return tuple(nearest[:limit])


def select(
    found: Interpretation,
    existing: Sequence[MemoryItem],
    vectors: Mapping[str, Vector],
    calibration: Calibration,
) -> tuple[str, ...]:
    """The new lines worth keeping.

    A line is left out if it is blank, longer than ``LINE_LIMIT``, the same as
    a stored or an earlier new line apart from case and edge punctuation, or at
    least ``near_duplicate`` similar to one of them. ``vectors`` holds the
    vector of each new line by its tidied text; a line with no vector skips the
    similarity check. Two lines that disagree are both kept.
    """
    seen = {_key(entry.text) for entry in existing}
    kept_vectors = [e.embedding for e in existing if e.embedding is not None]

    def fresh(line: str) -> bool:
        if not line or len(line) > LINE_LIMIT or _key(line) in seen:
            return False
        vector = vectors.get(line)
        if vector is not None and any(
            cosine(vector, other) >= calibration.near_duplicate
            for other in kept_vectors
        ):
            return False
        seen.add(_key(line))
        if vector is not None:
            kept_vectors.append(vector)
        return True

    facts: list[str] = []
    for line in map(tidy, found.facts):
        if len(facts) < PER_MESSAGE and fresh(line):
            facts.append(line)
    return tuple(facts)


def recalled_line(entry: MemoryItem, zone: tzinfo) -> str:
    """The line as the reply prompt shows it, with the local day it was told, so
    the model can let a newer line win."""
    told = f"told {_day_text(entry.recorded_at.astimezone(zone).date())}"
    return f"{entry.text} ({told})"


def shows_back(reply: str, line: str) -> bool:
    """Whether the reply quotes the stored line, apart from case, spacing and
    the punctuation at its ends."""
    return _key(line) in _flat(reply)


def stored_note(missing: Sequence[str], day: date) -> str:
    """The chip under the reply. It carries each stored line that the reply did
    not quote, so the user always sees the exact words."""
    when = f"{day.day} {MONTHS[day.month - 1][:3]}"
    if not missing:
        return f"Stored — you told me · {when}"
    lines = " · ".join(f"“{line}”" for line in missing)
    return f"Stored — you told me: {lines} · {when}"


def _flat(text: str) -> str:
    return " ".join(text.casefold().replace("’", "'").split())


def _key(text: str) -> str:
    return _flat(text).strip(_EDGES)


def _day_text(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"
