#!/usr/bin/env python3
"""Focused backend regressions for SumiTalk streaming <voice> sidecars."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_eq(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def make_state(job_id: str) -> dict:
    now = time.time()
    return {
        "id": job_id,
        "status": "running",
        "created_ts": now,
        "updated_ts": now,
        "created_at": "2026-07-18T00:00:00+08:00",
        "updated_at": "2026-07-18T00:00:00+08:00",
        "window_id": "voice-sidecar-test",
        "reply_target": "device-test",
        "execution_mode": "stream",
    }


def fake_mp3(frame_count: int = 100) -> bytes:
    frame_header = bytes.fromhex("FFFB9000")
    frame = frame_header + (b"\0" * (417 - len(frame_header)))
    return frame * max(1, int(frame_count))


def wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for asynchronous sidecar work")


def response_with_chunks(chunks: list[str]):
    from flask import Response

    def generate():
        for index, text in enumerate(chunks):
            finish_reason = "stop" if index == len(chunks) - 1 else None
            yield "data: " + json.dumps(
                {
                    "id": "voice-stream-test",
                    "model": "test-model",
                    "choices": [
                        {
                            "delta": {"content": text},
                            "finish_reason": finish_reason,
                        }
                    ],
                },
                ensure_ascii=False,
            ) + "\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), content_type="text/event-stream")


def test_parser_across_deltas(sidecar) -> None:
    job_id = "1" * 32
    part_id = "assistant-text-1-1"
    first = sidecar.feed_sumitalk_voice_delta(job_id, part_id, "前文<vo")
    second = sidecar.feed_sumitalk_voice_delta(job_id, part_id, "ice>这是一句")
    third = sidecar.feed_sumitalk_voice_delta(job_id, part_id, "语音</vo")
    fourth = sidecar.feed_sumitalk_voice_delta(job_id, part_id, "ice>后文")
    finished = sidecar.finish_sumitalk_voice_part(job_id, part_id)
    assert_eq(first.visible_text, "前文", "text before a split opening tag must stream immediately")
    assert_eq(second.visible_text + third.visible_text, "", "voice text must stay out of visible deltas")
    assert_eq(fourth.visible_text, "后文", "text after a split closing tag must remain visible")
    assert_eq(len(fourth.completed), 1, "one complete voice tag must produce one sidecar")
    assert_eq(fourth.completed[0].voice_index, 0, "the first voice index must be stable")
    assert_eq(fourth.completed[0].transcript, "这是一句语音", "voice transcript must survive delta splits")
    assert_eq(finished.visible_text, "", "a complete tag must leave no buffered text")
    assert_eq(
        sidecar.strip_complete_sumitalk_voice_tags("前文<voice>这是一句语音</voice>后文"),
        "前文后文",
        "terminal text must use the same visibility rule",
    )


def test_slow_tts_after_assistant_final(queue, sidecar) -> None:
    job_id = "2" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id))
    tts_started = threading.Event()
    release_tts = threading.Event()
    tts_calls = []

    def blocked_tts(transcript: str) -> bytes:
        tts_calls.append(transcript)
        tts_started.set()
        release_tts.wait(3.0)
        return fake_mp3()

    sidecar._tts_audio_bytes = blocked_tts
    sidecar._upload_audio = lambda audio, task_id: {
        "key": f"sumitalk/chat_media/audio/test/{task_id}.mp3",
        "contentType": "audio/mpeg",
        "size": len(audio),
    }
    sidecar._audio_public_url = lambda key: f"https://media.test/raw?key={key}"

    status, data = queue._consume_sumitalk_chat_stream(
        response_with_chunks(["正文<vo", "ice>晚到语音</voice>", "继续正文"]),
        job_id,
    )
    assert_eq(status, 200, "the text stream must complete normally")
    assert_eq(
        data["choices"][0]["message"]["content"],
        "正文继续正文",
        "voice tags must be stripped from the persisted assistant text",
    )
    assert_true(tts_started.wait(1.0), "TTS must start as soon as the closing tag is recognized")
    assert_true(
        queue.finalize_sumitalk_chat_job(
            job_id,
            "done",
            state_patch={"status_code": 200, "response": data},
            event_payload={
                "part_id": "assistant-final",
                "text": "正文继续正文",
                "role": "assistant",
                "finish_reason": "stop",
            },
            live=True,
        ),
        "assistant_final must not wait for TTS",
    )
    assert_true(queue.flush_sumitalk_chat_live_events(), "assistant_final must reach the durable event log")
    before_audio = queue.list_sumitalk_chat_job_events(job_id, limit=100)
    assert_eq(before_audio[-1]["kind"], "assistant_final", "text completion must be observable while TTS is blocked")
    assert_eq(queue.read_sumitalk_chat_job_state(job_id)["status"], "done", "the chat job must already be done")

    release_tts.set()
    wait_until(lambda: sidecar.pending_sumitalk_voice_sidecar_count(job_id) == 0)
    events = queue.list_sumitalk_chat_job_events(job_id, limit=100)
    audio_events = [event for event in events if event.get("kind") == "assistant_audio_ready"]
    assert_eq(len(audio_events), 1, "the completed voice must emit exactly one media event")
    audio = audio_events[0]
    assert_true(int(audio.get("seq") or 0) > int(before_audio[-1].get("seq") or 0), "audio may arrive after final text")
    assert_eq(audio.get("part_id"), "assistant-final:voice:0", "audio part id must include the voice index")
    assert_eq(audio.get("voice_index"), 0, "voice index must be preserved")
    assert_eq(audio.get("transcript"), "晚到语音", "audio event must keep the transcript")
    assert_eq(audio.get("mime"), "audio/mpeg", "audio event must expose its MIME type")
    assert_true(int(audio.get("duration_ms") or 0) > 0, "audio event must contain a real nonzero duration")
    assert_true(bool(audio.get("media_id")) and bool(audio.get("audio_url")), "audio media must be addressable")
    assert_eq(tts_calls, ["晚到语音"], "one voice segment must invoke TTS once")

    from flask import Blueprint, Flask
    from routes.miniapp.sumitalk_chat_jobs import register_routes

    app = Flask("sumitalk-voice-sidecar-sse")
    blueprint = Blueprint("sumitalk_voice_sidecar_sse", __name__, url_prefix="/miniapp-api")
    register_routes(blueprint)
    app.register_blueprint(blueprint)
    stream = app.test_client().get(
        f"/miniapp-api/sumitalk-chat-jobs/{job_id}/events/stream?after_seq=0",
        buffered=True,
    )
    streamed = [
        json.loads(line[6:])
        for line in stream.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]
    streamed_kinds = [event.get("kind") for event in streamed]
    assert_true("assistant_final" in streamed_kinds, "reconnect SSE must replay assistant_final")
    assert_true("assistant_audio_ready" in streamed_kinds, "reconnect SSE must continue past final to late audio")
    assert_true(
        streamed_kinds.index("assistant_final") < streamed_kinds.index("assistant_audio_ready"),
        "reconnect SSE must preserve terminal and sidecar sequence order",
    )


def test_persistent_concurrent_idempotency(queue, sidecar) -> None:
    job_id = "3" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id))
    tts_started = threading.Event()
    release_tts = threading.Event()
    call_lock = threading.Lock()
    calls = 0

    def blocked_tts(_transcript: str) -> bytes:
        nonlocal calls
        with call_lock:
            calls += 1
        tts_started.set()
        release_tts.wait(3.0)
        return fake_mp3(80)

    sidecar._tts_audio_bytes = blocked_tts
    sidecar._upload_audio = lambda audio, task_id: {
        "key": f"sumitalk/chat_media/audio/test/{task_id}.mp3",
        "size": len(audio),
    }
    sidecar._audio_public_url = lambda key: f"https://media.test/{key}"
    with ThreadPoolExecutor(max_workers=12) as executor:
        task_ids = list(
            executor.map(
                lambda _index: sidecar.schedule_sumitalk_voice_sidecar(
                    job_id,
                    "assistant-text-2-1",
                    0,
                    "并发只生成一次",
                ),
                range(24),
            )
        )
    assert_eq(len(set(task_ids)), 1, "all consumers must resolve to the same persistent task id")
    assert_true(tts_started.wait(1.0), "the claimed sidecar must start")
    assert_eq(calls, 1, "persistent SQLite claim must prevent duplicate TTS across consumers")
    queue.finalize_sumitalk_chat_job(
        job_id,
        "done",
        state_patch={"status_code": 200, "response": {"choices": []}},
        event_payload={"text": "正文完成", "role": "assistant", "finish_reason": "stop"},
        live=True,
    )
    release_tts.set()
    wait_until(lambda: sidecar.pending_sumitalk_voice_sidecar_count(job_id) == 0)
    assert_eq(calls, 1, "terminal notification and reconnect recovery must not regenerate audio")
    assert_eq(
        [event.get("kind") for event in queue.list_sumitalk_chat_job_events(job_id, limit=100)].count(
            "assistant_audio_ready"
        ),
        1,
        "duplicate consumers must not duplicate the ready event",
    )


def test_tts_failure_does_not_fail_chat(queue, sidecar) -> None:
    job_id = "4" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id))
    sidecar._tts_audio_bytes = lambda _transcript: b""
    task_id = sidecar.schedule_sumitalk_voice_sidecar(job_id, "assistant-final", 0, "失败语音")
    queue.finalize_sumitalk_chat_job(
        job_id,
        "done",
        state_patch={
            "status_code": 200,
            "response": {"choices": [{"message": {"role": "assistant", "content": "正文成功"}}]},
        },
        event_payload={"text": "正文成功", "role": "assistant", "finish_reason": "stop"},
        live=True,
    )
    wait_until(lambda: sidecar.pending_sumitalk_voice_sidecar_count(job_id) == 0)
    state = queue.read_sumitalk_chat_job_state(job_id)
    assert_eq(state.get("status"), "done", "TTS failure must not change the completed chat status")
    events = queue.list_sumitalk_chat_job_events(job_id, limit=100)
    assert_eq(events[-1].get("kind"), "assistant_audio_failed", "TTS failure must be a sidecar event")
    assert_eq(
        [event.get("kind") for event in events].count("assistant_final"),
        1,
        "TTS failure must not replace or duplicate assistant_final",
    )
    assert_eq(sidecar.get_sumitalk_voice_sidecar(task_id).get("status"), "failed", "failure state must be durable")


def test_ready_audio_waits_for_text_terminal(queue, sidecar) -> None:
    job_id = "7" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id))
    sidecar._tts_audio_bytes = lambda _transcript: fake_mp3(60)
    sidecar._upload_audio = lambda audio, task_id: {
        "key": f"sumitalk/chat_media/audio/test/{task_id}.mp3",
        "size": len(audio),
    }
    sidecar._audio_public_url = lambda key: f"https://media.test/{key}"
    task_id = sidecar.schedule_sumitalk_voice_sidecar(job_id, "assistant-final", 0, "先生成完")
    wait_until(lambda: (sidecar.get_sumitalk_voice_sidecar(task_id) or {}).get("status") == "ready")
    assert_true(
        not any(
            event.get("kind") == "assistant_audio_ready"
            for event in queue.list_sumitalk_chat_job_events(job_id, limit=100)
        ),
        "ready audio must not overtake assistant_final",
    )
    queue.finalize_sumitalk_chat_job(
        job_id,
        "done",
        state_patch={"status_code": 200, "response": {"choices": []}},
        event_payload={"text": "正文完成", "role": "assistant", "finish_reason": "stop"},
        live=True,
    )
    wait_until(lambda: sidecar.pending_sumitalk_voice_sidecar_count(job_id) == 0)
    kinds = [event.get("kind") for event in queue.list_sumitalk_chat_job_events(job_id, limit=100)]
    assert_true(
        kinds.index("assistant_final") < kinds.index("assistant_audio_ready"),
        "terminal notification must release already-ready audio in sequence order",
    )


def test_plain_text_is_unchanged(queue, sidecar) -> None:
    job_id = "5" * 32
    queue.write_sumitalk_chat_job_state(make_state(job_id))
    status, data = queue._consume_sumitalk_chat_stream(
        response_with_chunks(["普通", "正文\n保持原样"]),
        job_id,
    )
    assert_eq(status, 200, "plain stream must still succeed")
    assert_eq(
        data["choices"][0]["message"]["content"],
        "普通正文\n保持原样",
        "plain text must not be rewritten by the voice parser",
    )
    assert_eq(sidecar.pending_sumitalk_voice_sidecar_count(job_id), 0, "plain text must not create a sidecar")


def test_broker_keeps_post_terminal_sidecars() -> None:
    from services.sumitalk_live_event_broker import SumiTalkRunEventBroker

    async def scenario() -> list[str]:
        broker = SumiTalkRunEventBroker(max_events_per_job=32)
        job_id = "6" * 32
        await broker.publish({"job_id": job_id, "seq": 1, "kind": "assistant_final"})
        await broker.publish({"job_id": job_id, "seq": 2, "kind": "assistant_audio_ready"})
        stream = broker.subscribe(job_id, 0)
        first = await stream.__anext__()
        second = await stream.__anext__()
        await stream.aclose()
        return [str(first.get("kind") or ""), str(second.get("kind") or "")]

    assert_eq(
        asyncio.run(scenario()),
        ["assistant_final", "assistant_audio_ready"],
        "the live broker must not close before a late media sidecar",
    )


def main() -> None:
    from services import realtime_publish
    from services import sumitalk_chat_queue as queue
    from services import sumitalk_voice_sidecar as sidecar

    originals = {
        "publish": realtime_publish.publish_sumitalk_chat_event,
        "tts": sidecar._tts_audio_bytes,
        "upload": sidecar._upload_audio,
        "url": sidecar._audio_public_url,
    }
    realtime_publish.publish_sumitalk_chat_event = lambda _device_id, _event, window_id="": True
    try:
        with tempfile.TemporaryDirectory(prefix="du-sumitalk-voice-sidecar-") as temp_dir:
            root = Path(temp_dir)
            queue._SUMITALK_CHAT_JOB_DIR = root / "jobs"
            queue.SUMITALK_CHAT_QUEUE_DB = root / "queue.sqlite3"
            queue._SCHEMA_READY = False
            sidecar.discard_sumitalk_voice_stream("")
            test_parser_across_deltas(sidecar)
            test_slow_tts_after_assistant_final(queue, sidecar)
            test_persistent_concurrent_idempotency(queue, sidecar)
            test_tts_failure_does_not_fail_chat(queue, sidecar)
            test_ready_audio_waits_for_text_terminal(queue, sidecar)
            test_plain_text_is_unchanged(queue, sidecar)
            test_broker_keeps_post_terminal_sidecars()
            assert_true(queue.flush_sumitalk_chat_live_events(), "event persistence must drain")
    finally:
        realtime_publish.publish_sumitalk_chat_event = originals["publish"]
        sidecar._tts_audio_bytes = originals["tts"]
        sidecar._upload_audio = originals["upload"]
        sidecar._audio_public_url = originals["url"]

    print("sumitalk stream voice sidecar ok")


if __name__ == "__main__":
    main()
