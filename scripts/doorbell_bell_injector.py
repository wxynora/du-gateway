#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SYSTEM_NOTIFICATION = "📬 新消息：\nDoorbell Commons 信箱里有一封新信。"
CONTEXT_EXPLANATION = (
    "这是一条 Doorbell Commons 的系统通知，不是小玥说的话。"
    "请根据通知内容，自行决定要不要回应。"
)
WAKE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def response(status: str, error_code: str = "") -> tuple[int, dict]:
    payload = {"version": 1, "status": status}
    if error_code:
        payload["error_code"] = error_code
    return (0 if status == "accepted" else 1), payload


def parse_wake(raw: bytes | str) -> dict:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or "")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("expected_one_json_line")
    value = json.loads(lines[0])
    if not isinstance(value, dict) or set(value) != {
        "type",
        "version",
        "wake_id",
        "reason",
        "message",
    }:
        raise ValueError("invalid_wake_envelope")
    if value.get("type") != "doorbell_wake" or value.get("version") != 1:
        raise ValueError("unsupported_wake_envelope")
    wake_id = value.get("wake_id")
    if not isinstance(wake_id, str) or not WAKE_ID_PATTERN.fullmatch(wake_id):
        raise ValueError("invalid_wake_id")
    if value.get("reason") != "mailbox_unread" or value.get("message") != SYSTEM_NOTIFICATION:
        raise ValueError("unsupported_wake_content")
    return {"wake_id": wake_id}


def build_chat_body(wake_id: str, window_id: str) -> dict:
    return {
        "window_id": window_id,
        "client_request_id": f"doorbell-bell:{wake_id}",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_NOTIFICATION,
                "__dynamic__": True,
                "__temporary_dynamic__": True,
            },
            {"role": "user", "content": CONTEXT_EXPLANATION},
        ],
    }


def run_injector(
    raw: bytes | str,
    enqueue: Callable[..., tuple[str, dict | None, object | None]],
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> tuple[int, dict]:
    try:
        wake = parse_wake(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return response("permanent_error", "invalid_wake")

    window_id = str(environment.get("DOORBELL_BELL_WINDOW_ID") or "").strip()
    reply_target = str(environment.get("DOORBELL_BELL_REPLY_TARGET") or "").strip()
    if not window_id or not reply_target:
        return response("permanent_error", "target_not_configured")

    try:
        job_id, error, enqueue_result = enqueue(
            build_chat_body(wake["wake_id"], window_id),
            reply_target=reply_target,
            user_agent="SumiTalk Native Android Doorbell Bell/1.0",
            force_last4="1",
            remote_addr="127.0.0.1",
        )
    except Exception:
        return response("retryable_error", "queue_unavailable")
    if error is not None or not job_id or enqueue_result is None:
        return response("permanent_error", "queue_rejected")
    return response("accepted")


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    try:
        from services.sumitalk_chat_queue import build_sumitalk_chat_job_payload

        exit_code, payload = run_injector(
            sys.stdin.buffer.read(),
            build_sumitalk_chat_job_payload,
        )
    except Exception:
        exit_code, payload = response("retryable_error", "adapter_unavailable")
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
