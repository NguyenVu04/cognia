import gzip
import sqlite3
from pathlib import Path

from scripts import build_dictionary

LMF = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource>
  <Lexicon id="oewn" label="Open English Wordnet" language="en" version="2025">
    <LexicalEntry id="e1">
      <Lemma writtenForm="Bank" partOfSpeech="n"/>
      <Sense id="s1" synset="y1"/>
      <Sense id="s2" synset="y2"/>
      <Sense id="s3" synset="y3"/>
      <Sense id="s4" synset="y4"/>
    </LexicalEntry>
    <LexicalEntry id="e2">
      <Lemma writtenForm="bank" partOfSpeech="v"/>
      <Sense id="s5" synset="y5"/>
    </LexicalEntry>
    <LexicalEntry id="e3">
      <Lemma writtenForm="able" partOfSpeech="s"/>
      <Sense id="s6" synset="y6"/>
    </LexicalEntry>
    <Synset id="y1" partOfSpeech="n"><Definition>sloping land</Definition></Synset>
    <Synset id="y2" partOfSpeech="n">
      <Definition>a financial  institution</Definition>
    </Synset>
    <Synset id="y3" partOfSpeech="n"><Definition>a long ridge</Definition></Synset>
    <Synset id="y4" partOfSpeech="n"><Definition>a fourth meaning</Definition></Synset>
    <Synset id="y5" partOfSpeech="v"><Definition>tip laterally</Definition></Synset>
    <Synset id="y6" partOfSpeech="s"><Definition>having the means</Definition></Synset>
  </Lexicon>
</LexicalResource>
"""


def build(tmp_path: Path, packed: bool) -> list[tuple]:
    source = tmp_path / ("release.xml.gz" if packed else "release.xml")
    if packed:
        source.write_bytes(gzip.compress(LMF.encode("utf-8")))
    else:
        source.write_text(LMF, encoding="utf-8")
    target = tmp_path / "oewn.sqlite3"

    assert build_dictionary.main(source, target) == 0

    connection = sqlite3.connect(target)
    found = connection.execute(
        "SELECT lemma, pos, rank, definition FROM senses ORDER BY lemma, pos, rank"
    ).fetchall()
    meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    connection.close()
    assert meta["version"] == "2025"
    return found


def test_keeps_three_senses_per_part_in_order(tmp_path: Path) -> None:
    found = build(tmp_path, packed=True)

    assert found == [
        ("able", "adjective", 1, "having the means"),
        ("bank", "noun", 1, "sloping land"),
        ("bank", "noun", 2, "a financial institution"),
        ("bank", "noun", 3, "a long ridge"),
        ("bank", "verb", 1, "tip laterally"),
    ]


def test_reads_plain_xml(tmp_path: Path) -> None:
    assert len(build(tmp_path, packed=False)) == 5
