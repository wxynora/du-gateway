"""
电脑活动上报常驻脚本（Windows / macOS）。

只负责读取操作系统最后一次键鼠输入时间，并在该时间变化时 POST
到网关 `/api/pc_activity`。不轮询、不执行任何电脑指令。
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from urllib import error, request


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


GATEWAY_URL = _env("GATEWAY_URL")
PC_COMMAND_TOKEN = _env("PC_COMMAND_TOKEN")
PC_ACTIVITY_POLL_SECONDS = max(
    5,
    int(_env("PC_ACTIVITY_POLL_SECONDS", "30") or "30"),
)
PC_DEVICE_ID = _env("PC_DEVICE_ID", platform.node() or "pc")


def _log(message: str) -> None:
    print(message, flush=True)


def _windows_idle_seconds() -> float | None:
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    now_tick = int(ctypes.windll.kernel32.GetTickCount())
    idle_ms = (now_tick - int(info.dwTime)) & 0xFFFFFFFF
    return idle_ms / 1000.0


def _macos_idle_seconds() -> float | None:
    result = subprocess.run(
        ["ioreg", "-c", "IOHIDSystem"],
        check=False,
        timeout=5,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', result.stdout or "")
    if not match:
        return None
    return int(match.group(1)) / 1_000_000_000.0


def os_last_input_snapshot() -> tuple[str, float] | None:
    try:
        if sys.platform.startswith("win"):
            idle_seconds = _windows_idle_seconds()
        elif sys.platform == "darwin":
            idle_seconds = _macos_idle_seconds()
        else:
            return None
    except Exception as exc:
        _log(f"[PC-ACTIVITY] 读取系统输入状态失败: {exc}")
        return None
    if idle_seconds is None:
        return None
    observed_at = datetime.now().astimezone()
    raw_last_input_at = observed_at - timedelta(seconds=max(0.0, idle_seconds))
    last_input_at = datetime.fromtimestamp(
        round(raw_last_input_at.timestamp()),
        tz=observed_at.tzinfo,
    )
    return last_input_at.isoformat(timespec="seconds"), max(0.0, idle_seconds)


def report_activity(last_input_at: str, idle_seconds: float) -> bool:
    payload = json.dumps(
        {
            "device_id": PC_DEVICE_ID,
            "platform": sys.platform,
            "last_input_at": last_input_at,
            "idle_seconds": round(idle_seconds, 3),
        }
    ).encode("utf-8")
    req = request.Request(
        f"{GATEWAY_URL.rstrip('/')}/api/pc_activity",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-PC-Token": PC_COMMAND_TOKEN,
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return True
            _log(f"[PC-ACTIVITY] 上报失败 status={response.status}")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        _log(f"[PC-ACTIVITY] 上报失败 status={exc.code} body={body}")
    except Exception as exc:
        _log(f"[PC-ACTIVITY] 上报异常: {exc}")
    return False


def main() -> None:
    if not GATEWAY_URL or not PC_COMMAND_TOKEN:
        raise SystemExit("[PC-ACTIVITY] 缺少 GATEWAY_URL 或 PC_COMMAND_TOKEN")
    _log(f"[PC-ACTIVITY] 启动完成，每 {PC_ACTIVITY_POLL_SECONDS} 秒检查一次")
    last_reported_input_at = ""
    while True:
        snapshot = os_last_input_snapshot()
        if snapshot:
            last_input_at, idle_seconds = snapshot
            if last_input_at != last_reported_input_at:
                if report_activity(last_input_at, idle_seconds):
                    last_reported_input_at = last_input_at
        time.sleep(PC_ACTIVITY_POLL_SECONDS)


if __name__ == "__main__":
    main()
