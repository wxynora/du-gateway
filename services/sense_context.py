# 设备感知（sense/latest.json）→ 渡的 system 注入。
# battery + location + health + screen + foreground + app_sessions + usage。
# 字段约定见 docs/感知模块方案.md
from __future__ import annotations

from typing import Any

from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

_MAX_SNAPSHOT_CHARS = 800
_MAX_USAGE_APPS = 5
_MAX_APP_SESSION_ITEMS = 5
_SLEEP_GUESS_MIN_SCREEN_OFF_MINUTES = 60


def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _battery_charging_suffix(ch: Any) -> str | None:
    """
    charging 展示文案：Tasker/Android 整数状态码优先，其次兼容布尔与常见字符串。
    2=充电中，3=放电，4=未充电，5=满电。
    """
    if ch is None:
        return None
    try:
        n = int(ch)
        if n == 2:
            return "充电中"
        if n == 3:
            return "放电"
        if n == 4:
            return "未充电"
        if n == 5:
            return "满电"
    except (TypeError, ValueError):
        pass
    if ch is True or str(ch).lower() in ("true", "1", "yes", "on"):
        return "充电中"
    if ch is False or str(ch).lower() in ("false", "0", "no", "off"):
        return "未充电"
    return None


def _format_lat_lng(loc: dict) -> str | None:
    """有有效 lat/lng 时返回一行坐标文案，否则 None。"""
    lat, lng = loc.get("lat"), loc.get("lng")
    if lat is None or lng is None:
        return None
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    return f"定位：{la:.5f}，{ln:.5f}"


def _format_location_line(loc: dict) -> str | None:
    """优先高德写入的 address，否则退回经纬度。"""
    addr = (loc.get("address") or "").strip()
    if addr:
        return f"定位：{addr}"
    return _format_lat_lng(loc)


def _format_health_line(health: dict) -> str | None:
    """固定注入心率/步数：有哪个字段就显示哪个。"""
    hr = health.get("heart_rate")
    steps = health.get("steps")
    parts: list[str] = []
    if hr not in (None, ""):
        parts.append(f"心率：{hr}")
    if steps not in (None, ""):
        parts.append(f"步数：{steps}")
    if not parts:
        return None
    return "，".join(parts)


def _format_elapsed_from_iso(iso_str: str) -> str:
    dt = parse_iso_to_beijing(str(iso_str or "").strip())
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not dt or not now_dt:
        return "刚"
    seconds = int((now_dt - dt).total_seconds())
    if seconds <= 90:
        return "刚"
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes}分钟前"
    hours = minutes // 60
    rest_minutes = minutes % 60
    if hours < 24:
        if rest_minutes:
            return f"{hours}小时{rest_minutes}分钟前"
        return f"{hours}小时前"
    days = hours // 24
    rest_hours = hours % 24
    if rest_hours:
        return f"{days}天{rest_hours}小时前"
    return f"{days}天前"


def _format_duration_minutes(minutes: int) -> str:
    minutes = max(1, int(minutes))
    if minutes < 60:
        return f"{minutes}分钟"
    hours = minutes // 60
    rest_minutes = minutes % 60
    if rest_minutes:
        return f"{hours}小时{rest_minutes}分钟"
    return f"{hours}小时"


def _screen_off_duration_minutes(screen: dict) -> tuple[int | None, Any]:
    if str(screen.get("event") or "").strip().lower() != "screen_off":
        return None, None
    since_raw = str(screen.get("screenOffSince") or screen.get("occurredAt") or "").strip()
    since_dt = parse_iso_to_beijing(since_raw)
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if since_dt and now_dt:
        minutes = int((now_dt - since_dt).total_seconds() // 60)
        return max(0, minutes), since_dt
    try:
        duration_ms = int(screen.get("screenOffDurationMs") or 0)
    except Exception:
        duration_ms = 0
    if duration_ms > 0:
        return max(1, int(duration_ms // 60000)), None
    return None, None


def _format_sleep_guess_line(screen: dict) -> str | None:
    minutes, since_dt = _screen_off_duration_minutes(screen)
    if minutes is None or minutes < _SLEEP_GUESS_MIN_SCREEN_OFF_MINUTES:
        return None
    duration = _format_duration_minutes(minutes)
    if since_dt:
        return f"她可能睡着了：手机从 {since_dt.strftime('%H:%M')} 起连续熄屏 {duration}，期间没有明显手机操作。"
    return f"她可能睡着了：手机已连续熄屏 {duration}，期间没有明显手机操作。"


def _format_last_sleep_summary_line(screen: dict) -> str | None:
    summary = screen.get("sleepSummary")
    if not isinstance(summary, dict):
        return None
    try:
        total_minutes = int(summary.get("totalMinutes") or 0)
    except Exception:
        total_minutes = 0
    if total_minutes < _SLEEP_GUESS_MIN_SCREEN_OFF_MINUTES:
        return None
    start_dt = parse_iso_to_beijing(str(summary.get("startAt") or "").strip())
    end_dt = parse_iso_to_beijing(str(summary.get("endAt") or "").strip())
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if end_dt and now_dt and (now_dt - end_dt).total_seconds() > 24 * 3600:
        return None
    duration = _format_duration_minutes(total_minutes)
    try:
        segment_count = int(summary.get("segmentCount") or 0)
    except Exception:
        segment_count = 0
    try:
        awake_gap_minutes = int(summary.get("awakeGapMinutes") or 0)
    except Exception:
        awake_gap_minutes = 0
    time_range = ""
    if start_dt and end_dt:
        time_range = f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} "
    parts = [f"最近睡眠推断：{time_range}累计熄屏睡眠 {duration}"]
    if segment_count > 1:
        parts.append(f"分 {segment_count} 段")
    if awake_gap_minutes > 0:
        parts.append(f"中间醒着约 {_format_duration_minutes(awake_gap_minutes)}")
    return "，".join(parts) + "。"


def _format_screen_line(screen: dict) -> str | None:
    event = str(screen.get("event") or "").strip().lower()
    if not event:
        return None
    mapping = {
        "screen_on": "亮屏",
        "screen_off": "熄屏",
        "user_present": "解锁",
        "app_active": "打开 SumiTalk",
    }
    action = mapping.get(event)
    if not action:
        return None
    event_at = str(screen.get("occurredAt") or screen.get("observedAt") or screen.get("capturedAt") or screen.get("updatedAt") or "").strip()
    elapsed = _format_elapsed_from_iso(event_at)
    return f"屏幕状态：{elapsed}{action}"


def _format_usage_line(usage: dict) -> str | None:
    apps = usage.get("apps")
    if not isinstance(apps, list) or not apps:
        return None
    parts: list[str] = []
    for item in apps[:_MAX_USAGE_APPS]:
        if not isinstance(item, dict):
            continue
        pkg = str(item.get("packageName") or "").strip()
        app_name = str(item.get("appName") or "").strip() or pkg
        try:
            ms = int(item.get("foregroundMs") or 0)
        except Exception:
            ms = 0
        if not app_name or ms <= 0:
            continue
        total_mins = max(1, round(ms / 60000))
        hours = total_mins // 60
        mins = total_mins % 60
        if hours > 0 and mins > 0:
            duration = f"{hours}小时{mins}分钟"
        elif hours > 0:
            duration = f"{hours}小时"
        else:
            duration = f"{mins}分钟"
        parts.append(f"{app_name} {duration}")
    if not parts:
        return None
    return "最近使用：" + "，".join(parts)


def _format_session_duration_ms(ms: int) -> str:
    try:
        n = int(ms or 0)
    except Exception:
        n = 0
    if n <= 0:
        return ""
    if n < 60000:
        return "不到1分钟"
    return _format_duration_minutes(max(1, round(n / 60000)))


def _duration_ms_from_range(started_at: str, ended_at: str) -> int:
    start = parse_iso_to_beijing(str(started_at or "").strip())
    end = parse_iso_to_beijing(str(ended_at or "").strip())
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))


def _format_app_session_item(item: dict, active: bool = False) -> str | None:
    if not isinstance(item, dict):
        return None
    app_name = str(item.get("appName") or item.get("packageName") or "").strip()
    started_at = str(item.get("startedAt") or "").strip()
    started_dt = parse_iso_to_beijing(started_at)
    if not app_name or not started_dt:
        return None
    clock = started_dt.strftime("%H:%M")
    if active:
        now_dt = parse_iso_to_beijing(now_beijing_iso())
        duration_ms = max(0, int((now_dt - started_dt).total_seconds() * 1000)) if now_dt else 0
        duration = _format_session_duration_ms(duration_ms) or "刚打开"
        return f"{clock} 打开{app_name}，正在使用{duration}"
    try:
        duration_ms = int(item.get("durationMs") or 0)
    except Exception:
        duration_ms = 0
    if duration_ms <= 0:
        duration_ms = _duration_ms_from_range(started_at, str(item.get("endedAt") or "").strip())
    duration = _format_session_duration_ms(duration_ms)
    if not duration:
        return None
    return f"{clock} 打开{app_name}，看了{duration}"


def _format_app_sessions_line(app_sessions: dict) -> str | None:
    pieces: list[str] = []
    active = app_sessions.get("active")
    if isinstance(active, dict) and active:
        piece = _format_app_session_item(active, active=True)
        if piece:
            pieces.append(piece)
    recent = app_sessions.get("recent")
    if isinstance(recent, list):
        for item in recent:
            piece = _format_app_session_item(item if isinstance(item, dict) else {}, active=False)
            if piece:
                pieces.append(piece)
            if len(pieces) >= _MAX_APP_SESSION_ITEMS:
                break
    if not pieces:
        return None
    return "最近五次应用：" + "；".join(pieces[:_MAX_APP_SESSION_ITEMS])


def _format_foreground_line(foreground: dict) -> str | None:
    app_name = str(foreground.get("appName") or foreground.get("packageName") or "").strip()
    if not app_name:
        return None
    observed_at = str(foreground.get("observedAt") or foreground.get("updatedAt") or "").strip()
    elapsed = _format_elapsed_from_iso(observed_at)
    return f"当前前台应用：{elapsed}{app_name}"


def format_sense_snapshot_for_system() -> str:
    """
    标题「老婆当前状态」+ 电量 / 定位 / 心率步数 / 屏幕状态 / 前台应用 / 应用使用（有数据就注入）。
    """
    try:
        doc = r2_store.get_sense_latest()
    except Exception as e:
        logger.debug("get_sense_latest 失败（跳过注入） error=%s", e)
        return ""
    if not isinstance(doc, dict) or not doc:
        return ""

    bat = _as_dict(doc.get("battery"))
    loc = _as_dict(doc.get("location"))
    health = _as_dict(doc.get("health"))
    screen = _as_dict(doc.get("screen"))
    foreground = _as_dict(doc.get("foreground"))
    usage = _as_dict(doc.get("usage"))
    app_sessions = _as_dict(doc.get("app_sessions"))
    has_battery = bool(bat) and "level" in bat
    loc_line = _format_location_line(loc)
    health_line = _format_health_line(health)
    screen_line = _format_screen_line(screen)
    sleep_guess_line = _format_sleep_guess_line(screen)
    sleep_summary_line = None if sleep_guess_line else _format_last_sleep_summary_line(screen)
    foreground_line = _format_foreground_line(foreground)
    app_sessions_line = _format_app_sessions_line(app_sessions)
    usage_line = _format_usage_line(usage)
    if not has_battery and not loc_line and not health_line and not screen_line and not sleep_guess_line and not sleep_summary_line and not foreground_line and not app_sessions_line and not usage_line:
        return ""

    lines: list[str] = ["老婆当前状态"]
    if has_battery:
        lv = bat.get("level")
        ch = bat.get("charging")
        suffix = _battery_charging_suffix(ch)
        if suffix:
            lines.append(f"电量：{lv}%，{suffix}")
        else:
            lines.append(f"电量：{lv}%")
    if loc_line:
        lines.append(loc_line)
    if health_line:
        lines.append(health_line)
    if sleep_guess_line:
        lines.append(sleep_guess_line)
    elif sleep_summary_line:
        lines.append(sleep_summary_line)
    elif screen_line:
        lines.append(screen_line)
    if foreground_line:
        lines.append(foreground_line)
    if app_sessions_line:
        lines.append(app_sessions_line)
    if usage_line:
        lines.append(usage_line)

    body = "\n".join(lines)
    if len(body) > _MAX_SNAPSHOT_CHARS:
        body = body[: _MAX_SNAPSHOT_CHARS - 5] + "\n…"
    return body
