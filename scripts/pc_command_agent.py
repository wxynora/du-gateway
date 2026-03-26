"""
Windows 电脑控制常驻脚本：
- 轮询网关 GET /api/pc_command
- 执行指令
- 成功项按 id 回执 POST /api/pc_command/done

环境变量：
- GATEWAY_URL=https://your-domain
- PC_COMMAND_TOKEN=与网关一致
- PC_POLL_SECONDS=30
"""

from __future__ import annotations

import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


def _load_env_files() -> None:
    """自动加载环境变量：优先桌面 .env，其次脚本同目录 .env。"""
    candidates: list[Path] = []
    home = Path.home()
    candidates.append(home / "Desktop" / ".env")
    candidates.append(home / "OneDrive" / "Desktop" / ".env")
    candidates.append(Path(__file__).resolve().parent / ".env")
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                load_dotenv(p, override=False)
                print(f"[PC] 已加载环境变量文件: {p}")
        except Exception as e:
            print(f"[PC] 加载环境变量文件失败 {p}: {e}")


_load_env_files()


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


GATEWAY_URL = _env("GATEWAY_URL")
PC_COMMAND_TOKEN = _env("PC_COMMAND_TOKEN")
PC_POLL_SECONDS = max(5, int(_env("PC_POLL_SECONDS", "30") or "30"))


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-PC-Token": PC_COMMAND_TOKEN,
    }


def _audio_endpoint():
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def execute_command(cmd: str) -> bool:
    cmd = (cmd or "").strip()
    if not cmd:
        return False
    print(f"[PC] 执行指令: {cmd}")
    try:
        if cmd == "lock":
            import ctypes

            ctypes.windll.user32.LockWorkStation()
            return True

        if cmd == "shutdown" or cmd.startswith("shutdown:"):
            sec = 60
            if ":" in cmd:
                raw_sec = cmd.split(":", 1)[1].strip()
                if not raw_sec.isdigit():
                    return False
                sec = int(raw_sec)
                if sec < 0 or sec > 86400:
                    return False
            subprocess.run(["shutdown", "/s", "/t", str(sec)], check=False)
            return True

        if cmd == "restart" or cmd.startswith("restart:"):
            sec = 60
            if ":" in cmd:
                raw_sec = cmd.split(":", 1)[1].strip()
                if not raw_sec.isdigit():
                    return False
                sec = int(raw_sec)
                if sec < 0 or sec > 86400:
                    return False
            subprocess.run(["shutdown", "/r", "/t", str(sec)], check=False)
            return True

        if cmd == "sleep":
            subprocess.run(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                check=False,
            )
            return True

        if cmd == "mute":
            vol = _audio_endpoint()
            vol.SetMute(1, None)
            return True

        if cmd.startswith("volume:"):
            raw = cmd.split(":", 1)[1].strip()
            if not raw.isdigit():
                return False
            value = int(raw)
            if value < 0 or value > 100:
                return False
            vol = _audio_endpoint()
            vol.SetMasterVolumeLevelScalar(value / 100.0, None)
            return True

        if cmd.startswith("notify:"):
            from plyer import notification

            parts = cmd.split(":", 2)
            title = (parts[1] if len(parts) > 1 else "渡").strip() or "渡"
            content = (parts[2] if len(parts) > 2 else "").strip()
            notification.notify(title=title, message=content, timeout=5)
            return True

        if cmd.startswith("open:"):
            parts = cmd.split(":", 2)
            app = (parts[1] if len(parts) > 1 else "").strip()
            if not app:
                return False
            note_text = (parts[2] if len(parts) > 2 else "").strip()
            if app.lower() == "notepad" and note_text:
                # 预填内容写入桌面临时文件，再用记事本打开，便于继续编辑
                desktop = Path.home() / "Desktop"
                desktop_alt = Path.home() / "OneDrive" / "Desktop"
                base_dir = desktop if desktop.exists() else desktop_alt
                if not base_dir.exists():
                    base_dir = Path.cwd()
                note_path = base_dir / "du_notepad_note.txt"
                note_path.write_text(note_text + "\n", encoding="utf-8")
                subprocess.Popen(["notepad.exe", str(note_path)], shell=False)
                return True
            subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
            return True

        if cmd.startswith("url:"):
            url = cmd.split(":", 1)[1].strip()
            if not url:
                return False
            webbrowser.open(url)
            return True

        if cmd == "media:play":
            import pyautogui

            pyautogui.press("playpause")
            return True

        print(f"[PC] 未支持指令: {cmd}")
        return False
    except Exception as e:
        print(f"[PC] 执行失败 {cmd}: {e}")
        return False


def poll_once() -> None:
    if not GATEWAY_URL or not PC_COMMAND_TOKEN:
        print("[PC] 缺少 GATEWAY_URL 或 PC_COMMAND_TOKEN，无法轮询")
        return
    base = GATEWAY_URL.rstrip("/")
    try:
        res = requests.get(
            f"{base}/api/pc_command",
            headers=_headers(),
            timeout=20,
        )
        if res.status_code != 200:
            print(f"[PC] 拉取失败 status={res.status_code} body={(res.text or '')[:200]}")
            return
        data: dict[str, Any] = res.json() if res.content else {}
        pending = data.get("pending") if isinstance(data, dict) else []
        if not isinstance(pending, list) or not pending:
            return
        done_ids: list[str] = []
        for item in pending:
            if not isinstance(item, dict):
                continue
            cmd_id = str(item.get("id") or "").strip()
            cmd = str(item.get("cmd") or "").strip()
            if not cmd_id or not cmd:
                continue
            ok = execute_command(cmd)
            if ok:
                done_ids.append(cmd_id)
        if done_ids:
            ack = requests.post(
                f"{base}/api/pc_command/done",
                headers=_headers(),
                json={"doneIds": done_ids},
                timeout=20,
            )
            if ack.status_code != 200:
                print(f"[PC] 回执失败 status={ack.status_code} body={(ack.text or '')[:200]}")
                return
            payload = ack.json() if ack.content else {}
            removed = payload.get("removedCount") if isinstance(payload, dict) else 0
            print(f"[PC] 回执成功 done={len(done_ids)} removed={removed}")
    except Exception as e:
        print(f"[PC] 轮询异常: {e}")


def main() -> None:
    print(f"[PC] 启动完成，每 {PC_POLL_SECONDS} 秒轮询一次")
    if not GATEWAY_URL or not PC_COMMAND_TOKEN:
        print("[PC] 请在桌面 .env（或系统环境变量）中设置 GATEWAY_URL 与 PC_COMMAND_TOKEN")
    while True:
        poll_once()
        time.sleep(PC_POLL_SECONDS)


if __name__ == "__main__":
    main()
