import threading
import time
from datetime import timedelta

from config import (
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    MINIAPP_SCHEDULE_RUNTIME_ENABLED,
    MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS,
)
from storage import r2_store
from services.telegram_proactive import schedule_tick
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

_runtime_started = False
_runtime_lock = threading.Lock()
_wakeup_event = threading.Event()


def _hm_from_item(it: dict, field: str, fallback_h: int = 9, fallback_m: int = 0) -> tuple[int, int]:
    raw = str(it.get(field) or "").strip()
    if raw:
        try:
            hh, mm = (raw.split(":", 1) + ["0"])[:2]
            h = int(hh)
            m = int(mm)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
        except Exception:
            pass
    return fallback_h, fallback_m


def _seconds_to_next_due(now_dt, items: list[dict]) -> int:
    """
    计算下一次可能触发的等待秒数。
    - 仅用于等待优化，不参与最终触发判断（最终仍走 schedule_tick）。
    """
    candidates: list[int] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if not bool(it.get("enabled", True)):
            continue
        rep = str(it.get("repeat") or "once").strip().lower() or "once"
        anchor = parse_iso_to_beijing(str(it.get("datetime") or "").strip())
        target = None
        if rep == "once":
            if anchor:
                target = anchor
        elif rep == "daily":
            h, m = _hm_from_item(it, "daily_time", anchor.hour if anchor else 9, anchor.minute if anchor else 0)
            target = now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now_dt:
                target = target + timedelta(days=1)
        elif rep == "weekly":
            w = it.get("weekly_weekday", None)
            try:
                target_w = int(w)
            except Exception:
                target_w = anchor.weekday() if anchor else 0
            if target_w < 0 or target_w > 6:
                target_w = 0
            h, m = _hm_from_item(it, "weekly_time", anchor.hour if anchor else 9, anchor.minute if anchor else 0)
            target = now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
            delta_days = (target_w - target.weekday()) % 7
            target = target + timedelta(days=delta_days)
            if target <= now_dt:
                target = target + timedelta(days=7)
        if not target:
            continue
        sec = int((target - now_dt).total_seconds())
        if sec < 0:
            sec = 0
        candidates.append(sec)

    if not candidates:
        return 300
    return max(0, min(candidates))


def _loop():
    fallback_interval = max(30, int(MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS or 300))
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    logger.info("内置日历闹钟调度启动 fallback_interval_s=%s target_user_id=%s", fallback_interval, uid)
    while True:
        try:
            result = schedule_tick(uid)
            logger.info("内置日历闹钟 tick result=%s", result)
        except Exception as e:
            logger.exception("内置日历闹钟 tick 异常: %s", e)
        try:
            now_dt = parse_iso_to_beijing(now_beijing_iso())
            items = r2_store.get_schedule_items() or []
            next_due = _seconds_to_next_due(now_dt, items) if now_dt else fallback_interval
            wait_s = min(fallback_interval, max(5, next_due))
        except Exception:
            wait_s = fallback_interval
        # 事件驱动：有新增/启用/禁用/删除时立即唤醒重算；否则按下一次到点/兜底间隔等待
        _wakeup_event.wait(timeout=wait_s)
        _wakeup_event.clear()


def start_schedule_runtime_if_enabled():
    """按配置启动网关内置日历闹钟调度线程。"""
    global _runtime_started
    if not MINIAPP_SCHEDULE_RUNTIME_ENABLED:
        logger.info("内置日历闹钟调度未开启（MINIAPP_SCHEDULE_RUNTIME_ENABLED!=1）")
        return
    with _runtime_lock:
        if _runtime_started:
            return
        th = threading.Thread(target=_loop, name="miniapp-schedule-runtime", daemon=True)
        th.start()
        _runtime_started = True


def notify_schedule_changed():
    """当日历条目变更时，唤醒内置调度线程立即重算。"""
    _wakeup_event.set()

