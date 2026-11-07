import json
from datetime import date

from finetuning import render
from finetuning.examples import Remembered, ToolUse, Turn
from src.domain.conversation import rules as conversation_rules
from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog
from src.infrastructure.ai import tool_loop
from src.infrastructure.ai.llama_client import messages

from .factories import interpretation, summary, tools, voice


def test_render_matches_client_messages() -> None:
    example = voice()
    at = render.now_of(example)
    history = [
        Message("a", "c", USER, "Hey.", at),
        Message("b", "c", COMPANION, "Hmph. You're back.", at),
        Message("d", "c", USER, "I passed my driving test!", at),
    ]
    expected = messages(
        render.system_prompt("rin"), history, render.layer_4(example)
    )

    assert render.request(example).messages == expected


def test_system_prompt_is_layers_and_reasoning_rule() -> None:
    text = render.system_prompt("yuna")

    assert text.startswith(conversation_rules.LAYER_1)
    assert text.endswith(conversation_rules.REASONING_RULE)
    assert "You are Yuna" in text


def test_tool_schemas_match_tool_loop() -> None:
    expected = [tool_loop._schema(spec) for spec in catalog.SPECS]

    assert render.tool_schemas() == expected


def test_reply_offers_tools() -> None:
    assert len(render.request(voice()).tools) == len(catalog.SPECS)


def test_voice_crisis_has_instruction_no_mood_no_tools() -> None:
    example = voice(crisis=True, mood="pleased")

    built = render.request(example)
    last = built.messages[-1]["content"]

    assert safety_rules.instruction() in last
    assert "Your mood" not in last
    assert built.tools == []


def test_remembered_line_has_told_date() -> None:
    example = voice(remembered=(Remembered("Has a cat", date(2026, 11, 6)),))

    assert "- Has a cat (told 6 November 2026)" in render.layer_4(example)


def test_stored_lines_ask_to_quote() -> None:
    example = voice(stored=("Is learning to drive",))

    assert "“Is learning to drive”" in render.layer_4(example)


def test_interpretation_schema_attached() -> None:
    built = render.request(interpretation())

    assert built.schema is conversation_rules.INTERPRETATION_SCHEMA
    assert built.tools == []
    assert "answer only with JSON" in built.messages[-1]["content"]


def test_interpretation_answer_in_schema_order() -> None:
    [said] = render.answer(interpretation())

    assert list(json.loads(said["content"])) == list(
        conversation_rules.INTERPRETATION_SCHEMA["properties"]
    )
    assert said["reasoning_content"] == "A lasting fact about their work."


def test_summary_uses_summary_system() -> None:
    built = render.request(summary())

    assert built.messages[0]["content"] == conversation_rules.SUMMARY_SYSTEM
    assert built.messages[1]["content"].startswith("Messages:\nUser: I walked")


def test_voice_answer_has_reasoning() -> None:
    assert render.answer(voice()) == [
        {
            "role": "assistant",
            "content": "Ehh? You actually passed? ...Not bad. Not bad at all.",
            "reasoning_content": "Good news. Tease, then be glad.",
        }
    ]


def test_tools_result_from_app_rule() -> None:
    said = render.answer(tools())

    assert said[0]["tool_calls"][0]["function"]["name"] == "calculate"
    assert said[1] == {
        "role": "tool", "tool_call_id": "call0", "name": "calculate",
        "content": "12*7 = 84",
    }
    assert said[2]["content"] == "It's 84! Ooh, that was a quick one."


def test_tools_without_calls_answer_directly() -> None:
    said = render.answer(tools(calls=()))

    assert len(said) == 1


def test_open_needs_user_words() -> None:
    at = render.now_of(tools())

    refused = render.tool_result("open_in_browser", {"search": "cats"}, {}, "cats?", at)
    opened = render.tool_result(
        "open_in_browser", {"search": "cats"}, {}, "Search for cats", at
    )

    assert refused.startswith("Not opened")
    assert opened == "Opened a search for 'cats' in the user's browser."


def test_desk_time_from_data() -> None:
    at = render.now_of(tools())

    text = render.tool_result(
        "desk_time", {}, {"today_minutes": 165, "since_break_minutes": 40}, "", at
    )

    assert text == "At the machine today: 2 h 45 min. Since the last break: 40 min."


def test_desk_time_awareness_off() -> None:
    text = render.tool_result("desk_time", {}, {"awareness": False}, "", render.now_of(
        tools()))

    assert text == "Desk awareness is off, so time at the machine is not known."


def test_recall_from_data() -> None:
    text = render.tool_result(
        "recall_memory", {"query": "cat"},
        {"found": [{"text": "Has a cat", "told": "2026-11-01"}]}, "",
        render.now_of(tools()),
    )

    assert text == "Stored lines: Has a cat (told 1 November 2026)"


def test_why_i_feel_names_the_event() -> None:
    text = render.tool_result(
        "why_i_feel", {},
        {"character": "rin", "events": [{"class": "praise", "minutes_ago": 30}]},
        "", render.now_of(tools()),
    )

    assert "praise" in text
    assert text.startswith("Feeling now:")


def test_define_reads_given_senses() -> None:
    text = render.tool_result(
        "define_word", {"word": "brisk"},
        {"senses": [{"pos": "adjective", "definition": "quick and active"}]}, "",
        render.now_of(tools()),
    )

    assert text == "brisk (adjective): quick and active"


def test_exercise_already_running() -> None:
    at = render.now_of(tools())

    assert render.tool_result("breathing", {}, {}, "", at).startswith("Started")
    assert render.tool_result("stretch", {}, {"running": True}, "", at).startswith(
        "Not started"
    )


def test_unknown_tool_fails_softly() -> None:
    assert render.tool_result("weather", {}, {}, "", render.now_of(tools())) == (
        "I couldn't check that just now."
    )


def test_history_turns_render_in_order() -> None:
    example = voice(history=(Turn(True, "One"), Turn(False, "Two")))

    roles = [m["role"] for m in render.request(example).messages]

    assert roles == ["system", "user", "assistant", "user"]


def test_tools_call_ids_follow_order() -> None:
    example = tools(calls=(ToolUse("calculate", {"expression": "1+1"}),
                           ToolUse("date", {"op": "today"})))

    said = render.answer(example)

    assert [m["role"] for m in said] == ["assistant", "tool", "assistant", "tool",
                                         "assistant"]
    assert said[3]["content"] == "Today is Saturday 7 November 2026."
