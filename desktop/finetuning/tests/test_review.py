import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from finetuning.examples import write_examples
from finetuning.review import (
    Decision,
    Rating,
    Review,
    ReviewError,
    accepted,
    apply,
    decisions,
    make_server,
    record,
)

from .factories import interpretation, voice


def data(tmp_path: Path) -> Path:
    write_examples(tmp_path / "train" / "a.jsonl", [voice(), interpretation()])
    write_examples(
        tmp_path / "test" / "a.jsonl",
        [voice(id="t1", message="Other.", expect={"asks_mood": False})],
    )
    return tmp_path


def test_latest_decision_wins(tmp_path: Path) -> None:
    path = tmp_path / "review.jsonl"
    record(path, Decision("voice-1", "accepted", "t1"))
    record(path, Decision("voice-1", "rejected", "t2"))

    assert decisions(path)["voice-1"].status == "rejected"


def test_decisions_of_missing_file(tmp_path: Path) -> None:
    assert decisions(tmp_path / "none.jsonl") == {}


def test_apply_edit_replaces_target() -> None:
    edited = apply(voice(), Decision("voice-1", "accepted", "t", target="Hmph."))

    assert edited.target == "Hmph."
    assert edited.reasoning == voice().reasoning


def test_accepted_keeps_only_accepted() -> None:
    found = {
        "voice-1": Decision("voice-1", "accepted", "t"),
        "voice-2": Decision("voice-2", "rejected", "t"),
    }

    kept = accepted([voice(), voice(id="voice-2"), voice(id="voice-3")], found)

    assert [e.id for e in kept] == ["voice-1"]


def test_detail_has_prompt_answer_warnings(tmp_path: Path) -> None:
    review = Review(data(tmp_path))
    review.decide({"id": "voice-1", "status": "rejected", "target": "*blushes* thanks"})

    shown = review.detail("voice-1")

    assert shown["messages"][0]["role"] == "system"
    assert shown["answer"][0]["content"] == "*blushes* thanks"
    assert "stage_direction" in shown["warnings"]
    assert shown["status"] == "rejected"


def test_detail_unknown_id(tmp_path: Path) -> None:
    with pytest.raises(ReviewError):
        Review(data(tmp_path)).detail("nope")


def test_decide_refuses_errors(tmp_path: Path) -> None:
    review = Review(data(tmp_path))

    with pytest.raises(ReviewError, match="Not accepted"):
        review.decide({"id": "voice-1", "status": "accepted", "target": ""})


def test_decide_refuses_unknown_status(tmp_path: Path) -> None:
    with pytest.raises(ReviewError):
        Review(data(tmp_path)).decide({"id": "voice-1", "status": "maybe"})


def test_decide_reads_interpretation_json(tmp_path: Path) -> None:
    review = Review(data(tmp_path))
    target = dict(interpretation().target, importance=2)

    review.decide(
        {"id": "interp-1", "status": "accepted", "target": json.dumps(target)}
    )

    assert decisions(tmp_path / "review.jsonl")["interp-1"].target == target


def test_decide_bad_json(tmp_path: Path) -> None:
    with pytest.raises(ReviewError, match="not JSON"):
        Review(data(tmp_path)).decide(
            {"id": "interp-1", "status": "accepted", "target": "{nope"}
        )


def test_listing_filters_and_progress(tmp_path: Path) -> None:
    review = Review(data(tmp_path))
    review.decide({"id": "voice-1", "status": "rejected"})

    listed = review.listing({"part": "train", "status": "pending"})

    assert [r["id"] for r in listed["examples"]] == ["interp-1"]
    assert listed["progress"]["train/voice"] == [1, 1]
    assert listed["progress"]["test/voice"] == [0, 1]


def serve(**parts):
    server = make_server(**parts)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def stop(server) -> None:
    server.shutdown()
    server.server_close()


def post(url: str, body: dict) -> dict:
    request = Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urlopen(request) as response:
        return json.loads(response.read())


def test_server_binds_localhost_only(tmp_path: Path) -> None:
    server = make_server(review=Review(data(tmp_path)))
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_post_decision_appends_line(tmp_path: Path) -> None:
    server, url = serve(review=Review(data(tmp_path)))
    try:
        shown = post(
            f"{url}/api/decision",
            {"id": "voice-1", "status": "accepted", "target": "Hmph. Nice."},
        )
    finally:
        stop(server)

    assert shown["status"] == "accepted"
    lines = (tmp_path / "review.jsonl").read_text("utf-8").splitlines()
    assert len(lines) == 1


def test_post_unknown_id_is_400(tmp_path: Path) -> None:
    server, url = serve(review=Review(data(tmp_path)))
    try:
        with pytest.raises(HTTPError) as caught:
            post(f"{url}/api/decision", {"id": "nope", "status": "accepted"})
    finally:
        stop(server)

    assert caught.value.code == 400


def test_page_is_served(tmp_path: Path) -> None:
    server, url = serve(review=Review(data(tmp_path)))
    try:
        with urlopen(url + "/") as response:
            page = response.read().decode()
    finally:
        stop(server)

    assert 'const MODE = "review"' in page


def results(folder: Path, replies: dict[str, str]) -> None:
    folder.mkdir(parents=True)
    lines = [
        json.dumps({"id": i, "job": "voice", "reply": r, "context": {"message": i}})
        for i, r in replies.items()
    ]
    (folder / "results.jsonl").write_text("\n".join(lines) + "\n", "utf-8")


def test_rate_blind_order_hides_names(tmp_path: Path) -> None:
    results(tmp_path / "base", {"a": "base-a", "b": "base-b"})
    results(tmp_path / "tuned", {"a": "tuned-a", "c": "tuned-c"})

    listed = Rating(tmp_path, "base", "tuned").listing()

    assert [p["id"] for p in listed["pairs"]] == ["a"]
    assert sorted(listed["pairs"][0]["replies"]) == ["base-a", "tuned-a"]
    assert "names" not in listed["pairs"][0]


def test_rate_records_names(tmp_path: Path) -> None:
    results(tmp_path / "base", {"a": "base-a"})
    results(tmp_path / "tuned", {"a": "tuned-a"})
    rating = Rating(tmp_path, "base", "tuned")
    tuned_at = rating.listing()["pairs"][0]["replies"].index("tuned-a")

    rating.rate(
        {
            "id": "a",
            "better": tuned_at,
            "scores": [{"character": 4, "feeling": 5}, {"character": 2, "feeling": 3}],
        }
    )

    row = json.loads((tmp_path / "ratings-base-tuned.jsonl").read_text("utf-8"))
    assert row["better"] == "tuned"
    assert set(row["scores"]) == {"base", "tuned"}
    assert rating.listing()["pairs"][0]["rated"] is True


def test_rate_refuses_bad_score(tmp_path: Path) -> None:
    results(tmp_path / "base", {"a": "x"})
    results(tmp_path / "tuned", {"a": "y"})

    with pytest.raises(ReviewError):
        Rating(tmp_path, "base", "tuned").rate(
            {
                "id": "a",
                "better": 0,
                "scores": [{"character": 9, "feeling": 1},
                           {"character": 1, "feeling": 1}],
            }
        )
