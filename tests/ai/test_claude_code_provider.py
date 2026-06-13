"""Interprétation du flux stream-json de Claude Code (parties pures)."""

from __future__ import annotations

from halo.ai.claude_code_provider import interpret_line


def test_init_line_carries_session_id() -> None:
    item = interpret_line({"type": "system", "subtype": "init", "session_id": "abc-123"})
    assert item.kind == "session"
    assert item.session_id == "abc-123"


def test_partial_text_delta_streams() -> None:
    item = interpret_line(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Bon"},
            },
        }
    )
    assert item.kind == "delta"
    assert item.text == "Bon"


def test_thinking_delta_is_ignored() -> None:
    item = interpret_line(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": "hmm"},
            },
        }
    )
    assert item.kind == "noise"


def test_assistant_message_joins_text_blocks() -> None:
    item = interpret_line(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Bonjour "},
                    {"type": "tool_use", "name": "x"},
                    {"type": "text", "text": "monde"},
                ]
            },
        }
    )
    assert item.kind == "full_text"
    assert item.text == "Bonjour monde"


def test_success_result_carries_usage_and_session() -> None:
    item = interpret_line(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "abc-123",
            "usage": {"input_tokens": 12, "output_tokens": 34},
        }
    )
    assert item.kind == "done"
    assert (item.input_tokens, item.output_tokens) == (12, 34)
    assert item.session_id == "abc-123"


def test_error_result_yields_clean_hint() -> None:
    item = interpret_line(
        {"type": "result", "subtype": "error_during_execution", "is_error": True,
         "result": "Something   went\nwrong"}
    )
    assert item.kind == "error"
    assert item.error_hint == "Something went wrong"


def test_unknown_lines_are_noise() -> None:
    assert interpret_line({"type": "user"}).kind == "noise"
    assert interpret_line({}).kind == "noise"
