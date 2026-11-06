import sqlite3
from pathlib import Path

import pytest

from src.domain.ports import DictionaryUnavailable, Sense
from src.infrastructure.storage.dictionary import UNAVAILABLE, SqliteDictionary
from src.utils import paths


@pytest.fixture
def small(tmp_path: Path) -> Path:
    path = tmp_path / "words.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE senses (lemma TEXT, pos TEXT, rank INTEGER, definition TEXT)"
    )
    connection.executemany(
        "INSERT INTO senses VALUES (?, ?, ?, ?)",
        [("bank", "verb", 1, "tip laterally"), ("bank", "noun", 2, "a bank"),
         ("bank", "noun", 1, "sloping land")],
    )
    connection.commit()
    connection.close()
    return path


def test_senses_in_order(small: Path) -> None:
    assert SqliteDictionary(small).senses(" Bank ") == [
        Sense("noun", "sloping land"), Sense("noun", "a bank"),
        Sense("verb", "tip laterally"),
    ]


def test_unknown_word_is_empty(small: Path) -> None:
    assert SqliteDictionary(small).senses("zyxq") == []


def test_dictionary_read_only(small: Path) -> None:
    dictionary = SqliteDictionary(small)
    dictionary.senses("bank")

    with pytest.raises(sqlite3.OperationalError):
        dictionary._open().execute("DELETE FROM senses")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DictionaryUnavailable, match=UNAVAILABLE):
        SqliteDictionary(tmp_path / "none.sqlite3").senses("bank")


def test_shipped_dictionary_knows_a_word() -> None:
    shipped = SqliteDictionary(paths.resource("dictionary", "oewn.sqlite3"))

    assert shipped.senses("serendipity")[0].pos == "noun"
