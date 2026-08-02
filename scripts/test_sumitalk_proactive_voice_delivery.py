#!/usr/bin/env python3
"""Focused regressions for backend SumiTalk proactive voice delivery."""

from __future__ import annotations

import copy
import sqlite3
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


def fake_mp3(frame_count: int = 80) -> bytes:
    frame_header = bytes.fromhex("FFFB9000")
    frame = frame_header + (b"\0" * (417 - len(frame_header)))
    return frame * max(1, int(frame_count))


def wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for proactive voice sidecar")


def test_complete_voice_extraction(sidecar) -> None:
    voices = sidecar.extract_complete_sumitalk_voices(
        "先说文字<voice>第一句</voice><voice>   </voice><VOICE>第二句</VOICE>"
    )
    assert_eq(
        [(voice.voice_index, voice.transcript) for voice in voices],
        [(0, "第一句"), (2, "第二句")],
        "complete proactive voice tags must preserve stable source indexes",
    )


def test_existing_sidecar_schema_migrates_once(sidecar, queue, temp_dir: Path) -> None:
    old_sidecar_db = sidecar.SUMITALK_CHAT_QUEUE_DB
    old_queue_db = queue.SUMITALK_CHAT_QUEUE_DB
    sidecar_db = temp_dir / "legacy-sidecars.sqlite3"
    with sqlite3.connect(sidecar_db) as conn:
        conn.execute(
            """
            CREATE TABLE sumitalk_chat_voice_sidecars (
                task_id TEXT NOT NULL UNIQUE,
                job_id TEXT NOT NULL,
                source_part_id TEXT NOT NULL,
                voice_index INTEGER NOT NULL,
                event_part_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                lease_token TEXT,
                locked_at REAL,
                media_id TEXT,
                remote_key TEXT,
                audio_url TEXT,
                mime TEXT,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                event_emitted INTEGER NOT NULL DEFAULT 0,
                event_seq INTEGER,
                event_lease_token TEXT,
                event_locked_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(job_id, source_part_id, voice_index)
            )
            """
        )
    sidecar.SUMITALK_CHAT_QUEUE_DB = sidecar_db
    queue.SUMITALK_CHAT_QUEUE_DB = sidecar_db
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: sidecar._ensure_schema(), range(8)))
        with sqlite3.connect(sidecar_db) as conn:
            columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(sumitalk_chat_voice_sidecars)"
                ).fetchall()
            }
        assert_true(
            {"delivery_kind", "target_device_id", "target_message_id"} <= columns,
            "existing sidecar databases must receive the proactive delivery columns",
        )
    finally:
        sidecar.SUMITALK_CHAT_QUEUE_DB = old_sidecar_db
        queue.SUMITALK_CHAT_QUEUE_DB = old_queue_db


def test_followup_queues_text_before_voice_schedule(
    conversation_followup,
    history,
    realtime_publish,
) -> None:
    old_target_resolver = conversation_followup._resolve_sumitalk_target_device_id
    old_window_resolver = conversation_followup._resolve_sumitalk_delivery_window_id
    old_schedule = conversation_followup._schedule_sumitalk_proactive_voice_actions
    old_append_action = conversation_followup.r2_store.append_app_action
    old_load = history._load_sumitalk_histories
    old_merge = history._merge_sumitalk_messages
    old_save = history._save_sumitalk_histories
    old_storage_key = history._sumitalk_history_storage_key
    old_publish = realtime_publish.publish_assistant_message
    events: list[tuple[str, str]] = []
    stored: dict = {}

    def fake_append_action(action_type, payload, **_kwargs):
        events.append(("action", action_type))
        return {"id": "text-action", "duplicate": False}, None

    def fake_schedule(device_id: str, message_id: str, content: str):
        assert_eq(events, [("action", "deliver_chat_message")], "text action must be queued first")
        assert_eq(device_id, "device-followup", "voice schedule must use the resolved device")
        assert_true(message_id.startswith("assistant-followup-"), "message id must remain stable")
        assert_eq(content, "<voice>后端生成这句语音</voice>", "voice source must stay intact")
        events.append(("schedule", message_id))
        return ("voice-task",)

    conversation_followup._resolve_sumitalk_target_device_id = lambda _value: "device-followup"
    conversation_followup._resolve_sumitalk_delivery_window_id = (
        lambda _window_id, _device_id: "window-followup"
    )
    conversation_followup._schedule_sumitalk_proactive_voice_actions = fake_schedule
    conversation_followup.r2_store.append_app_action = fake_append_action
    history._load_sumitalk_histories = lambda: copy.deepcopy(stored)
    history._merge_sumitalk_messages = lambda current, incoming: list(current) + list(incoming)
    history._sumitalk_history_storage_key = lambda _device_id, _window_id: "history-key"

    def fake_save(data) -> bool:
        stored.clear()
        stored.update(copy.deepcopy(data))
        return True

    history._save_sumitalk_histories = fake_save
    realtime_publish.publish_assistant_message = lambda *_args, **_kwargs: True
    try:
        ok = conversation_followup._append_sumitalk_assistant_message_to_device(
            "preferred-device",
            "<voice>后端生成这句语音</voice>",
            created_at="2026-07-29T12:00:00+08:00",
            window_id="requested-window",
        )
        assert_true(ok, "proactive message delivery must succeed")
        assert_eq(events[0], ("action", "deliver_chat_message"), "text must be first")
        assert_eq(events[1][0], "schedule", "voice scheduling must follow the text action")
    finally:
        conversation_followup._resolve_sumitalk_target_device_id = old_target_resolver
        conversation_followup._resolve_sumitalk_delivery_window_id = old_window_resolver
        conversation_followup._schedule_sumitalk_proactive_voice_actions = old_schedule
        conversation_followup.r2_store.append_app_action = old_append_action
        history._load_sumitalk_histories = old_load
        history._merge_sumitalk_messages = old_merge
        history._save_sumitalk_histories = old_save
        history._sumitalk_history_storage_key = old_storage_key
        realtime_publish.publish_assistant_message = old_publish


def test_proactive_sidecar_is_persistently_idempotent(sidecar, queue, r2_store, temp_dir: Path) -> None:
    old_sidecar_db = sidecar.SUMITALK_CHAT_QUEUE_DB
    old_queue_db = queue.SUMITALK_CHAT_QUEUE_DB
    old_tts = sidecar._tts_audio_bytes
    old_upload = sidecar._upload_audio
    old_public_url = sidecar._audio_public_url
    old_append_action = r2_store.append_app_action
    sidecar_db = temp_dir / "proactive-sidecars.sqlite3"
    sidecar.SUMITALK_CHAT_QUEUE_DB = sidecar_db
    queue.SUMITALK_CHAT_QUEUE_DB = sidecar_db
    tts_calls: list[str] = []
    queued_actions: list[dict] = []
    lock = threading.Lock()

    def fake_tts(transcript: str) -> bytes:
        with lock:
            tts_calls.append(transcript)
        return fake_mp3()

    def fake_append_action(action_type, payload, **kwargs):
        with lock:
            queued_actions.append(
                {
                    "type": action_type,
                    "payload": copy.deepcopy(payload),
                    "kwargs": copy.deepcopy(kwargs),
                }
            )
        return {"id": f"action-{len(queued_actions)}", "duplicate": False}, None

    sidecar._tts_audio_bytes = fake_tts
    sidecar._upload_audio = lambda audio, task_id: {
        "id": f"media-{task_id}",
        "key": f"sumitalk/chat_media/audio/test/{task_id}.mp3",
        "size": len(audio),
    }
    sidecar._audio_public_url = lambda key: f"https://media.test/{key}"
    r2_store.append_app_action = fake_append_action
    try:
        def schedule_once() -> str:
            return sidecar.schedule_sumitalk_proactive_voice_sidecar(
                device_id="device-proactive",
                message_id="assistant-followup-stable",
                voice_index=0,
                transcript="醒了就回我一句",
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            task_ids = list(pool.map(lambda _: schedule_once(), range(12)))
        assert_eq(len(set(task_ids)), 1, "duplicate scheduling must resolve to one stable task")
        task_id = task_ids[0]
        assert_true(bool(task_id), "proactive voice task id must be created")
        wait_until(
            lambda: bool(
                (sidecar.get_sumitalk_voice_sidecar(task_id) or {}).get("event_emitted")
            )
        )
        assert_eq(tts_calls, ["醒了就回我一句"], "duplicate scheduling must call TTS once")
        assert_eq(len(queued_actions), 1, "duplicate scheduling must enqueue one audio action")
        action = queued_actions[0]
        assert_eq(action["type"], "deliver_chat_audio", "sidecar must use the App audio action")
        assert_eq(
            action["payload"]["message_id"],
            "assistant-followup-stable",
            "audio must attach to the original proactive message",
        )
        assert_eq(action["payload"]["voice_index"], 0, "voice index must remain stable")
        assert_eq(action["payload"]["transcript"], "醒了就回我一句", "transcript must survive TTS")
        assert_true(
            action["payload"]["part_id"].endswith(":voice:0"),
            "audio part id must be deterministic",
        )
        assert_eq(
            action["kwargs"]["idempotency_key"],
            (
                "chat-audio:device-proactive:assistant-followup-stable:"
                f"{action['payload']['part_id']}"
            ),
            "queued audio action must have a stable idempotency key",
        )

        schedule_once()
        time.sleep(0.05)
        assert_eq(tts_calls, ["醒了就回我一句"], "completed retries must not rerun TTS")
        assert_eq(len(queued_actions), 1, "completed retries must not enqueue another audio action")
    finally:
        sidecar.SUMITALK_CHAT_QUEUE_DB = old_sidecar_db
        queue.SUMITALK_CHAT_QUEUE_DB = old_queue_db
        sidecar._tts_audio_bytes = old_tts
        sidecar._upload_audio = old_upload
        sidecar._audio_public_url = old_public_url
        r2_store.append_app_action = old_append_action


def test_audio_action_contract_and_done_idempotency(
    app_action_store,
    runtime_sqlite,
    temp_dir: Path,
) -> None:
    old_runtime_db = runtime_sqlite.RUNTIME_STATE_DB
    old_schema_ready = runtime_sqlite._SCHEMA_READY
    old_bootstrapped = app_action_store._APP_ACTION_BOOTSTRAPPED
    old_publish = app_action_store._publish_app_action
    runtime_sqlite.RUNTIME_STATE_DB = temp_dir / "runtime-state.sqlite3"
    runtime_sqlite._SCHEMA_READY = False
    app_action_store._APP_ACTION_BOOTSTRAPPED = True
    app_action_store._publish_app_action = lambda _item: None
    payload = {
        "message_id": "assistant-followup-contract",
        "part_id": "proactive-text-assistant-followup-contract:voice:0",
        "sidecar_task_id": "sumitalk-voice-contract",
        "media_id": "media-contract",
        "remote_url": "/miniapp-api/chat-media/raw-public?key=voice.mp3",
        "mime": "audio/mpeg",
        "duration_millis": 1800,
        "transcript": "这是一条主动语音",
        "voice_index": 0,
    }
    try:
        runtime_sqlite.ensure_schema()
        first, error = app_action_store.append_app_action(
            "deliver_chat_audio",
            payload,
            device_id="device-contract",
            expires_in_sec=30 * 24 * 60 * 60,
            source="proactive_followup",
            idempotency_key="chat-audio-contract",
        )
        assert_true(first is not None and error is None, "audio action must be accepted")
        report = app_action_store.report_app_actions(
            [{"id": first["id"], "status": "done", "detail": {"attached": True}}],
            device_id="device-contract",
        )
        assert_eq(report.get("processed"), 1, "audio action completion must be recorded")
        duplicate, error = app_action_store.append_app_action(
            "deliver_chat_audio",
            payload,
            device_id="device-contract",
            expires_in_sec=30 * 24 * 60 * 60,
            source="proactive_followup",
            idempotency_key="chat-audio-contract",
        )
        assert_true(error is None and duplicate is not None, "completed audio retry must resolve")
        assert_eq(duplicate["id"], first["id"], "completed retry must reuse the same action")
        assert_true(duplicate.get("duplicate"), "completed retry must be marked duplicate")
        assert_eq(
            duplicate["payload"],
            payload,
            "audio payload must preserve the App's existing field contract",
        )
    finally:
        runtime_sqlite.RUNTIME_STATE_DB = old_runtime_db
        runtime_sqlite._SCHEMA_READY = old_schema_ready
        app_action_store._APP_ACTION_BOOTSTRAPPED = old_bootstrapped
        app_action_store._publish_app_action = old_publish


def main() -> None:
    from routes.miniapp import sumitalk_history as history
    from services import sumitalk_chat_queue as queue
    from services import sumitalk_voice_sidecar as sidecar
    from services import conversation_followup, realtime_publish
    from storage import app_action_store, r2_store, runtime_sqlite

    with tempfile.TemporaryDirectory(prefix="sumitalk-proactive-voice-") as temp:
        temp_dir = Path(temp)
        test_complete_voice_extraction(sidecar)
        test_existing_sidecar_schema_migrates_once(sidecar, queue, temp_dir)
        test_followup_queues_text_before_voice_schedule(
            conversation_followup,
            history,
            realtime_publish,
        )
        test_proactive_sidecar_is_persistently_idempotent(sidecar, queue, r2_store, temp_dir)
        test_audio_action_contract_and_done_idempotency(app_action_store, runtime_sqlite, temp_dir)
    print("SumiTalk proactive voice delivery tests passed")


if __name__ == "__main__":
    main()
