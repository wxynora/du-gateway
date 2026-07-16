#!/usr/bin/env python3
"""Pure-local regression tests for streaming Prompt Cache collection."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_eq(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


class FakeStreamResponse:
    status_code = 200

    def iter_lines(self):
        packets = [
            {
                "model": "served-model",
                "choices": [{"delta": {"content": "真实流式回复"}, "finish_reason": None}],
            },
            {
                "model": "served-model",
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 18,
                    "total_tokens": 138,
                    "prompt_tokens_details": {"cached_tokens": 96},
                },
            },
        ]
        for packet in packets:
            yield ("data: " + json.dumps(packet, ensure_ascii=False)).encode("utf-8")
        yield b"data: [DONE]"


def test_stream_forward_collects_usage() -> None:
    import routes.chat as chat_route

    captured_bodies = []
    entries = []
    originals = {
        "_get_forward_targets": chat_route._get_forward_targets,
        "_apply_active_model_request_policy": chat_route._apply_active_model_request_policy,
        "_apply_openrouter_request_policy": chat_route._apply_openrouter_request_policy,
        "requests_post": chat_route.requests.post,
    }
    chat_route._get_forward_targets = lambda _model: [("https://upstream.test/v1/chat/completions", "")]
    chat_route._apply_active_model_request_policy = lambda body, _url: body
    chat_route._apply_openrouter_request_policy = lambda body, _url: body

    def fake_post(_url, *, headers, json, timeout, stream):
        captured_bodies.append(json)
        assert_eq(stream, True, "stream request flag")
        return FakeStreamResponse()

    chat_route.requests.post = fake_post
    try:
        body = {
            "model": "requested-model",
            "stream": True,
            "messages": [{"role": "user", "content": "你好"}],
        }
        profile = chat_route._build_prompt_cache_profile(body, "https://upstream.test/v1/chat/completions")
        chunks = list(
            chat_route._stream_forward_to_ai(
                body,
                {},
                prompt_cache_profile=profile,
                cache_debug_sink=entries.append,
            )
        )
    finally:
        chat_route._get_forward_targets = originals["_get_forward_targets"]
        chat_route._apply_active_model_request_policy = originals["_apply_active_model_request_policy"]
        chat_route._apply_openrouter_request_policy = originals["_apply_openrouter_request_policy"]
        chat_route.requests.post = originals["requests_post"]

    assert chunks[-1] == b"data: [DONE]\n"
    assert_eq(captured_bodies[0]["stream_options"], {"include_usage": True}, "usage must be requested")
    assert_eq(len(entries), 1, "one upstream stream must produce one cache entry")
    entry = entries[0]
    assert_eq(entry["usage"]["prompt_tokens"], 120, "prompt usage")
    assert_eq(entry["usage"]["cached_tokens"], 96, "cache read usage")
    assert_eq(entry["usage"]["completion_tokens"], 18, "completion usage")
    assert_eq(entry["response"]["actual_model"], "served-model", "actual upstream model")
    assert_eq(entry["response"]["finish_reason"], "stop", "stream finish reason")


def test_anthropic_stream_collector_preserves_cache_usage() -> None:
    from services.prompt_cache_debug import StreamCacheDebugCollector

    collector = StreamCacheDebugCollector(
        {"model": "requested-claude", "messages": []},
        "https://anthropic.test/v1/messages",
    )
    collector.feed(
        "data: "
        + json.dumps(
            {
                "model": "served-claude",
                "anthropic_model": "served-claude",
                "requested_model": "requested-claude",
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "input_tokens": 240,
                    "output_tokens": 32,
                    "cache_creation_input_tokens": 40,
                    "cache_read_input_tokens": 180,
                },
            }
        )
        + "\n\n"
    )
    entry = collector.build()
    assert_eq(entry["usage"]["cache_creation_input_tokens"], 40, "Anthropic cache creation")
    assert_eq(entry["usage"]["cache_read_input_tokens"], 180, "Anthropic cache read")
    assert_eq(entry["response"]["requested_model"], "requested-claude", "Anthropic requested model")
    assert_eq(entry["response"]["actual_model"], "served-claude", "Anthropic actual model")


def test_no_tool_stream_archives_cache_entry() -> None:
    from flask import Flask
    import routes.chat as chat_route

    app = Flask("stream-prompt-cache-no-tool-archive")
    archived = []
    originals = {
        "_stream_forward_to_ai": chat_route._stream_forward_to_ai,
        "_extract_and_store_hidden_sidecars": chat_route._extract_and_store_hidden_sidecars,
        "_is_du_daily_maintenance_request": chat_route._is_du_daily_maintenance_request,
        "step_archive_and_maybe_summary": chat_route.step_archive_and_maybe_summary,
    }

    def fake_stream(_body, _headers, *, prompt_cache_profile=None, cache_debug_sink=None):
        if cache_debug_sink:
            cache_debug_sink(
                {
                    "request": {"model": "test-model"},
                    "usage": {"usage_returned": True, "prompt_tokens": 42},
                    "response": {"actual_model": "served-model"},
                }
            )
        yield ("data: " + json.dumps({"choices": [{"delta": {"content": "普通回复"}, "finish_reason": "stop"}]}) + "\n\n").encode("utf-8")
        yield b"data: [DONE]\n\n"

    chat_route._stream_forward_to_ai = fake_stream
    chat_route._extract_and_store_hidden_sidecars = lambda text, **kwargs: text
    chat_route._is_du_daily_maintenance_request = lambda: False
    chat_route.step_archive_and_maybe_summary = lambda _window, _messages, assistant, **_kwargs: archived.append(assistant)
    try:
        body = {
            "model": "test-model",
            "stream": True,
            "messages": [{"role": "user", "content": "你好"}],
        }
        with app.test_request_context("/v1/chat/completions", method="POST"):
            output = b"".join(
                chat_route._stream_with_r2_archive(
                    body,
                    {},
                    window_id="local-test",
                    prompt_cache_profile=chat_route._build_prompt_cache_profile(body),
                )
            )
    finally:
        for name, value in originals.items():
            setattr(chat_route, name, value)

    assert "普通回复".encode("utf-8") in output
    assert_eq(len(archived), 1, "no-tool stream must archive once")
    assert_eq(len(archived[0]["cache_debug"]), 1, "no-tool stream must archive its cache entry")


def test_tool_stream_archives_each_cache_entry() -> None:
    from flask import Flask
    import routes.chat as chat_route

    app = Flask("stream-prompt-cache-archive")
    archived = []
    originals = {
        "_stream_forward_to_ai": chat_route._stream_forward_to_ai,
        "_extract_and_store_hidden_sidecars": chat_route._extract_and_store_hidden_sidecars,
        "_disable_followup_request": chat_route._disable_followup_request,
        "_is_du_daily_maintenance_request": chat_route._is_du_daily_maintenance_request,
        "step_archive_and_maybe_summary": chat_route.step_archive_and_maybe_summary,
        "sumitalk_card_suffix_for_stream": chat_route.sumitalk_card_suffix_for_stream,
    }
    round_no = 0

    def fake_stream(body, _headers, *, prompt_cache_profile=None, cache_debug_sink=None):
        nonlocal round_no
        round_no += 1
        if cache_debug_sink:
            cache_debug_sink(
                {
                    "request": {"model": body.get("model"), "round": round_no},
                    "usage": {"usage_returned": True, "prompt_tokens": 100 + round_no},
                    "response": {"actual_model": f"served-{round_no}"},
                }
            )
        has_tool_result = any(message.get("role") == "tool" for message in body.get("messages") or [])
        if not has_tool_result:
            packets = [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "test_tool", "arguments": "{\"x\":1}"},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ]
        else:
            packets = [{"choices": [{"delta": {"content": "最终答案"}, "finish_reason": "stop"}]}]
        for packet in packets:
            yield ("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n").encode("utf-8")
        yield b"data: [DONE]\n\n"

    chat_route._stream_forward_to_ai = fake_stream
    chat_route._extract_and_store_hidden_sidecars = lambda text, **kwargs: text
    chat_route._disable_followup_request = lambda: True
    chat_route._is_du_daily_maintenance_request = lambda: False
    chat_route.step_archive_and_maybe_summary = lambda _window, _messages, assistant, **_kwargs: archived.append(assistant)
    chat_route.sumitalk_card_suffix_for_stream = lambda _text, _messages: ""
    try:
        body = {
            "model": "test-model",
            "stream": True,
            "messages": [{"role": "user", "content": "查一下"}],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "test_tool", "parameters": {"type": "object"}},
                }
            ],
        }
        with app.test_request_context("/v1/chat/completions", method="POST"):
            output = b"".join(
                chat_route._stream_with_r2_archive(
                    body,
                    {},
                    window_id="local-test",
                    prompt_cache_profile=chat_route._build_prompt_cache_profile(body),
                    tool_executor=lambda _name, _arguments: json.dumps({"ok": True}),
                )
            )
    finally:
        for name, value in originals.items():
            setattr(chat_route, name, value)

    assert "最终答案".encode("utf-8") in output
    assert_eq(len(archived), 1, "one final assistant message must be archived")
    assert_eq(len(archived[0]["cache_debug"]), 2, "tool stream must archive every upstream round")
    assert_eq(archived[0]["cache_debug"][0]["request"]["round"], 1, "first tool round")
    assert_eq(archived[0]["cache_debug"][1]["request"]["round"], 2, "final tool round")


def main() -> None:
    test_stream_forward_collects_usage()
    test_anthropic_stream_collector_preserves_cache_usage()
    test_no_tool_stream_archives_cache_entry()
    test_tool_stream_archives_each_cache_entry()
    print("stream prompt cache debug ok")


if __name__ == "__main__":
    main()
