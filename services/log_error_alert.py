from __future__ import annotations

import hashlib
import re
import threading
import time

_lock = threading.Lock()
_recent: dict[str, float] = {}
_global_last_at = 0.0
_COOLDOWN_SECONDS = 300.0
_GLOBAL_MIN_INTERVAL_SECONDS = 30.0


def _fingerprint(line: str) -> str:
    text = str(line or "")
    text = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?", "<time>", text)
    text = re.sub(r"\b[0-9a-f]{8,}(?:-[0-9a-f]{4,})*\b", "<id>", text, flags=re.I)
    text = re.sub(r"\b\d{4,}\b", "<num>", text)
    return hashlib.sha1(text[:500].encode("utf-8", errors="ignore")).hexdigest()[:16]


def maybe_enqueue_log_error_alert(line: str, level_name: str = "ERROR") -> None:
    raw = str(line or "").strip()
    if not raw:
        return
    fp = _fingerprint(raw)
    now = time.time()
    global _global_last_at
    with _lock:
        last = float(_recent.get(fp) or 0.0)
        if now - last < _COOLDOWN_SECONDS:
            return
        if now - _global_last_at < _GLOBAL_MIN_INTERVAL_SECONDS:
            return
        _recent[fp] = now
        _global_last_at = now
        if len(_recent) > 200:
            cutoff = now - 3600.0
            for key, ts in list(_recent.items()):
                if ts < cutoff:
                    _recent.pop(key, None)
    threading.Thread(target=_enqueue_alert, args=(raw, str(level_name or "ERROR"), fp), daemon=True).start()


def _enqueue_alert(line: str, level_name: str, fp: str) -> None:
    try:
        from storage import r2_store

        title = f"网关日志红了：{level_name.upper()}"
        msg = line
        if len(msg) > 360:
            msg = msg[:360] + "..."
        r2_store.append_app_action(
            "show_choice_dialog",
            {
                "title": title,
                "message": f"检测到一条 {level_name.upper()} 日志：\n{msg}",
                "choice_a": "知道了",
                "choice_b": "等会看",
                "level": "warning",
                "dismissible": True,
                "timeoutSeconds": 1800,
                "notifyDu": False,
            },
            source="log_error_alert",
            expires_in_sec=1800,
            idempotency_key=f"log_error_alert_{fp}_{int(time.time() // _COOLDOWN_SECONDS)}",
        )
    except Exception:
        # 不能在日志 handler 的错误提醒里继续打日志，否则可能递归刷屏。
        pass
