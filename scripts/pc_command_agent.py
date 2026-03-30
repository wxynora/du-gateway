"""
电脑控制常驻脚本（Windows / macOS）：
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
import sys
import time
import webbrowser
from math import ceil
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


def _load_env_files() -> None:
    """自动加载环境变量：只读取下载目录下的 .env。"""
    env_path = Path.home() / "Downloads" / ".env"
    try:
        if env_path.exists() and env_path.is_file():
            load_dotenv(env_path, override=False)
            print(f"[PC] 已加载环境变量文件: {env_path}")
    except Exception as e:
        print(f"[PC] 加载环境变量文件失败 {env_path}: {e}")


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


def _safe_text(s: str) -> str:
    text = str(s or "")
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return text
    except Exception:
        return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _log(msg: str) -> None:
    try:
        print(_safe_text(msg), flush=True)
    except Exception:
        try:
            print(str(msg).encode("ascii", errors="replace").decode("ascii", errors="replace"), flush=True)
        except Exception:
            pass


def _audio_endpoint():
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _run_command(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def _run_osascript(script: str, timeout: int = 15) -> bool:
    try:
        res = _run_command(["osascript", "-e", script], timeout=timeout)
        if res.returncode == 0:
            return True
        _log(f"[PC] osascript 失败 code={res.returncode} stderr={(res.stderr or '').strip()[:300]}")
        return False
    except Exception as e:
        _log(f"[PC] osascript 执行异常: {e}")
        return False


def _desktop_dir() -> Path:
    desktop = Path.home() / "Desktop"
    desktop_alt = Path.home() / "OneDrive" / "Desktop"
    if desktop.exists():
        return desktop
    if desktop_alt.exists():
        return desktop_alt
    return Path.cwd()


def _mac_app_name(name: str) -> str:
    aliases = {
        "notepad": "TextEdit",
        "wechat": "WeChat",
    }
    text = (name or "").strip()
    return aliases.get(text.lower(), text)


def _mac_shutdown_args(restart: bool, sec: int) -> list[str]:
    action = "-r" if restart else "-h"
    if sec <= 0:
        when = "now"
    else:
        when = f"+{ceil(sec / 60)}"
    return ["sudo", "-n", "shutdown", action, when]


def _mac_notify(title: str, content: str) -> bool:
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    escaped_body = content.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{escaped_body}" with title "{escaped_title}" sound name "Glass"'
    return _run_osascript(script)


def _mac_media_play() -> bool:
    primary = 'tell application "Music" to playpause'
    if _run_osascript(primary):
        return True
    try:
        import pyautogui

        pyautogui.press("playpause")
        return True
    except Exception as e:
        _log(f"[PC] media:play 兜底失败: {e}")
        return False


def _mute_fallback_with_media_key() -> bool:
    """
    兜底静音：模拟系统静音媒体键（VK_VOLUME_MUTE=173）。
    避免 pycaw/comtypes 在部分机器上接口不兼容导致静音失败。
    """
    try:
        ps_exe = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        if not Path(ps_exe).exists():
            ps_exe = "powershell.exe"
        subprocess.run(
            [
                ps_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "(New-Object -ComObject WScript.Shell).SendKeys([char]173)",
            ],
            check=False,
            timeout=8,
        )
        return True
    except Exception:
        return False


def execute_command(cmd: str) -> bool:
    cmd = (cmd or "").strip()
    if not cmd:
        return False
    _log(f"[PC] 执行指令: {cmd}")
    try:
        if cmd == "lock":
            if _is_windows():
                import ctypes

                ctypes.windll.user32.LockWorkStation()
                return True
            if _is_macos():
                return _run_osascript(
                    'tell application "System Events" to keystroke "q" using {control down, command down}'
                )
            return False

        if cmd == "shutdown" or cmd.startswith("shutdown:"):
            sec = 60
            if ":" in cmd:
                raw_sec = cmd.split(":", 1)[1].strip()
                if not raw_sec.isdigit():
                    return False
                sec = int(raw_sec)
                if sec < 0 or sec > 86400:
                    return False
            if _is_windows():
                subprocess.run(["shutdown", "/s", "/t", str(sec)], check=False)
                return True
            if _is_macos():
                res = _run_command(_mac_shutdown_args(restart=False, sec=sec))
                if res.returncode == 0:
                    return True
                _log(f"[PC] shutdown 失败，请确认已配置免密码 sudo。stderr={(res.stderr or '').strip()[:300]}")
                return False
            return False

        if cmd == "restart" or cmd.startswith("restart:"):
            sec = 60
            if ":" in cmd:
                raw_sec = cmd.split(":", 1)[1].strip()
                if not raw_sec.isdigit():
                    return False
                sec = int(raw_sec)
                if sec < 0 or sec > 86400:
                    return False
            if _is_windows():
                subprocess.run(["shutdown", "/r", "/t", str(sec)], check=False)
                return True
            if _is_macos():
                res = _run_command(_mac_shutdown_args(restart=True, sec=sec))
                if res.returncode == 0:
                    return True
                _log(f"[PC] restart 失败，请确认已配置免密码 sudo。stderr={(res.stderr or '').strip()[:300]}")
                return False
            return False

        if cmd == "sleep":
            if _is_windows():
                subprocess.run(
                    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                    check=False,
                )
                return True
            if _is_macos():
                res = _run_command(["pmset", "sleepnow"])
                if res.returncode == 0:
                    return True
                _log(f"[PC] sleep 失败 stderr={(res.stderr or '').strip()[:300]}")
                return False
            return False

        if cmd == "mute":
            if _is_windows():
                try:
                    vol = _audio_endpoint()
                    vol.SetMute(1, None)
                    return True
                except Exception as e:
                    _log(f"[PC] mute 主方案失败，尝试兜底: {e}")
                    return _mute_fallback_with_media_key()
            if _is_macos():
                return _run_osascript("set volume with output muted")
            return False

        if cmd.startswith("volume:"):
            raw = cmd.split(":", 1)[1].strip()
            if not raw.isdigit():
                return False
            value = int(raw)
            if value < 0 or value > 100:
                return False
            if _is_windows():
                vol = _audio_endpoint()
                vol.SetMasterVolumeLevelScalar(value / 100.0, None)
                return True
            if _is_macos():
                return _run_osascript(f"set volume output volume {value}")
            return False

        if cmd.startswith("notify:"):
            parts = cmd.split(":", 2)
            title = (parts[1] if len(parts) > 1 else "渡").strip() or "渡"
            content = (parts[2] if len(parts) > 2 else "").strip()
            if _is_macos():
                if _mac_notify(title, content):
                    return True
            try:
                from plyer import notification

                notification.notify(title=title, message=content, timeout=5)
                return True
            except Exception as e:
                _log(f"[PC] 通知中心发送失败: {e}")
            if _is_macos():
                return _mac_notify(title, content)
            return False

        if cmd.startswith("open:"):
            parts = cmd.split(":", 2)
            app = (parts[1] if len(parts) > 1 else "").strip()
            if not app:
                return False
            note_text = (parts[2] if len(parts) > 2 else "").strip()
            if app.lower() == "notepad" and note_text:
                # 预填内容写入桌面临时文件，再打开默认编辑器，便于继续编辑
                note_path = _desktop_dir() / "du_notepad_note.txt"
                note_path.write_text(note_text + "\n", encoding="utf-8")
                if _is_windows():
                    subprocess.Popen(["notepad.exe", str(note_path)], shell=False)
                    return True
                if _is_macos():
                    subprocess.Popen(["open", "-a", "TextEdit", str(note_path)], shell=False)
                    return True
                return False
            if _is_windows():
                subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
                return True
            if _is_macos():
                subprocess.Popen(["open", "-a", _mac_app_name(app)], shell=False)
                return True
            return False

        if cmd.startswith("url:"):
            url = cmd.split(":", 1)[1].strip()
            if not url:
                return False
            webbrowser.open(url)
            return True

        if cmd == "media:play":
            if _is_macos():
                return _mac_media_play()
            try:
                import pyautogui

                pyautogui.press("playpause")
                return True
            except Exception as e:
                _log(f"[PC] media:play 执行失败: {e}")
                return False

        _log(f"[PC] 未支持指令: {cmd}")
        return False
    except Exception as e:
        _log(f"[PC] 执行失败 {cmd}: {e}")
        return False


def poll_once() -> None:
    if not GATEWAY_URL or not PC_COMMAND_TOKEN:
        _log("[PC] 缺少 GATEWAY_URL 或 PC_COMMAND_TOKEN，无法轮询")
        return
    base = GATEWAY_URL.rstrip("/")
    try:
        res = requests.get(
            f"{base}/api/pc_command",
            headers=_headers(),
            timeout=20,
        )
        if res.status_code != 200:
            _log(f"[PC] 拉取失败 status={res.status_code} body={(res.text or '')[:200]}")
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
                _log(f"[PC] 回执失败 status={ack.status_code} body={(ack.text or '')[:200]}")
                return
            payload = ack.json() if ack.content else {}
            removed = payload.get("removedCount") if isinstance(payload, dict) else 0
            _log(f"[PC] 回执成功 done={len(done_ids)} removed={removed}")
    except Exception as e:
        _log(f"[PC] 轮询异常: {e}")


def main() -> None:
    _log(f"[PC] 启动完成，每 {PC_POLL_SECONDS} 秒轮询一次")
    if not GATEWAY_URL or not PC_COMMAND_TOKEN:
        _log("[PC] 请在桌面 .env（或系统环境变量）中设置 GATEWAY_URL 与 PC_COMMAND_TOKEN")
    while True:
        poll_once()
        time.sleep(PC_POLL_SECONDS)


if __name__ == "__main__":
    main()
