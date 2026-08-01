#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_wake_envelope(raw: bytes | str) -> dict:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("expected_one_json_line")
    data = json.loads(lines[0])
    if not isinstance(data, dict):
        raise ValueError("wake_envelope_must_be_object")
    if data.get("version") != 1 or data.get("type") != "garden_wake":
        raise ValueError("unsupported_wake_envelope")
    reason = str(data.get("reason") or "").strip()
    message = str(data.get("message") or "").strip()
    if not reason or not message:
        raise ValueError("wake_reason_and_message_required")
    return {
        "version": 1,
        "type": "garden_wake",
        "reason": reason,
        "message": message,
    }


def run_injector(raw: bytes | str, handler: Callable[[str, str], dict]) -> tuple[int, dict]:
    envelope = parse_wake_envelope(raw)
    result = handler(envelope["reason"], envelope["message"])
    if not isinstance(result, dict):
        result = {"ok": False, "injected": False, "delivered": False, "error": "invalid_handler_result"}
    response = {
        "ok": bool(result.get("ok")),
        "injected": bool(result.get("injected")),
        "delivered": bool(result.get("delivered")),
        "channel": str(result.get("channel") or ""),
        "window_id": str(result.get("window_id") or ""),
    }
    error = str(result.get("error") or "").strip()
    if error:
        response["error"] = error
    return (0 if response["injected"] else 1), response


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    try:
        from services.telegram_proactive import handle_galatea_garden_wake

        exit_code, response = run_injector(sys.stdin.buffer.read(), handle_galatea_garden_wake)
    except Exception as e:
        exit_code = 1
        response = {
            "ok": False,
            "injected": False,
            "delivered": False,
            "error": str(e) or e.__class__.__name__,
        }
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
