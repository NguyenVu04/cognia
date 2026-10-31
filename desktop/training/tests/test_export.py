from datetime import date

import pytest

from training import export


def test_write_licences_copies_licence_text(tmp_path) -> None:
    source = tmp_path / "LICENSE"
    source.write_text("Licence words", "utf-8")

    export.write_licences(tmp_path / "out", source, "base/model", date(2026, 10, 31))

    assert (tmp_path / "out" / "LICENSE.txt").read_text("utf-8") == "Licence words"


def test_write_licences_states_weights_are_modified(tmp_path) -> None:
    source = tmp_path / "LICENSE"
    source.write_text("Licence words", "utf-8")

    export.write_licences(tmp_path / "out", source, "base/model", date(2026, 10, 31))

    notice = (tmp_path / "out" / "NOTICE.txt").read_text("utf-8")
    assert "modified weights" in notice
    assert "base/model" in notice
    assert "2026-10-31" in notice


def test_write_licences_refuses_missing_source(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        export.write_licences(
            tmp_path, tmp_path / "missing", "base/model", date(2026, 10, 31)
        )


def test_name_chat_file_ignores_the_vision_projector(tmp_path) -> None:
    (tmp_path / "model-Q4_K_M.gguf").write_text("model", "utf-8")
    (tmp_path / "mmproj-F16.gguf").write_text("vision", "utf-8")

    chat_file = export._name_chat_file(tmp_path)

    assert chat_file == tmp_path / "chat.gguf"
    assert chat_file.read_text("utf-8") == "model"


def test_name_chat_file_refuses_two_models(tmp_path) -> None:
    (tmp_path / "one.gguf").write_text("model", "utf-8")
    (tmp_path / "two.gguf").write_text("model", "utf-8")

    with pytest.raises(ValueError):
        export._name_chat_file(tmp_path)
