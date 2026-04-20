# 设备感知（sense/latest.json）→ 渡的 system 注入。
# battery + location + health + music + screen + usage。
# 字段约定见 docs/感知模块方案.md
from __future__ import annotations

from typing import Any

from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)

_MAX_SNAPSHOT_CHARS = 800
_MAX_USAGE_APPS = 5


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


def _format_music_line(music: dict) -> str | None:
    """格式化当前音乐：优先歌名，其次补充歌手/专辑与播放状态。"""
    track = str(music.get("track") or "").strip()
    artist = str(music.get("artist") or "").strip()
    album = str(music.get("album") or "").strip()
    playing = music.get("playing")

    if not track and not artist and not album:
        return None

    parts: list[str] = []
    if track:
        parts.append(track)
    if artist:
        parts.append(artist)
    if album:
        parts.append(album)

    text = " - ".join(parts) if parts else ""
    return f"音乐：{text}" if text else None


def _format_music_playing_line(music: dict) -> str | None:
    """单独格式化播放状态，便于在注入中直观看到当前是否在播。"""
    playing = music.get("playing")
    if playing is True or str(playing).lower() in ("true", "1", "yes", "on"):
        return "播放状态：播放中"
    if playing is False or str(playing).lower() in ("false", "0", "no", "off"):
        return "播放状态：已暂停"
    return None


def _format_screen_line(screen: dict) -> str | None:
    event = str(screen.get("event") or "").strip().lower()
    if not event:
        return None
    mapping = {
        "screen_on": "刚亮屏",
        "screen_off": "刚熄屏",
        "user_present": "刚解锁",
        "app_active": "刚打开 SumiTalk",
    }
    label = mapping.get(event)
    if not label:
        return None
    return f"屏幕状态：{label}"


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


def format_sense_snapshot_for_system() -> str:
    """
    标题「老婆当前状态」+ 电量 / 定位 / 心率步数 / 音乐 / 屏幕状态 / 应用使用（有数据就注入）。
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
    music = _as_dict(doc.get("music"))
    screen = _as_dict(doc.get("screen"))
    usage = _as_dict(doc.get("usage"))
    has_battery = bool(bat) and "level" in bat
    loc_line = _format_location_line(loc)
    health_line = _format_health_line(health)
    music_line = _format_music_line(music)
    music_playing_line = _format_music_playing_line(music)
    screen_line = _format_screen_line(screen)
    usage_line = _format_usage_line(usage)
    if not has_battery and not loc_line and not health_line and not music_line and not music_playing_line and not screen_line and not usage_line:
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
    if music_line:
        lines.append(music_line)
    if music_playing_line:
        lines.append(music_playing_line)
    if screen_line:
        lines.append(screen_line)
    if usage_line:
        lines.append(usage_line)

    body = "\n".join(lines)
    if len(body) > _MAX_SNAPSHOT_CHARS:
        body = body[: _MAX_SNAPSHOT_CHARS - 5] + "\n…"
    return body
