#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Blueprint, Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import chat
from routes.miniapp import upstreams as upstream_routes
from services.cloudflare_anthropic import (
    ANTHROPIC_REQUIRED_DEFAULT_MAX_TOKENS,
    anthropic_headers,
    openai_to_anthropic_request,
)
from services import upstream_policy
from services.upstream_policy import anthropic_messages_url
from storage import upstream_store


class _FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200, lines: list[bytes] | None = None):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)
        self.content = self.text.encode("utf-8")
        self._lines = list(lines or [])

    def json(self) -> dict:
        return self._payload

    def iter_lines(self):
        return iter(self._lines)


def _anthropic_response(text: str = "OK") -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-6",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 1},
    }


class AnthropicFormatSwitchTest(unittest.TestCase):
    def test_three_defaults_and_explicit_value_survives_model_save(self) -> None:
        items = [
            {"name": "kiro", "url": "https://api2.68886868.xyz/v1/chat/completions", "api_key": "k1"},
            {"name": "pioneer", "url": "https://api.pioneer.ai/v1/chat/completions", "api_key": "k2"},
            {
                "name": "cloudflare",
                "url": "https://gateway.ai.cloudflare.com/v1/account/gateway/anthropic/v1/messages",
                "api_key": "k3",
            },
            {"name": "other", "url": "https://example.com/v1/chat/completions", "api_key": "k4"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            upstream_store, "ACTIVE_MODEL_FILE", Path(temp_dir) / "active_upstream_model.json"
        ), mock.patch.object(
            upstream_store, "load_upstreams", return_value={"active": 0, "items": items}
        ):
            self.assertEqual(
                [True, True, True, False],
                [upstream_store.get_anthropic_format_for_item(item, index) for index, item in enumerate(items)],
            )
            self.assertTrue(upstream_store.get_active_anthropic_format())
            self.assertTrue(upstream_store.set_active_anthropic_format(False))
            self.assertFalse(upstream_store.get_active_anthropic_format())
            self.assertTrue(upstream_store.set_active_model("[Kiro次] claude-opus-4-6-thinking [不补]"))
            self.assertFalse(upstream_store.get_active_anthropic_format())
            saved = json.loads(upstream_store.ACTIVE_MODEL_FILE.read_text(encoding="utf-8"))
            entry = saved["models_by_upstream"]["url:https://api2.68886868.xyz/v1/chat/completions"]
            self.assertIs(entry["anthropic_format"], False)

    def test_url_headers_and_required_max_tokens(self) -> None:
        source_url = "https://api2.68886868.xyz/v1/chat/completions?route=main"
        target_url = anthropic_messages_url(source_url)
        self.assertEqual("https://api2.68886868.xyz/v1/messages?route=main", target_url)
        self.assertEqual(target_url, anthropic_messages_url(target_url))

        headers = anthropic_headers(
            {"Content-Type": "application/json", "Authorization": "Bearer test-key"},
            target_url,
            "test-key",
        )
        self.assertEqual("2023-06-01", headers["anthropic-version"])
        self.assertEqual("test-key", headers["x-api-key"])
        self.assertEqual("Bearer test-key", headers["Authorization"])

        base_body = {
            "model": "claude-opus-4-6",
            "messages": [{"role": "user", "content": "hello"}],
        }
        converted = openai_to_anthropic_request(base_body, target_url)
        self.assertEqual(128000, ANTHROPIC_REQUIRED_DEFAULT_MAX_TOKENS)
        self.assertEqual(128000, converted["max_tokens"])
        self.assertEqual(
            77,
            openai_to_anthropic_request({**base_body, "max_tokens": 77}, target_url)["max_tokens"],
        )
        self.assertEqual(
            88,
            openai_to_anthropic_request({**base_body, "max_completion_tokens": 88}, target_url)["max_tokens"],
        )

    def test_nonstream_forward_uses_anthropic_path_and_converts_response(self) -> None:
        captured: dict = {}

        def fake_post(url, *, headers, json, timeout):
            captured.update(url=url, headers=headers, body=json, timeout=timeout)
            return _FakeResponse(_anthropic_response("已切换"))

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            headers={"X-Reply-Channel": "sumitalk"},
        ), mock.patch.object(
            chat, "_get_forward_targets", return_value=[("https://api2.68886868.xyz/v1/chat/completions", "test-key")]
        ), mock.patch.object(
            chat, "_apply_active_model_request_policy", side_effect=lambda body, _url: body
        ), mock.patch.object(
            chat, "_apply_openrouter_request_policy", side_effect=lambda body, _url: body
        ), mock.patch.object(
            chat, "_should_use_anthropic_format", return_value=True
        ), mock.patch.object(
            chat, "_build_cache_debug_entry", return_value={}
        ), mock.patch.object(chat.requests, "post", side_effect=fake_post):
            data, status, error, _cache_debug = chat._forward_to_ai(
                {
                    "model": "[Kiro次] claude-opus-4-6-thinking [不补]",
                    "messages": [
                        {"role": "system", "content": "system"},
                        {"role": "user", "content": "hello"},
                    ],
                },
                {"X-Reply-Channel": "sumitalk"},
            )

        self.assertEqual(200, status)
        self.assertIsNone(error)
        self.assertEqual("https://api2.68886868.xyz/v1/messages", captured["url"])
        self.assertEqual("test-key", captured["headers"]["x-api-key"])
        self.assertEqual("2023-06-01", captured["headers"]["anthropic-version"])
        self.assertEqual(128000, captured["body"]["max_tokens"])
        self.assertNotIn("stream_options", captured["body"])
        self.assertEqual("已切换", data["choices"][0]["message"]["content"])

    def test_switch_off_keeps_the_existing_openai_forward(self) -> None:
        captured: dict = {}
        openai_response = {
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "model": "claude-opus-4-6",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "OPENAI"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        }

        def fake_post(url, *, headers, json, timeout):
            captured.update(url=url, headers=headers, body=json)
            return _FakeResponse(openai_response)

        app = Flask(__name__)
        with app.test_request_context("/v1/chat/completions", method="POST"), mock.patch.object(
            chat, "_get_forward_targets", return_value=[("https://api2.68886868.xyz/v1/chat/completions", "test-key")]
        ), mock.patch.object(
            chat, "_apply_active_model_request_policy", side_effect=lambda body, _url: body
        ), mock.patch.object(
            chat, "_apply_openrouter_request_policy", side_effect=lambda body, _url: body
        ), mock.patch.object(
            chat, "_should_use_anthropic_format", return_value=False
        ), mock.patch.object(
            chat, "_build_cache_debug_entry", return_value={}
        ), mock.patch.object(chat.requests, "post", side_effect=fake_post):
            data, status, error, _cache_debug = chat._forward_to_ai(
                {
                    "model": "claude-opus-4-6",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                {},
            )

        self.assertEqual(200, status)
        self.assertIsNone(error)
        self.assertEqual("https://api2.68886868.xyz/v1/chat/completions", captured["url"])
        self.assertNotIn("anthropic-version", captured["headers"])
        self.assertNotIn("x-api-key", captured["headers"])
        self.assertNotIn("max_tokens", captured["body"])
        self.assertEqual("OPENAI", data["choices"][0]["message"]["content"])

    def test_active_policy_reads_the_same_switch_without_inventing_kiro_fields(self) -> None:
        item = {"url": "https://api2.68886868.xyz/v1/chat/completions"}
        with mock.patch.object(upstream_store, "get_active_item", return_value=item), mock.patch.object(
            upstream_store, "get_active_anthropic_format", return_value=True
        ), mock.patch.object(
            upstream_store,
            "get_cached_active_model",
            return_value="[Kiro次] claude-opus-4-6-thinking [不补]",
        ), mock.patch.object(
            upstream_store, "get_active_claude_thinking_effort", return_value="max"
        ), mock.patch.object(
            upstream_store, "get_active_codex_reasoning_effort", return_value="high"
        ):
            self.assertTrue(upstream_policy.should_use_anthropic_format(item["url"]))
            body = upstream_policy.apply_active_model_request_policy(
                {"messages": [{"role": "user", "content": "hello"}]},
                item["url"],
            )

        self.assertEqual("[Kiro次] claude-opus-4-6-thinking [不补]", body["model"])
        self.assertNotIn("thinking", body)
        self.assertNotIn("output_config", body)

    def test_stream_forward_uses_anthropic_sse_adapter(self) -> None:
        captured: dict = {}
        fake_response = _FakeResponse(
            {},
            lines=[b"event: message_start", b'data: {"type":"message_start"}'],
        )

        def fake_post(url, *, headers, json, timeout, stream):
            captured.update(url=url, headers=headers, body=json, timeout=timeout, stream=stream)
            return fake_response

        adapted = [b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n']
        app = Flask(__name__)
        with app.test_request_context("/v1/chat/completions", method="POST"), mock.patch.object(
            chat, "_get_forward_targets", return_value=[("https://api2.68886868.xyz/v1/chat/completions", "test-key")]
        ), mock.patch.object(
            chat, "_apply_active_model_request_policy", side_effect=lambda body, _url: body
        ), mock.patch.object(
            chat, "_apply_openrouter_request_policy", side_effect=lambda body, _url: body
        ), mock.patch.object(
            chat, "_should_use_anthropic_format", return_value=True
        ), mock.patch.object(
            chat, "_anthropic_sse_to_openai_sse", return_value=iter(adapted)
        ) as sse_adapter, mock.patch.object(
            chat, "_StreamCacheDebugCollector"
        ), mock.patch.object(chat.requests, "post", side_effect=fake_post):
            chunks = list(
                chat._stream_forward_to_ai(
                    {
                        "model": "[Kiro次] claude-opus-4-6-thinking [不补]",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    {},
                )
            )

        self.assertEqual(adapted, chunks)
        self.assertEqual("https://api2.68886868.xyz/v1/messages", captured["url"])
        self.assertTrue(captured["stream"])
        self.assertTrue(captured["body"]["stream"])
        self.assertNotIn("stream_options", captured["body"])
        sse_adapter.assert_called_once()

    def test_backend_endpoint_and_probe_use_the_same_switch(self) -> None:
        item = {
            "name": "kiro",
            "url": "https://api2.68886868.xyz/v1/chat/completions",
            "api_key": "test-key",
        }
        app = Flask(__name__)
        bp = Blueprint("test_upstreams", __name__, url_prefix="/miniapp-api")
        upstream_routes.register_routes(bp)
        app.register_blueprint(bp)

        with mock.patch.object(
            upstream_store, "load_upstreams", return_value={"active": 0, "items": [item]}
        ), mock.patch.object(
            upstream_store, "get_cached_active_model", return_value="claude-opus-4-6"
        ), mock.patch.object(
            upstream_store, "get_active_anthropic_format", return_value=True
        ), mock.patch.object(
            upstream_store, "get_anthropic_format_for_item", return_value=True
        ), mock.patch.object(
            upstream_store, "set_active_anthropic_format", return_value=True
        ) as setter:
            client = app.test_client()
            get_response = client.get("/miniapp-api/upstreams")
            self.assertEqual(200, get_response.status_code)
            self.assertIs(get_response.get_json()["items"][0]["anthropic_format"], True)
            put_response = client.put(
                "/miniapp-api/upstreams/anthropic-format",
                json={"enabled": False},
            )
            self.assertEqual(200, put_response.status_code)
            setter.assert_called_once_with(False)
            invalid_response = client.put(
                "/miniapp-api/upstreams/anthropic-format",
                json={"enabled": "false"},
            )
            self.assertEqual(400, invalid_response.status_code)

        captured: dict = {}

        def fake_get(_url, *, headers, timeout):
            return _FakeResponse({"data": [{"id": "claude-opus-4-6"}]})

        def fake_post(url, *, headers, json, timeout):
            captured.update(url=url, headers=headers, body=json)
            return _FakeResponse(_anthropic_response())

        with mock.patch.object(
            upstream_store, "get_anthropic_format_for_item", return_value=True
        ), mock.patch.object(
            upstream_routes.requests, "get", side_effect=fake_get
        ), mock.patch.object(upstream_routes.requests, "post", side_effect=fake_post):
            result = upstream_routes._probe_upstream_item(item, 0)

        self.assertEqual("ok", result["status"])
        self.assertEqual("https://api2.68886868.xyz/v1/messages", captured["url"])
        self.assertEqual(8, captured["body"]["max_tokens"])
        self.assertEqual("test-key", captured["headers"]["x-api-key"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
