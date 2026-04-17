"""
QQ / NapCat 掉线巡检：
- 检测 NapCat 是否进入扫码登录态（qrcode.png 出现）
- 首次检测到后，通过现有 Telegram Bot 给指定用户发一次告警
- 二维码消失后重置状态，下一次再掉线可以继续告警

用法：
  cd 项目根目录
  python scripts/run_qq_entry_watchdog.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)

from config import (
    QQ_ENTRY_WATCHDOG_ALERT_TELEGRAM_USER_ID,
    QQ_ENTRY_WATCHDOG_ENABLED,
    QQ_ENTRY_WATCHDOG_QRCODE_PATH,
    QQ_ENTRY_WATCHDOG_STATE_FILE,
    TELEGRAM_BOT_TOKEN,
)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _send_alert(text: str) -> bool:
    uid = int(QQ_ENTRY_WATCHDOG_ALERT_TELEGRAM_USER_ID or 0)
    if uid <= 0 or not TELEGRAM_BOT_TOKEN:
        return False
    body = parse.urlencode({"chat_id": str(uid), "text": text}).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            return 200 <= int(resp.status or 0) < 300
    except Exception:
        return False


def main() -> int:
    if not QQ_ENTRY_WATCHDOG_ENABLED:
        print("[qq-watchdog] disabled")
        return 0

    qrcode_path = Path(QQ_ENTRY_WATCHDOG_QRCODE_PATH)
    state_path = Path(QQ_ENTRY_WATCHDOG_STATE_FILE)
    state = _load_state(state_path)

    active = bool(state.get("qrcode_active"))
    last_mtime = float(state.get("last_qrcode_mtime", 0.0) or 0.0)

    if qrcode_path.exists():
        try:
            stat = qrcode_path.stat()
            mtime = float(stat.st_mtime)
        except Exception:
            mtime = 0.0

        if (not active) or (mtime > last_mtime):
            sent = _send_alert(
                "\n".join(
                    [
                        "QQ / NapCat 需要重新扫码登录。",
                        f"时间：{_now_text()}",
                        f"二维码文件：{qrcode_path}",
                    ]
                )
            )
            state = {
                "qrcode_active": True,
                "last_qrcode_mtime": mtime,
                "last_alert_at": _now_text(),
                "last_alert_sent": bool(sent),
            }
            _save_state(state_path, state)
            print(f"[qq-watchdog] qrcode detected sent={sent}")
            return 0

        print("[qq-watchdog] qrcode still active, skip duplicate alert")
        return 0

    if active:
        state = {
            "qrcode_active": False,
            "last_qrcode_mtime": 0.0,
            "last_recovered_at": _now_text(),
        }
        _save_state(state_path, state)
        print("[qq-watchdog] qrcode cleared")
        return 0

    print("[qq-watchdog] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
