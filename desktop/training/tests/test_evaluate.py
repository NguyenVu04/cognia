import csv
import json
from dataclasses import asdict, replace

import pytest

from training import evaluate
from training.evaluate import Labelled, Reply, Report, Thresholds

BASE = Report(
    class_accuracy=0.7,
    crisis_recall=0.8,
    importance_error=2.0,
    complies_share=0.8,
    rubric_mean=3.0,
    first_word_p95=2.0,
    file_bytes=100,
)
TUNED = replace(BASE, class_accuracy=0.8, crisis_recall=0.9, rubric_mean=4.0)
LIMITS = Thresholds(
    class_accuracy=0.75,
    crisis_recall=0.85,
    complies_share=0.8,
    rubric_margin=0.5,
    first_word_p95=3.0,
    file_bytes=200,
)


def answer(event_class: str, importance: int = 5, crisis: bool = False) -> dict:
    return {"event_class": event_class, "importance": importance, "crisis": crisis}


def label(event_class: str, importance: int = 5, crisis: bool = False) -> Labelled:
    return Labelled(event_class, importance, crisis)


def scored_sheet(tmp_path, scores: dict[str, str]):
    """A sheet for two models, with each row given the score of its model."""
    path = tmp_path / "sheet.csv"
    evaluate.write_rubric_sheet({"tuned": ["a"], "base": ["b"]}, path, seed=1)
    with evaluate._key_path(path).open(newline="", encoding="utf-8") as key:
        models = {row["id"]: row["model"] for row in csv.DictReader(key)}
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        for criterion in evaluate.RUBRIC_CRITERIA:
            row[criterion] = scores[models[row["id"]]]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_collect_passes_the_schema() -> None:
    seen = []

    def generate(messages, schema) -> Reply:
        seen.append(schema)
        return Reply("text", 1.0)

    replies = evaluate.collect(generate, [[], []], {"type": "object"})

    assert replies == [Reply("text", 1.0)] * 2
    assert seen == [{"type": "object"}] * 2


def test_score_counts_correct_classes() -> None:
    labels = [label("a"), label("a"), label("a"), label("x", crisis=True)]
    answers = [answer("a"), answer("a"), answer("a"), answer("y", crisis=True)]

    assert evaluate.score_interpretation(answers, labels)["class_accuracy"] == 0.75


def test_score_crisis_recall_counts_only_crisis_labels() -> None:
    labels = [label("a", crisis=True), label("a", crisis=True), label("a")]
    answers = [answer("a", crisis=True), answer("a"), answer("a", crisis=True)]

    assert evaluate.score_interpretation(answers, labels)["crisis_recall"] == 0.5


def test_score_crisis_recall_without_crisis_labels_raises() -> None:
    with pytest.raises(ValueError):
        evaluate.score_interpretation([answer("a")], [label("a")])


def test_score_importance_error_is_mean_absolute() -> None:
    labels = [label("a", 5, crisis=True), label("a", 5)]
    answers = [answer("a", 6), answer("a", 2)]

    assert evaluate.score_interpretation(answers, labels)["importance_error"] == 2.0


def test_score_refuses_length_mismatch() -> None:
    with pytest.raises(ValueError):
        evaluate.score_interpretation([answer("a")] * 3, [label("a")] * 4)


def test_share_complying_uses_the_given_check() -> None:
    assert evaluate.share_complying(["yes", "no"], lambda text: text == "yes") == 0.5


def test_share_complying_empty_raises() -> None:
    with pytest.raises(ValueError):
        evaluate.share_complying([], bool)


def test_percentile_of_one_value() -> None:
    assert evaluate.percentile([2.0], 0.95) == 2.0


def test_percentile_is_nearest_rank() -> None:
    assert evaluate.percentile([float(n) for n in range(1, 21)], 0.95) == 19.0


def test_rubric_sheet_hides_the_model(tmp_path) -> None:
    path = tmp_path / "sheet.csv"

    evaluate.write_rubric_sheet({"tuned-model": ["a"], "base-model": ["b"]}, path, 1)

    assert "model" not in path.read_text("utf-8")


def test_rubric_sheet_is_stable_for_one_seed(tmp_path) -> None:
    samples = {"tuned": list("abcdef"), "base": list("ghijkl")}
    one, two = tmp_path / "one.csv", tmp_path / "two.csv"

    evaluate.write_rubric_sheet(samples, one, seed=3)
    evaluate.write_rubric_sheet(samples, two, seed=3)

    assert one.read_text("utf-8") == two.read_text("utf-8")


def test_read_rubric_sheet_means_per_model(tmp_path) -> None:
    path = scored_sheet(tmp_path, {"tuned": "4", "base": "2"})

    assert evaluate.read_rubric_sheet(path) == {"tuned": 4.0, "base": 2.0}


def test_read_rubric_sheet_refuses_score_outside_range(tmp_path) -> None:
    path = scored_sheet(tmp_path, {"tuned": "6", "base": "2"})

    with pytest.raises(ValueError):
        evaluate.read_rubric_sheet(path)


def test_read_rubric_sheet_refuses_blank_score(tmp_path) -> None:
    path = scored_sheet(tmp_path, {"tuned": "", "base": "2"})

    with pytest.raises(ValueError):
        evaluate.read_rubric_sheet(path)


def test_gates_pass_when_all_met() -> None:
    assert evaluate.accepted(TUNED, BASE, LIMITS)


def test_gates_fail_on_crisis_recall_alone() -> None:
    tuned = replace(TUNED, crisis_recall=0.84)

    results = evaluate.gates(tuned, BASE, LIMITS)

    assert not evaluate.accepted(tuned, BASE, LIMITS)
    assert [gate.name for gate in results if not gate.passed] == ["interpretation"]


def test_gates_fail_when_tuned_does_not_beat_base() -> None:
    limits = replace(LIMITS, rubric_margin=0.0)

    assert not evaluate.accepted(replace(TUNED, rubric_mean=3.0), BASE, limits)


def test_gates_fail_when_interpretation_falls_below_base() -> None:
    base = replace(BASE, class_accuracy=0.9)

    assert not evaluate.accepted(TUNED, base, LIMITS)


def test_gates_fail_on_file_size() -> None:
    assert not evaluate.accepted(replace(TUNED, file_bytes=201), BASE, LIMITS)


def test_gate_exactly_at_threshold_passes() -> None:
    tuned = replace(
        TUNED,
        class_accuracy=0.75,
        crisis_recall=0.85,
        first_word_p95=3.0,
        file_bytes=200,
    )

    assert evaluate.accepted(tuned, BASE, LIMITS)


def test_write_report_lists_every_gate(tmp_path) -> None:
    path = tmp_path / "report.md"

    evaluate.write_report(path, evaluate.gates(TUNED, BASE, LIMITS), TUNED, BASE)

    text = path.read_text("utf-8")
    assert all(name in text for name in ("voice", "interpretation", "safety", "cost"))


def test_main_gate_returns_one_for_a_refused_model(tmp_path) -> None:
    files = {
        "tuned": asdict(replace(TUNED, file_bytes=201)),
        "base": asdict(BASE),
        "limits": asdict(LIMITS),
    }
    paths = []
    for name, content in files.items():
        paths.append(tmp_path / f"{name}.json")
        paths[-1].write_text(json.dumps(content), "utf-8")

    code = evaluate.main(["gate", *map(str, paths), str(tmp_path / "report.md")])

    assert code == 1
