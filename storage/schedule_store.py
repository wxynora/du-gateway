"""R2 storage helpers for MiniApp schedule/reminder items."""
import threading
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from storage import schedule_sqlite_store
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso

R2_KEY_SCHEDULE_ITEMS = "schedule/items.json"
R2_KEY_SCHEDULE_FIRED = "schedule/fired.json"
SCHEDULE_FIRED_RETENTION_HOURS = 48

_schedule_write_lock = threading.Lock()

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _parse_fired_key_at(occurrence_key: str) -> Optional[datetime]:
    raw = str(occurrence_key or "").strip()
    if not raw:
        return None
    stamp = raw.rsplit("|", 1)[-1].strip()
    if not stamp:
        return None
    try:
        if len(stamp) == 10 and stamp[4] == "-" and stamp[7] == "-":
            return datetime.strptime(stamp, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING_TZ)
        return dt.astimezone(BEIJING_TZ)
    except Exception:
        return None


def _prune_schedule_fired_keys(keys: set[str]) -> set[str]:
    now = datetime.now(BEIJING_TZ)
    cutoff = now - timedelta(hours=SCHEDULE_FIRED_RETENTION_HOURS)
    out: set[str] = set()
    for key in keys or set():
        clean = str(key or "").strip()
        if not clean:
            continue
        fired_at = _parse_fired_key_at(clean)
        if fired_at is None or fired_at >= cutoff:
            out.add(clean)
    return out


def _read_schedule_items_from_r2() -> list[dict]:
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_SCHEDULE_ITEMS)
    if not data or not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out = []
    for x in items:
        if not isinstance(x, dict):
            continue
        out.append(dict(x))
    out.sort(key=lambda x: (str(x.get("datetime") or ""), str(x.get("id") or "")))
    return out


def get_schedule_items() -> list[dict]:
    """读取日历/提醒条目列表。"""
    items = _read_schedule_items_from_r2()
    schedule_sqlite_store.replace_items(items)
    return items


def save_schedule_items(items: list[dict]) -> bool:
    """保存日历/提醒条目列表（覆盖）。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"items": items or []}
    with _schedule_write_lock:
        try:
            _write_json(client, R2_KEY_SCHEDULE_ITEMS, payload)
            schedule_sqlite_store.replace_items(payload["items"])
            return True
        except Exception as e:
            logger.error("save_schedule_items 失败 error=%s", e, exc_info=True)
            return False


def disable_schedule_item(item_id: str) -> bool:
    """禁用某条提醒：enabled=false，未来不再触发。"""
    iid = (item_id or "").strip()
    if not iid:
        return False
    items = get_schedule_items()
    if not items:
        return False
    changed = False
    now_iso = now_beijing_iso()
    for it in items:
        if str(it.get("id") or "").strip() != iid:
            continue
        if bool(it.get("enabled")):
            it["enabled"] = False
            it["disabled_at"] = now_iso
            changed = True
        break
    if not changed:
        return False
    return save_schedule_items(items)


def enable_schedule_item(item_id: str) -> bool:
    """启用某条提醒：enabled=true。"""
    iid = (item_id or "").strip()
    if not iid:
        return False
    items = get_schedule_items()
    if not items:
        return False
    changed = False
    now_iso = now_beijing_iso()
    for it in items:
        if str(it.get("id") or "").strip() != iid:
            continue
        if not bool(it.get("enabled")):
            it["enabled"] = True
            it["enabled_at"] = now_iso
            changed = True
        break
    if not changed:
        return False
    return save_schedule_items(items)


def create_schedule_item(
    title: str,
    datetime_str: str,
    repeat: str = "once",
    note: str = "",
    enabled: bool = True,
    weekly_weekday: Optional[int] = None,
    weekly_time: str = "",
    daily_time: str = "",
    created_by: str = "wife",
    target_role: str = "wife",
) -> Optional[dict]:
    """创建一条提醒并写入 schedule/items.json。"""
    def _parse_hhmm(raw: str) -> tuple[int, int] | None:
        """解析 HH:mm，兼容全角冒号与 0:0 这类输入。"""
        s = str(raw or "").strip()
        if not s:
            return None
        s = s.replace("：", ":")
        if ":" not in s:
            return None
        hh, mm = (s.split(":", 1) + [""])[:2]
        hh = hh.strip()
        mm = mm.strip()
        if not hh.isdigit() or not mm.isdigit():
            return None
        hhi = int(hh)
        mmi = int(mm)
        if hhi < 0 or hhi > 23 or mmi < 0 or mmi > 59:
            return None
        return hhi, mmi

    def _norm_hhmm(raw: str) -> str:
        parsed = _parse_hhmm(raw)
        if not parsed:
            return ""
        hhi, mmi = parsed
        return f"{hhi:02d}:{mmi:02d}"

    t = (title or "").strip()
    dt = (datetime_str or "").strip()
    rep = (repeat or "once").strip().lower() or "once"
    n = (note or "").strip()
    creator = (created_by or "wife").strip().lower() or "wife"
    if creator not in ("wife", "du"):
        creator = "wife"
    target = (target_role or "wife").strip().lower() or "wife"
    if target not in ("wife", "du"):
        target = "wife"
    if not t:
        return None
    if rep not in ("once", "daily", "weekly"):
        rep = "once"

    wday = weekly_weekday if isinstance(weekly_weekday, int) else None
    wtime = _norm_hhmm(weekly_time)
    dtime = _norm_hhmm(daily_time)
    if rep == "weekly":
        if wday is None or wday < 0 or wday > 6:
            return None
        hm = _parse_hhmm(wtime)
        if not hm:
            return None
        hhi, mmi = hm
        # 计算“下一次该周几该时刻”的北京时间，保存为 datetime 锚点
        now = datetime.now(BEIJING_TZ)
        next_dt = now.replace(hour=hhi, minute=mmi, second=0, microsecond=0)
        delta_days = (wday - next_dt.weekday()) % 7
        next_dt = next_dt + timedelta(days=delta_days)
        if next_dt <= now:
            next_dt = next_dt + timedelta(days=7)
        dt = next_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    elif rep == "daily":
        hm = _parse_hhmm(dtime)
        if not hm:
            return None
        hhi, mmi = hm
        now = datetime.now(BEIJING_TZ)
        next_dt = now.replace(hour=hhi, minute=mmi, second=0, microsecond=0)
        if next_dt <= now:
            next_dt = next_dt + timedelta(days=1)
        dt = next_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    else:
        if not dt:
            return None

    item = {
        "id": str(uuid4()),
        "title": t,
        "datetime": dt,
        "repeat": rep,
        "enabled": bool(enabled),
        "note": n,
        "created_by": creator,
        "target_role": target,
        "created_at": now_beijing_iso(),
    }
    if rep == "weekly" and wday is not None:
        item["weekly_weekday"] = int(wday)
        item["weekly_time"] = wtime
    if rep == "daily":
        item["daily_time"] = dtime
    items = get_schedule_items()
    items.append(item)
    ok = save_schedule_items(items)
    return item if ok else None


def delete_schedule_item(item_id: str) -> bool:
    """删除某条提醒。"""
    iid = (item_id or "").strip()
    if not iid:
        return False
    items = get_schedule_items()
    if not items:
        return False
    new_items = [it for it in items if str(it.get("id") or "").strip() != iid]
    if len(new_items) == len(items):
        return False
    return save_schedule_items(new_items)


def _read_schedule_fired_keys_from_r2() -> set[str]:
    client = _s3_client()
    if not client:
        return set()
    data = _read_json(client, R2_KEY_SCHEDULE_FIRED)
    if not data or not isinstance(data, dict):
        return set()
    keys = data.get("keys")
    if not isinstance(keys, list):
        return set()
    out = set()
    for k in keys:
        s = str(k or "").strip()
        if s:
            out.add(s)
    return out


def get_schedule_fired_keys() -> set[str]:
    """读取已触发 occurrence_key 集合。"""
    raw_keys = _read_schedule_fired_keys_from_r2()
    keys = _prune_schedule_fired_keys(raw_keys)
    if keys != raw_keys:
        client = _s3_client()
        if client:
            payload = {
                "keys": sorted(keys),
                "updated_at": now_beijing_iso(),
            }
            with _schedule_write_lock:
                try:
                    _write_json(client, R2_KEY_SCHEDULE_FIRED, payload)
                except Exception as e:
                    logger.warning("schedule fired keys TTL 回写失败 error=%s", e)
    schedule_sqlite_store.replace_fired_keys(keys)
    return keys


def add_schedule_fired_key(occurrence_key: str) -> bool:
    """写入一条已触发 occurrence_key（幂等）。"""
    k = (occurrence_key or "").strip()
    if not k:
        return False
    keys = get_schedule_fired_keys()
    if k in keys:
        return True
    keys.add(k)
    keys = _prune_schedule_fired_keys(keys)
    payload = {
        "keys": sorted(keys),
        "updated_at": now_beijing_iso(),
    }
    client = _s3_client()
    if not client:
        return False
    with _schedule_write_lock:
        try:
            _write_json(client, R2_KEY_SCHEDULE_FIRED, payload)
            schedule_sqlite_store.add_fired_key(k)
            return True
        except Exception as e:
            logger.error("add_schedule_fired_key 失败 key=%s error=%s", k, e, exc_info=True)
            return False
