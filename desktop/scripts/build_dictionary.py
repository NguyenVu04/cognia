"""Build the read-only dictionary of ``define_word`` from Open English WordNet.

Reads a WN-LMF release (``english-wordnet-<year>.xml`` or ``.xml.gz``) and
writes one SQLite file that holds, for each word and part of speech, its first
definitions in WordNet's order. Nothing else of WordNet is kept, so the file
stays small enough to ship.

    uv run python scripts/build_dictionary.py <release.xml.gz> <target.sqlite3>
"""

from __future__ import annotations

import gzip
import sqlite3
import sys
import xml.etree.ElementTree as ElementTree
from datetime import date
from pathlib import Path

# The senses kept for each word and part of speech, most common first.
SENSES_PER_PART = 3
PARTS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective",
         "r": "adverb"}

_SCHEMA = (
    "CREATE TABLE senses (lemma TEXT NOT NULL, pos TEXT NOT NULL, "
    "rank INTEGER NOT NULL, definition TEXT NOT NULL, "
    "PRIMARY KEY (lemma, pos, rank)) STRICT, WITHOUT ROWID",
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
)


def read(source: Path) -> tuple[str, list[tuple[str, str, list[str]]], dict[str, str]]:
    """The release's version, each entry as (lemma, part of speech, its synsets
    in order), and the definition of each synset."""
    opener = gzip.open if source.suffix == ".gz" else open
    version = ""
    entries: list[tuple[str, str, list[str]]] = []
    definitions: dict[str, str] = {}
    with opener(source, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            tag = element.tag
            if tag == "Lexicon":
                version = element.get("version", "")
            elif tag == "LexicalEntry":
                lemma = element.find("Lemma")
                if lemma is not None:
                    synsets = [s.get("synset") for s in element.iter("Sense")]
                    entries.append(
                        (
                            lemma.get("writtenForm", ""),
                            lemma.get("partOfSpeech", ""),
                            [s for s in synsets if s],
                        )
                    )
                element.clear()
            elif tag == "Synset":
                definition = element.find("Definition")
                if definition is not None and definition.text:
                    definitions[element.get("id", "")] = " ".join(
                        definition.text.split()
                    )
                element.clear()
    return version, entries, definitions


def rows(
    entries: list[tuple[str, str, list[str]]], definitions: dict[str, str]
) -> list[tuple[str, str, int, str]]:
    """One row for each kept sense: the word in lower case, the part of speech
    in words, its rank from 1, and its definition. Two parts of speech that
    read the same, such as the two kinds of adjective, share their ranks."""
    kept: dict[tuple[str, str], list[str]] = {}
    for lemma, part, synsets in entries:
        key = (lemma.casefold(), PARTS.get(part, ""))
        if not key[0] or not key[1]:
            continue
        found = kept.setdefault(key, [])
        for synset in synsets:
            text = definitions.get(synset)
            if text and text not in found and len(found) < SENSES_PER_PART:
                found.append(text)
    return [
        (lemma, part, rank, text)
        for (lemma, part), texts in sorted(kept.items())
        for rank, text in enumerate(texts, start=1)
    ]


def write(target: Path, version: str, kept: list[tuple[str, str, int, str]]) -> None:
    target.unlink(missing_ok=True)
    connection = sqlite3.connect(target)
    try:
        for statement in _SCHEMA:
            connection.execute(statement)
        connection.executemany("INSERT INTO senses VALUES (?, ?, ?, ?)", kept)
        connection.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [
                ("source", "Open English WordNet"),
                ("version", version),
                ("built", date.today().isoformat()),
            ],
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()


def main(source: Path, target: Path) -> int:
    version, entries, definitions = read(source)
    kept = rows(entries, definitions)
    write(target, version, kept)
    print(f"{len(kept)} senses of version {version} in {target.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
