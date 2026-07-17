#!/usr/bin/env python3
"""Backend contract tests for native SumiTalk streaming.

Run from repo root:
  .venv/bin/python scripts/test_sumitalk_native_stream_backend.py
"""

from __future__ import annotations

import asyncio
import json
import inspect
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUMITALK_CHAT_NATIVE_STREAM_ENABLED"] = "1"


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_eq(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def make_state(job_id: str, *, execution_mode: str = "stream") -> dict:
    now = time.time()
    return {
        "id": job_id,
        "ok": True,
        "status": "queued",
        "stage": "queued",
        "created_ts": now,
        "updated_ts": now,
        "created_at": "2026-07-14T00:00:00+08:00",
        "updated_at": "2026-07-14T00:00:00+08:00",
        "window_id": "native-test",
        "reply_target": "device-test",
        "execution_mode": execution_mode,
    }


def test_mode_and_channel_parity(queue) -> tuple[str, dict]:
    old_model = queue.upstream_store.get_cached_active_model
    old_stream_enabled = queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED
    queue.upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "test-model"
    try:
        queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED = False
        assert_true(
            not queue.should_stream_sumitalk_chat_job("SumiTalk Native Android"),
            "native stream kill switch must keep the nonstream fallback available",
        )
        queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED = True
        base = {
            "messages": [{"role": "user", "content": "你好"}],
            "window_id": "native-test",
            "reply_target": "device-test",
            "stream": False,
            "app_mode": "real",
        }
        native_body = {**base, "client_request_id": "native-contract-1"}
        legacy_body = {**base, "client_request_id": "legacy-contract-1"}
        native_job_id, native_error, _ = queue.build_sumitalk_chat_job_payload(
            native_body,
            reply_target="device-test",
            user_agent="SumiTalk Native Android",
            force_last4="1",
            remote_addr="127.0.0.1",
        )
        legacy_job_id, legacy_error, _ = queue.build_sumitalk_chat_job_payload(
            legacy_body,
            reply_target="device-test",
            user_agent="SumiTalk MiniApp",
            force_last4="1",
            remote_addr="127.0.0.1",
        )
        assert_true(not native_error and not legacy_error, "both request modes should enqueue")

        native_item = queue.claim_next_sumitalk_chat_job()
        legacy_item = queue.claim_next_sumitalk_chat_job()
        assert_true(native_item is not None and legacy_item is not None, "both jobs should be claimable")
        assert_eq(native_item.job_id, native_job_id, "native job should keep queue order")
        assert_eq(legacy_item.job_id, legacy_job_id, "legacy job should keep queue order")
        assert_true(native_item.payload["chat_body"]["stream"] is True, "native Android must use stream mode")
        assert_true(legacy_item.payload["chat_body"]["stream"] is False, "legacy MiniApp must stay nonstream")
        assert_eq(native_item.payload["execution_mode"], "stream", "native mode should be observable")
        assert_eq(legacy_item.payload["execution_mode"], "nonstream", "legacy mode should be observable")
        for header in ("X-Reply-Channel", "X-Reply-Target", "X-Window-Id", "X-Force-Last4"):
            assert_eq(
                native_item.payload["headers"][header],
                legacy_item.payload["headers"][header],
                f"{header} must be identical across transport modes",
            )
        assert_eq(native_item.payload["headers"]["X-Reply-Channel"], "sumitalk", "both modes must enter SumiTalk pipeline")
        for key in ("model", "messages", "window_id", "app_mode"):
            assert_eq(
                native_item.payload["chat_body"][key],
                legacy_item.payload["chat_body"][key],
                f"{key} must be shared across transport modes",
            )
        queue.ack_sumitalk_chat_queue_item(native_item.id, lease_token=native_item.lease_token)
        queue.ack_sumitalk_chat_queue_item(legacy_item.id, lease_token=legacy_item.lease_token)
        return native_job_id, native_item.payload
    finally:
        queue.upstream_store.get_cached_active_model = old_model
        queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED = old_stream_enabled


def test_shared_game_nonstream_boundary(queue) -> None:
    old_model = queue.upstream_store.get_cached_active_model
    old_stream_enabled = queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED
    queue.upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "test-model"
    queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED = True
    try:
        expected_modes = {
            "private_board": "nonstream",
            "wenyou": "nonstream",
            "captivity_simulator": "nonstream",
            "random_imitator_td": "stream",
        }
        for index, (game_id, expected_mode) in enumerate(expected_modes.items(), start=1):
            job_id, error, _ = queue.build_sumitalk_chat_job_payload(
                {
                    "messages": [{"role": "user", "content": "继续这一轮"}],
                    "window_id": "native-game-test",
                    "reply_target": "device-test",
                    "client_request_id": f"native-game-contract-{index}",
                    "game_id": game_id,
                },
                reply_target="device-test",
                user_agent="SumiTalk Native Android",
                force_last4="1",
                remote_addr="127.0.0.1",
            )
            assert_true(not error, f"{game_id} should enqueue")
            item = queue.claim_next_sumitalk_chat_job()
            assert_true(item is not None, f"{game_id} job should be claimable")
            assert_eq(item.job_id, job_id, f"{game_id} should keep queue order")
            assert_eq(item.payload["execution_mode"], expected_mode, f"{game_id} transport mode")
            assert_eq(
                bool(item.payload["chat_body"]["stream"]),
                expected_mode == "stream",
                f"{game_id} gateway stream flag",
            )
            assert_true("game_id" not in item.payload["chat_body"], "routing metadata must not leak upstream")
            assert_eq(item.payload["headers"]["X-SumiTalk-Game-Id"], game_id, "game id must remain observable")
            queue.ack_sumitalk_chat_queue_item(item.id, lease_token=item.lease_token)
    finally:
        queue.upstream_store.get_cached_active_model = old_model
        queue.SUMITALK_CHAT_NATIVE_STREAM_ENABLED = old_stream_enabled


def test_durable_events_and_endpoints(queue, job_id: str) -> None:
    queue.append_sumitalk_chat_job_event(job_id, "run_started", {"mode": "snapshot"})
    queue.append_sumitalk_chat_job_event(
        job_id,
        "assistant_delta",
        {"part_id": "assistant-final", "mode": "delta", "text": "你 \n"},
    )
    response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "你好"},
                "finish_reason": "stop",
            }
        ]
    }
    assert_true(
        queue.finalize_sumitalk_chat_job(
            job_id,
            "done",
            state_patch={"status_code": 200, "response": response},
            event_payload={"part_id": "assistant-final", "mode": "snapshot", "text": "你好"},
        ),
        "first terminal transition should succeed",
    )
    assert_true(
        queue.finalize_sumitalk_chat_job(
            job_id,
            "done",
            state_patch={"status_code": 200, "response": response},
            event_payload={"text": "不应重复"},
        ),
        "repeating the same terminal transition should be idempotent",
    )
    assert_true(
        queue.append_sumitalk_chat_job_event(job_id, "assistant_delta", {"text": "迟到"}) is None,
        "events after a terminal event must be rejected",
    )
    events = queue.list_sumitalk_chat_job_events(job_id, after_seq=0, limit=100)
    terminal_events = [event for event in events if event.get("kind") == "assistant_final"]
    assert_eq(len(terminal_events), 1, "terminal event must be exactly once")
    delta_event = next(event for event in events if event.get("kind") == "assistant_delta")
    assert_eq(delta_event["text"], "你 \n", "delta whitespace must be preserved exactly")
    mirrored_kinds = [event.get("kind") for event in (queue.read_sumitalk_chat_job_state(job_id).get("events") or [])]
    assert_true("assistant_delta" not in mirrored_kinds, "token deltas must not rewrite the JSON summary file")
    assert_eq([event["seq"] for event in events], list(range(1, len(events) + 1)), "event sequence must be contiguous")
    assert_eq([event["event_id"] for event in events], [f"{job_id}:{event['seq']}" for event in events], "event ids must be stable")

    from flask import Blueprint, Flask
    from routes.miniapp.sumitalk_chat_jobs import register_routes

    app = Flask("sumitalk-native-stream-contract")
    bp = Blueprint("sumitalk_native_stream_contract", __name__, url_prefix="/miniapp-api")
    register_routes(bp)
    app.register_blueprint(bp)
    client = app.test_client()

    page = client.get(f"/miniapp-api/sumitalk-chat-jobs/{job_id}/events?after_seq=1&limit=100&wait_ms=0")
    assert_eq(page.status_code, 200, "event page should be available")
    page_json = page.get_json()
    assert_eq(page_json["status"], "done", "event page should derive terminal status")
    assert_true(all(int(event["seq"]) > 1 for event in page_json["events"]), "after_seq must resume strictly after cursor")

    stream = client.get(
        f"/miniapp-api/sumitalk-chat-jobs/{job_id}/events/stream?after_seq=1",
        buffered=True,
    )
    assert_eq(stream.status_code, 200, "SSE endpoint should be available")
    assert_true(stream.content_type.startswith("text/event-stream"), "SSE endpoint must use event-stream content type")
    assert_eq(stream.headers.get("X-Accel-Buffering"), "no", "proxy buffering must be disabled")
    streamed = []
    for line in stream.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            streamed.append(json.loads(line[6:]))
    assert_eq([event["seq"] for event in streamed], [event["seq"] for event in page_json["events"]], "polling and SSE must read the same log")
    assert_eq(streamed[-1]["kind"], "assistant_final", "SSE should close on the terminal event")

    paged_job_id = "9" * 32
    queue.write_sumitalk_chat_job_state(make_state(paged_job_id))
    for index in range(120):
        queue.append_sumitalk_chat_job_event(
            paged_job_id,
            "assistant_delta",
            {"part_id": "assistant-final", "mode": "delta", "text": str(index)},
        )
    queue.finalize_sumitalk_chat_job(
        paged_job_id,
        "done",
        state_patch={"status_code": 200, "response": response},
        event_payload={"part_id": "assistant-final", "mode": "snapshot", "text": "done"},
    )
    first_page = client.get(
        f"/miniapp-api/sumitalk-chat-jobs/{paged_job_id}/events?after_seq=0&limit=100&wait_ms=0"
    ).get_json()
    assert_true(first_page["has_more"], "first polling page should advertise remaining events")
    assert_eq(first_page["status"], "running", "polling must not report terminal before delivering terminal event")
    second_page = client.get(
        f"/miniapp-api/sumitalk-chat-jobs/{paged_job_id}/events?after_seq=100&limit=100&wait_ms=0"
    ).get_json()
    assert_eq(second_page["status"], "done", "polling may report done once terminal event is in the page")
    assert_eq(second_page["events"][-1]["kind"], "assistant_final", "terminal polling page must include terminal event")
    paged_stream = client.get(
        f"/miniapp-api/sumitalk-chat-jobs/{paged_job_id}/events/stream?after_seq=0",
        buffered=True,
    )
    paged_events = [
        json.loads(line[6:])
        for line in paged_stream.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]
    assert_eq(len(paged_events), 121, "SSE must drain every page before closing on terminal state")
    assert_eq(paged_events[-1]["kind"], "assistant_final", "paged SSE must include its terminal event")

    recovered_job_id = "c" * 32
    queue.write_sumitalk_chat_job_state(make_state(recovered_job_id))
    queue.append_sumitalk_chat_job_event(
        recovered_job_id,
        "assistant_final",
        {"text": "崩溃后恢复", "role": "assistant", "finish_reason": "stop", "status_code": 200},
    )
    recovered = queue.maybe_mark_sumitalk_chat_job_stale(recovered_job_id)
    assert_eq(recovered["status"], "done", "terminal event must recover a lagging JSON summary")
    assert_eq(
        recovered["response"]["choices"][0]["message"]["content"],
        "崩溃后恢复",
        "terminal recovery must keep the final reply",
    )

    cancelled_job_id = "d" * 32
    queue.write_sumitalk_chat_job_state(make_state(cancelled_job_id))
    from services import realtime_publish

    original_publish = realtime_publish.publish_sumitalk_chat_event
    published_terminals = []
    realtime_publish.publish_sumitalk_chat_event = lambda _device_id, event, window_id="": (
        published_terminals.append((event, window_id)) or True
    )
    try:
        assert_true(queue.cancel_sumitalk_chat_job(cancelled_job_id, "test_cancel"), "cancel should succeed")
        assert_true(queue.cancel_sumitalk_chat_job(cancelled_job_id, "test_cancel"), "cancel should be idempotent")
    finally:
        realtime_publish.publish_sumitalk_chat_event = original_publish
    cancelled_events = queue.list_sumitalk_chat_job_events(cancelled_job_id, limit=100)
    assert_eq(
        [event["kind"] for event in cancelled_events].count("run_cancelled"),
        1,
        "cancelled jobs must have exactly one terminal event",
    )
    assert_eq(
        [event.get("kind") for event, _window_id in published_terminals],
        ["run_cancelled"],
        "stream cancellation must notify the live broker immediately and only once",
    )

    failed_job_id = "e" * 32
    queue.write_sumitalk_chat_job_state(make_state(failed_job_id))
    assert_true(
        queue.finalize_sumitalk_chat_job(
            failed_job_id,
            "error",
            state_patch={"status_code": 502, "error": "upstream failed"},
            event_payload={"status_code": 502, "error": "upstream failed"},
        ),
        "error should finalize",
    )
    failed_events = queue.list_sumitalk_chat_job_events(failed_job_id, limit=100)
    assert_eq(failed_events[-1]["kind"], "run_error", "errors must use the native terminal event")

    concurrent_job_id = "f" * 32
    queue.write_sumitalk_chat_job_state(make_state(concurrent_job_id))
    with ThreadPoolExecutor(max_workers=8) as executor:
        appended = list(
            executor.map(
                lambda index: queue.append_sumitalk_chat_job_event(
                    concurrent_job_id,
                    "assistant_delta",
                    {"part_id": "assistant-final", "mode": "delta", "text": str(index)},
                ),
                range(60),
            )
        )
    assert_true(all(appended), "concurrent delta appends should all succeed")
    concurrent_events = queue.list_sumitalk_chat_job_events(concurrent_job_id, limit=100)
    assert_eq(
        [event["seq"] for event in concurrent_events],
        list(range(1, 61)),
        "SQLite must allocate monotonic sequence numbers across concurrent writers",
    )


def test_live_dispatch_precedes_async_persistence(queue) -> None:
    from services import realtime_publish

    job_id = "1" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id, execution_mode="stream"))
    original_publish = realtime_publish.publish_sumitalk_chat_event
    original_persist = queue._persist_sumitalk_chat_live_event
    persistence_started = threading.Event()
    release_persistence = threading.Event()
    terminal_published = threading.Event()
    published = []

    def fake_publish(_device_id, event, window_id=""):
        published.append((int(event.get("seq") or 0), str(event.get("kind") or ""), window_id))
        if event.get("kind") == "assistant_final":
            terminal_published.set()
        return True

    def blocked_persist(event):
        if not persistence_started.is_set():
            persistence_started.set()
            release_persistence.wait(2.0)
        original_persist(event)

    realtime_publish.publish_sumitalk_chat_event = fake_publish
    queue._persist_sumitalk_chat_live_event = blocked_persist
    try:
        assert_true(
            queue.emit_live_sumitalk_chat_job_event(job_id, "assistant_delta", {"text": "一"}),
            "first live event should be accepted",
        )
        assert_true(persistence_started.wait(1.0), "async persistence should receive the first event")
        assert_true(
            queue.emit_live_sumitalk_chat_job_event(job_id, "assistant_delta", {"text": "二"}),
            "second live event should be accepted while SQLite is blocked",
        )
        assert_true(
            queue.finalize_sumitalk_chat_job(
                job_id,
                "done",
                state_patch={"status_code": 200, "response": {"choices": []}},
                event_payload={"text": "一二", "role": "assistant", "finish_reason": "stop"},
                live=True,
            ),
            "live terminal transition should succeed",
        )
        assert_true(
            terminal_published.wait(1.0),
            "assistant_final must reach realtime before the blocked SQLite writer is released",
        )
        assert_eq(
            [(seq, kind) for seq, kind, _window_id in published],
            [(1, "assistant_delta"), (2, "assistant_delta"), (3, "assistant_final")],
            "realtime delivery must stay ordered and independent from persistence",
        )
        assert_eq(
            queue._read_durable_sumitalk_chat_events(job_id, 0, 10),
            [],
            "blocked persistence must not be mistaken for realtime delivery",
        )
    finally:
        release_persistence.set()
        assert_true(queue.flush_sumitalk_chat_live_events(), "live events should finish persistence after release")
        queue._persist_sumitalk_chat_live_event = original_persist
        realtime_publish.publish_sumitalk_chat_event = original_publish

    durable = queue._read_durable_sumitalk_chat_events(job_id, 0, 10)
    assert_eq([event["seq"] for event in durable], [1, 2, 3], "reconnect log must catch up in order")
    assert_eq(durable[-1]["kind"], "assistant_final", "reconnect log must retain the terminal event")
    mirrored = queue.read_sumitalk_chat_job_state(job_id).get("events") or []
    assert_eq(
        [int(event.get("seq") or 0) for event in mirrored],
        sorted(int(event.get("seq") or 0) for event in mirrored),
        "async summary mirroring must remain ordered even when terminal state is written first",
    )


def test_sse_reads_live_broker_without_active_sqlite_polling(queue) -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import sumitalk_chat_jobs as jobs_route

    job_id = "2" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id, execution_mode="stream"))
    terminal = {
        "seq": 1,
        "event_id": f"{job_id}:1",
        "run_id": job_id,
        "job_id": job_id,
        "kind": "assistant_final",
        "text": "实时完成",
    }
    durable_reads = []
    original_list = jobs_route.list_sumitalk_chat_job_events
    original_subscribe = jobs_route.subscribe_sumitalk_chat_events

    def fake_list(*_args, **_kwargs):
        durable_reads.append(True)
        return []

    def fake_subscribe(received_job_id, after_seq):
        assert_eq(received_job_id, job_id, "SSE must subscribe to the requested run")
        assert_eq(after_seq, 0, "live subscription must continue after the recovery cursor")
        yield terminal

    jobs_route.list_sumitalk_chat_job_events = fake_list
    jobs_route.subscribe_sumitalk_chat_events = fake_subscribe
    try:
        app = Flask("sumitalk-live-sse-contract")
        bp = Blueprint("sumitalk_live_sse_contract", __name__, url_prefix="/miniapp-api")
        jobs_route.register_routes(bp)
        app.register_blueprint(bp)
        response = app.test_client().get(
            f"/miniapp-api/sumitalk-chat-jobs/{job_id}/events/stream?after_seq=0",
            buffered=True,
        )
    finally:
        jobs_route.list_sumitalk_chat_job_events = original_list
        jobs_route.subscribe_sumitalk_chat_events = original_subscribe

    streamed = [
        json.loads(line[6:])
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]
    assert_eq(streamed, [terminal], "SSE must forward the broker event directly")
    assert_eq(len(durable_reads), 1, "normal live delivery must only query SQLite for initial recovery")


def test_realtime_run_event_broker() -> None:
    from services.sumitalk_live_event_broker import SumiTalkRunEventBroker

    async def scenario():
        broker = SumiTalkRunEventBroker(max_events_per_job=32)
        event = {"job_id": "3" * 32, "seq": 1, "kind": "assistant_final", "text": "完成"}
        assert_true(await broker.publish(event), "broker should accept a valid run event")
        stream = broker.subscribe(event["job_id"], 0)
        return await stream.__anext__()

    assert_eq(asyncio.run(scenario()), {"job_id": "3" * 32, "seq": 1, "kind": "assistant_final", "text": "完成"}, "broker should replay its live ring")


def test_realtime_run_event_subscription_bridge() -> None:
    from services import realtime_publish

    job_id = "4" * 32
    terminal = {"job_id": job_id, "seq": 7, "kind": "assistant_final", "text": "完成"}
    captured = {}
    closed = threading.Event()
    original_get = realtime_publish.requests.get

    class FakeResponse:
        status_code = 200

        def iter_lines(self, decode_unicode=False):
            yield ": ping"
            yield "data: " + json.dumps(terminal, ensure_ascii=False)

        def close(self):
            closed.set()

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    realtime_publish.requests.get = fake_get
    try:
        received = list(realtime_publish.subscribe_sumitalk_chat_events(job_id, 6))
    finally:
        realtime_publish.requests.get = original_get

    assert_eq(received, [None, terminal], "gateway bridge must preserve heartbeat and realtime event data")
    assert_eq(captured.get("params"), {"job_id": job_id, "after_seq": 6}, "bridge must resume from the SSE cursor")
    assert_true(bool(captured.get("stream")), "bridge must keep the local IPC response streaming")
    assert_true(closed.is_set(), "bridge must close its local HTTP stream")


def test_realtime_failure_falls_back_to_durable_log(queue) -> None:
    from services import realtime_publish

    job_id = "5" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id, execution_mode="stream"))
    original_publish = realtime_publish.publish_sumitalk_chat_event
    publish_attempts = []
    realtime_publish.publish_sumitalk_chat_event = lambda _device_id, event, window_id="": (
        publish_attempts.append(int(event.get("seq") or 0)) and False
    )
    try:
        queue.emit_live_sumitalk_chat_job_event(job_id, "assistant_delta", {"text": "一"})
        queue.emit_live_sumitalk_chat_job_event(job_id, "assistant_delta", {"text": "二"})
        assert_true(queue.flush_sumitalk_chat_live_events(), "failed realtime events should still persist")
    finally:
        realtime_publish.publish_sumitalk_chat_event = original_publish

    assert_eq(publish_attempts, [1], "realtime failure should briefly open the local circuit")
    assert_eq(
        [event.get("text") for event in queue._read_durable_sumitalk_chat_events(job_id, 0, 10)],
        ["一", "二"],
        "SQLite fallback must retain events skipped by the unavailable realtime channel",
    )


def test_worker_stream_and_nonstream(queue) -> None:
    from flask import Flask, Response, jsonify, request
    import routes.chat as chat_route

    app = Flask("sumitalk-worker-contract")
    captured = []
    reply_text = "你 好\n" + ("长" * 2000)
    original_chat_completions = chat_route.chat_completions

    def fake_chat_completions():
        body = request.get_json(silent=True) or {}
        captured.append(
            {
                "stream": bool(body.get("stream")),
                "channel": request.headers.get("X-Reply-Channel"),
                "target": request.headers.get("X-Reply-Target"),
                "window": request.headers.get("X-Window-Id"),
                "messages": body.get("messages"),
            }
        )
        if body.get("stream"):
            if body.get("simulate_truncated"):
                return Response(
                    ['data: {"choices":[{"delta":{"content":"半截"}}]}\n\n'],
                    content_type="text/event-stream",
                )

            def generate():
                yield 'data: {"id":"stream-1","model":"test-model","choices":[{"delta":{"role":"assistant"}}]}\n\n'
                yield 'data: {"id":"stream-1","model":"test-model","choices":[{"delta":{"content":"你"}}]}\n\n'
                yield "data: " + json.dumps(
                    {
                        "id": "stream-1",
                        "model": "test-model",
                        "choices": [{"delta": {"content": reply_text[1:]}, "finish_reason": "stop"}],
                    },
                    ensure_ascii=False,
                ) + "\n\n"
                yield "data: [DONE]\n\n"

            response_headers = {}
            if body.get("route_emits_events"):
                rich_job_id = str(request.headers.get("X-SumiTalk-Job-Id") or "")
                queue.emit_live_sumitalk_chat_job_event(
                    rich_job_id,
                    "assistant_text_started",
                    {"part_id": "assistant-text-1", "round": 1, "mode": "delta"},
                )
                for event_text in queue._chat_event_text_chunks(reply_text):
                    queue.emit_live_sumitalk_chat_job_event(
                        rich_job_id,
                        "assistant_delta",
                        {
                            "part_id": "assistant-text-1",
                            "round": 1,
                            "mode": "delta",
                            "text": event_text,
                        },
                    )
                queue.emit_live_sumitalk_chat_job_event(
                    rich_job_id,
                    "assistant_text_finished",
                    {"part_id": "assistant-text-1", "round": 1, "mode": "delta"},
                )
                response_headers["X-SumiTalk-Rich-Events"] = "1"
            return Response(generate(), content_type="text/event-stream", headers=response_headers)
        return jsonify(
            {
                "id": "nonstream-1",
                "model": "test-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": reply_text},
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SumiTalk Native Android",
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": "device-test",
        "X-Window-Id": "native-test",
    }
    chat_route.chat_completions = fake_chat_completions
    try:
        for stream in (True, False):
            job_id = ("a" if stream else "b") * 32
            queue.write_sumitalk_chat_job_state(make_state(job_id, execution_mode="stream" if stream else "nonstream"))
            payload = {
                "chat_body": {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "你好"}],
                    "window_id": "native-test",
                    "stream": stream,
                },
                "headers": {**headers, "X-SumiTalk-Job-Id": job_id},
                "remote_addr": "127.0.0.1",
                "execution_mode": "stream" if stream else "nonstream",
            }
            assert_eq(queue.run_sumitalk_chat_job(app, job_id, payload), "done", "worker should complete both modes")
            if stream:
                assert_true(queue.flush_sumitalk_chat_live_events(), "stream events should finish async persistence")
            state = queue.read_sumitalk_chat_job_state(job_id)
            assert_eq(state["response"]["choices"][0]["message"]["content"], reply_text, "both modes must persist the same exact reply")
            worker_events = queue.list_sumitalk_chat_job_events(job_id, limit=100)
            kinds = [event["kind"] for event in worker_events]
            assert_eq(kinds.count("assistant_final"), 1, "worker must emit one terminal event")
            if stream:
                assert_true("assistant_delta" in kinds, "stream mode must persist text deltas")
                assert_eq(
                    "".join(event.get("text") or "" for event in worker_events if event.get("kind") == "assistant_delta"),
                    reply_text,
                    "large upstream chunks must be split without truncating the reconstructed reply",
                )
            else:
                assert_true("assistant_delta" not in kinds, "nonstream mode must remain one-shot")
        rich_job_id = "7" * 32
        queue.write_sumitalk_chat_job_state(make_state(rich_job_id, execution_mode="stream"))
        rich_payload = {
            "chat_body": {
                "model": "test-model",
                "messages": [{"role": "user", "content": "富事件去重"}],
                "window_id": "native-test",
                "stream": True,
                "route_emits_events": True,
            },
            "headers": {**headers, "X-SumiTalk-Job-Id": rich_job_id},
            "remote_addr": "127.0.0.1",
            "execution_mode": "stream",
        }
        assert_eq(queue.run_sumitalk_chat_job(app, rich_job_id, rich_payload), "done", "rich stream should complete")
        assert_true(queue.flush_sumitalk_chat_live_events(), "rich stream events should finish async persistence")
        rich_events = queue.list_sumitalk_chat_job_events(rich_job_id, limit=100)
        assert_eq(
            "".join(event.get("text") or "" for event in rich_events if event.get("kind") == "assistant_delta"),
            reply_text,
            "worker must not replay assistant deltas already emitted by the shared chat route",
        )
        assert_eq(
            queue.read_sumitalk_chat_job_state(rich_job_id)["response"]["choices"][0]["message"]["content"],
            reply_text,
            "rich mode must still aggregate the exact terminal response",
        )
        assert_eq(
            rich_events[-1].get("part_id"),
            "assistant-text-1",
            "terminal event must reconcile the final live assistant part instead of appending a duplicate",
        )
        truncated_job_id = "8" * 32
        queue.write_sumitalk_chat_job_state(make_state(truncated_job_id, execution_mode="stream"))
        truncated_payload = {
            "chat_body": {
                "model": "test-model",
                "messages": [{"role": "user", "content": "截断测试"}],
                "window_id": "native-test",
                "stream": True,
                "simulate_truncated": True,
            },
            "headers": {**headers, "X-SumiTalk-Job-Id": truncated_job_id},
            "remote_addr": "127.0.0.1",
            "execution_mode": "stream",
        }
        assert_eq(
            queue.run_sumitalk_chat_job(app, truncated_job_id, truncated_payload),
            "error",
            "truncated streams must fail instead of saving a partial reply as complete",
        )
        assert_true(queue.flush_sumitalk_chat_live_events(), "stream error should finish async persistence")
        truncated_events = queue.list_sumitalk_chat_job_events(truncated_job_id, limit=100)
        assert_eq(truncated_events[-1]["kind"], "run_error", "truncated streams must end with run_error")
        assert_eq(captured[0]["channel"], captured[1]["channel"], "worker channel injection must match")
        assert_eq(captured[0]["target"], captured[1]["target"], "worker reply target must match")
        assert_eq(captured[0]["window"], captured[1]["window"], "worker window must match")
        assert_eq(captured[0]["messages"], captured[1]["messages"], "worker request messages must match")
    finally:
        chat_route.chat_completions = original_chat_completions


def test_rich_tool_stream_events() -> None:
    from flask import Flask
    import routes.chat as chat_route

    app = Flask("sumitalk-rich-stream-contract")
    events = []
    originals = {
        "_stream_forward_to_ai": chat_route._stream_forward_to_ai,
        "_extract_and_store_hidden_sidecars": chat_route._extract_and_store_hidden_sidecars,
        "_disable_followup_request": chat_route._disable_followup_request,
        "_is_du_daily_maintenance_request": chat_route._is_du_daily_maintenance_request,
        "sumitalk_card_suffix_for_stream": chat_route.sumitalk_card_suffix_for_stream,
    }

    def fake_stream(body, _headers, **_kwargs):
        has_tool_result = any(message.get("role") == "tool" for message in body.get("messages") or [])
        if not has_tool_result:
            packets = [
                {"choices": [{"delta": {"reasoning_content": "先看一下"}}]},
                {"choices": [{"delta": {"content": "我先查一下。"}}]},
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
                },
            ]
        else:
            packets = [
                {"choices": [{"delta": {"reasoning_content": "结果够了"}}]},
                {"choices": [{"delta": {"content": "最终答案"}, "finish_reason": "stop"}]},
            ]
        for packet in packets:
            yield ("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n").encode("utf-8")
        yield b"data: [DONE]\n\n"

    chat_route._stream_forward_to_ai = fake_stream
    chat_route._extract_and_store_hidden_sidecars = lambda text, **kwargs: text
    chat_route._disable_followup_request = lambda: True
    chat_route._is_du_daily_maintenance_request = lambda: True
    chat_route.sumitalk_card_suffix_for_stream = lambda text, messages: ""
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
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            headers={"X-Reply-Channel": "sumitalk", "X-Reply-Target": "device-test"},
        ):
            output = b"".join(
                chat_route._stream_with_r2_archive(
                    body,
                    {},
                    window_id="native-test",
                    reply_channel="sumitalk",
                    tool_executor=lambda name, arguments: json.dumps({"ok": True, "value": 1}),
                    sumitalk_event_sink=lambda kind, payload: events.append({"kind": kind, **payload}),
                )
            ).decode("utf-8")
        kinds = [event["kind"] for event in events]
        assert_true("reasoning_delta" in kinds, "reasoning should be emitted before the round finishes")
        assert_true("assistant_delta" in kinds, "intermediate assistant dialogue should remain visible")
        assert_true("tool_call_started" in kinds, "tool execution should expose running state")
        assert_true("tool_arguments_delta" in kinds, "tool arguments should use the native rich event contract")
        assert_true("tool_output_delta" in kinds, "tool output should be available before completion")
        assert_true("tool_call_finished" in kinds, "tool execution should expose completion")
        assistant_text = "".join(
            event.get("text") or "" for event in events if event.get("kind") == "assistant_delta"
        )
        assert_true("我先查一下。" in assistant_text, "tool-round dialogue must stream before tool execution")
        assert_true("最终答案" in assistant_text, "final assistant text must use the same rich event stream")
        assert_true("最终答案" in output, "final assistant text should still be streamed")
        assert_true("我先查一下" not in output, "intermediate dialogue must not be replayed into the final text part")
        first_reasoning = kinds.index("reasoning_delta")
        tool_started = kinds.index("tool_call_started")
        tool_finished = kinds.index("tool_call_finished")
        assert_true(first_reasoning < tool_started < tool_finished, "reasoning and tool lifecycle order must be stable")
    finally:
        for name, value in originals.items():
            setattr(chat_route, name, value)


def test_no_tool_reasoning_stream_events() -> None:
    from flask import Flask
    import routes.chat as chat_route

    app = Flask("sumitalk-no-tool-stream-contract")
    events = []
    originals = {
        "_stream_forward_to_ai": chat_route._stream_forward_to_ai,
        "_extract_and_store_hidden_sidecars": chat_route._extract_and_store_hidden_sidecars,
        "_is_du_daily_maintenance_request": chat_route._is_du_daily_maintenance_request,
    }

    def fake_stream(_body, _headers, **_kwargs):
        packets = [
            {"choices": [{"delta": {"reasoning_content": "先想"}}]},
            {"choices": [{"delta": {"content": "你\n"}}]},
            {"choices": [{"delta": {"content": "[du:ho"}}]},
            {"choices": [{"delta": {"content": "me desire=30]"}}]},
            {"choices": [{"delta": {"reasoning_content": "再想"}}]},
            {"choices": [{"delta": {"content": " 好"}, "finish_reason": "stop"}]},
        ]
        for packet in packets:
            yield ("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n").encode("utf-8")
        yield b"data: [DONE]\n\n"

    chat_route._stream_forward_to_ai = fake_stream
    chat_route._extract_and_store_hidden_sidecars = lambda text, **kwargs: text
    chat_route._is_du_daily_maintenance_request = lambda: True
    try:
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            headers={"X-Reply-Channel": "sumitalk", "X-Reply-Target": "device-test"},
        ):
            output = b"".join(
                chat_route._stream_with_r2_archive(
                    {
                        "model": "test-model",
                        "stream": True,
                        "messages": [{"role": "user", "content": "你好"}],
                    },
                    {},
                    window_id="native-test",
                    reply_channel="sumitalk",
                    sumitalk_event_sink=lambda kind, payload: events.append({"kind": kind, **payload}),
                )
            ).decode("utf-8")
        kinds = [event["kind"] for event in events]
        assert_eq(
            [kind for kind in kinds if kind.startswith("reasoning_")],
            ["reasoning_started", "reasoning_delta", "reasoning_delta", "reasoning_finished"],
            "no-tool reasoning must expose a complete streaming lifecycle",
        )
        assert_eq(
            "".join(event.get("text") or "" for event in events if event.get("kind") == "assistant_delta"),
            "你\n 好",
            "no-tool assistant events must preserve the exact visible stream",
        )
        assert_eq(
            [
                (event.get("kind"), event.get("text"))
                for event in events
                if event.get("kind") in {"reasoning_delta", "assistant_delta"}
            ],
            [
                ("reasoning_delta", "先想"),
                ("assistant_delta", "你"),
                ("reasoning_delta", "再想"),
                ("assistant_delta", "\n 好"),
            ],
            "reasoning and assistant deltas must keep the upstream packet order",
        )
        visible_parts = []
        for line in output.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            packet = json.loads(line[6:])
            visible_parts.append(str((((packet.get("choices") or [{}])[0] or {}).get("delta") or {}).get("content") or ""))
        assert_eq("".join(visible_parts), "你\n 好", "visible SSE must keep spaces and line breaks")
        assert_true("先想" not in output, "reasoning must stay out of assistant text SSE")
        assert_true("du:home" not in output, "Pixel Home short markers must stay out of visible SSE")
    finally:
        for name, value in originals.items():
            setattr(chat_route, name, value)


def test_sumitalk_stream_completion_does_not_wait_for_archive() -> None:
    from flask import Flask
    import routes.chat as chat_route

    app = Flask("sumitalk-async-archive-contract")
    archive_started = threading.Event()
    archive_release = threading.Event()
    archive_finished = threading.Event()
    originals = {
        "_stream_forward_to_ai": chat_route._stream_forward_to_ai,
        "_extract_and_store_hidden_sidecars": chat_route._extract_and_store_hidden_sidecars,
        "_is_du_daily_maintenance_request": chat_route._is_du_daily_maintenance_request,
        "step_archive_and_maybe_summary": chat_route.step_archive_and_maybe_summary,
    }

    def fake_stream(_body, _headers, **_kwargs):
        yield 'data: {"choices":[{"delta":{"content":"最终正文"},"finish_reason":"stop"}]}\n\n'.encode("utf-8")
        yield b"data: [DONE]\n\n"

    def blocked_archive(*_args, **_kwargs):
        archive_started.set()
        archive_release.wait(2.0)
        archive_finished.set()

    chat_route._stream_forward_to_ai = fake_stream
    chat_route._extract_and_store_hidden_sidecars = lambda text, **_kwargs: text
    chat_route._is_du_daily_maintenance_request = lambda: False
    chat_route.step_archive_and_maybe_summary = blocked_archive

    def consume_stream() -> bytes:
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            headers={"X-Reply-Channel": "sumitalk", "X-Reply-Target": "device-test"},
        ):
            return b"".join(
                chat_route._stream_with_r2_archive(
                    {
                        "model": "test-model",
                        "stream": True,
                        "messages": [{"role": "user", "content": "你好"}],
                    },
                    {},
                    window_id="native-test",
                    reply_channel="sumitalk",
                    sumitalk_event_sink=lambda _kind, _payload: None,
                )
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(consume_stream)
            assert_true(archive_started.wait(3.0), "stream completion should schedule archive work")
            output = future.result(timeout=0.5)
            assert_true("最终正文" in output.decode("utf-8"), "assistant text must finish before archive completes")
            assert_true(not archive_finished.is_set(), "stream response must return while archive is still blocked")
            archive_release.set()
            assert_true(archive_finished.wait(1.0), "background archive should still run to completion")
    finally:
        archive_release.set()
        for name, value in originals.items():
            setattr(chat_route, name, value)


def test_sumitalk_stream_archive_queue_is_fifo() -> None:
    import routes.chat as chat_route

    original_archive = chat_route.step_archive_and_maybe_summary
    first_started = threading.Event()
    release_first = threading.Event()
    second_finished = threading.Event()
    order = []

    def fake_archive(window_id, *_args, **_kwargs):
        order.append(f"start:{window_id}")
        if window_id == "fifo-1":
            first_started.set()
            release_first.wait(2.0)
        order.append(f"end:{window_id}")
        if window_id == "fifo-2":
            second_finished.set()

    chat_route.step_archive_and_maybe_summary = fake_archive
    try:
        chat_route._enqueue_sumitalk_stream_archive(("fifo-1", [], {}, None, False, False))
        chat_route._enqueue_sumitalk_stream_archive(("fifo-2", [], {}, None, False, False))
        assert_true(first_started.wait(1.0), "first archive should start")
        time.sleep(0.05)
        assert_eq(order, ["start:fifo-1"], "second archive must not overtake a blocked first archive")
        release_first.set()
        assert_true(second_finished.wait(1.0), "queued second archive should run after the first")
        assert_eq(
            order,
            ["start:fifo-1", "end:fifo-1", "start:fifo-2", "end:fifo-2"],
            "stream archives must preserve conversation order",
        )
    finally:
        release_first.set()
        chat_route.step_archive_and_maybe_summary = original_archive


def test_pixel_home_stream_and_final_parity() -> None:
    from services.pc_command_handler import PcmdDuThoughtStreamState
    from services.pixel_home import split_assistant_for_pixel_home

    state = PcmdDuThoughtStreamState()
    visible_chunks = [
        state.feed_delta("去吧。\n[d"),
        state.feed_delta("u:home desire=30"),
        state.feed_delta("]"),
    ]
    assert_eq("".join(visible_chunks), "去吧。", "streaming must match the final visible reply")

    visible, payload = split_assistant_for_pixel_home("去吧。\n[du:home desire=30]")
    assert_eq(visible, "去吧。", "final parsing must keep the same visible reply")
    assert_true(isinstance(payload, dict), "final parsing must preserve the Pixel Home sidecar")
    assert_eq(payload.get("du_body_state", {}).get("desire_value"), 30, "desire must still reach state update")


def test_shared_chat_pipeline_structure() -> None:
    import routes.chat as chat_route

    source = inspect.getsource(chat_route.chat_completions)
    pipeline_start = source.index("body = _inject_qq_group_activity_context(body)")
    transport_branch = source.index('if body.get("stream"):', source.index("client_requested_stream", pipeline_start))
    required_shared_steps = [
        "step_clean_images_and_save_desc",
        "step_clean_for_forward",
        "step_inject_core_behavior_rules",
        "_inject_channel_nsfw_system",
        "step_inject_du_vitals",
        "step_inject_du_daily",
        "step_inject_pixel_home",
        "step_inject_dynamic_memory",
        "step_inject_summary",
        "step_inject_latest_4_rounds_for_new_window",
        "step_inject_gateway_tools",
        "step_inject_chat_tools",
        "step_inject_forum_tools",
        "step_inject_amap_mcp_tools",
        "step_inject_websearch_tools",
        "step_inject_du_midterm_memory",
        "body = _inject_qq_group_activity_context(body)",
        "step_trim_messages_if_over_limit",
    ]
    for step in required_shared_steps:
        position = source.index(step, pipeline_start)
        assert_true(position < transport_branch, f"{step} must run before stream/nonstream split")
    assert_true(
        source.index("reply_channel = _reply_channel()") < pipeline_start,
        "channel resolution must be shared before the pipeline",
    )
    assert_true(
        "sumitalk_event_sink=_emit_sumitalk_chat_event if is_sumitalk_request else None" in source,
        "native stream must publish rich events through the same SumiTalk job",
    )
    assert_true(
        "sumitalk_rich_events=True" in source and "X-SumiTalk-Rich-Events" in source,
        "worker and shared route must agree on rich-event ownership",
    )


def main() -> None:
    from services import sumitalk_chat_queue as queue
    from services import realtime_publish

    original_publish = realtime_publish.publish_sumitalk_chat_event
    realtime_publish.publish_sumitalk_chat_event = lambda _device_id, _event, window_id="": True
    try:
        with tempfile.TemporaryDirectory(prefix="du-sumitalk-native-stream-") as temp_dir:
            root = Path(temp_dir)
            queue._SUMITALK_CHAT_JOB_DIR = root / "jobs"
            queue.SUMITALK_CHAT_QUEUE_DB = root / "queue.sqlite3"
            queue._SCHEMA_READY = False

            job_id, _payload = test_mode_and_channel_parity(queue)
            test_shared_game_nonstream_boundary(queue)
            test_durable_events_and_endpoints(queue, job_id)
            test_live_dispatch_precedes_async_persistence(queue)
            test_sse_reads_live_broker_without_active_sqlite_polling(queue)
            test_realtime_run_event_broker()
            test_realtime_run_event_subscription_bridge()
            test_worker_stream_and_nonstream(queue)
            test_rich_tool_stream_events()
            test_no_tool_reasoning_stream_events()
            test_sumitalk_stream_completion_does_not_wait_for_archive()
            test_sumitalk_stream_archive_queue_is_fifo()
            test_pixel_home_stream_and_final_parity()
            test_shared_chat_pipeline_structure()
            test_realtime_failure_falls_back_to_durable_log(queue)
            assert_true(queue.flush_sumitalk_chat_live_events(), "all async event persistence should be drained")
    finally:
        realtime_publish.publish_sumitalk_chat_event = original_publish

    print("sumitalk native stream backend contract ok")


if __name__ == "__main__":
    main()
