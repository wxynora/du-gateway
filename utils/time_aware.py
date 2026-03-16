# 时间与农历：全部北京时间；时间段（每次注入）+ 具体时间/农历（渡上一轮触发时注入）
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

# 北京时间 UTC+8
BEIJING_TZ = timezone(timedelta(hours=8))

_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 农历：可选依赖，无则仅返回占位
try:
    from zhdate import ZhDate
    _HAS_ZHDATE = True
except ImportError:
    _HAS_ZHDATE = False

# 黄历缓存：按北京时间按日缓存一次，避免一天内多次请求外部黄历 API
_ALMANAC_CACHE = {
    "date": "",
    "text": "",
}


# 按小时（0-23）映射到大概时间段（北京时间）
_PERIODS = [
    (0, 5, "深夜"),
    (5, 8, "早上"),
    (8, 11, "上午"),
    (11, 14, "中午"),
    (14, 17, "下午"),
    (17, 19, "傍晚"),
    (19, 22, "晚上"),
    (22, 24, "深夜"),
]


def _now_beijing() -> datetime:
    """当前北京时间。"""
    return datetime.now(BEIJING_TZ)


def now_beijing_iso() -> str:
    """当前北京时间的 ISO 字符串，用于存储（+08:00）。"""
    return _now_beijing().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def today_beijing() -> str:
    """今日日期 YYYY-MM-DD（北京时间），用于按日存储键等。"""
    return _now_beijing().strftime("%Y-%m-%d")


def parse_iso_to_beijing(iso_str: Optional[str]) -> Optional[datetime]:
    """
    把存储的 ISO 时间转成北京时间的 datetime，解析失败返回 None。
    - 带时区的（Z / +00:00 / +08:00 等）：按该时区转成北京时间。
    - 无时区的（如 2026-03-06T15:59:25）：视为已是北京时间，不再按 UTC 转（避免导出里的本地时间被当成 UTC 导致错成「美国时间」）。
    """
    if not iso_str or not isinstance(iso_str, str):
        return None
    s = iso_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING_TZ)
            return dt
        return dt.astimezone(BEIJING_TZ)
    except Exception:
        return None


def get_time_period(dt: Optional[datetime] = None) -> str:
    """当前大概时间段：早上、上午、中午、下午、傍晚、晚上、深夜（北京时间）。"""
    if dt is None:
        dt = _now_beijing()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)
    h = dt.hour
    for start, end, label in _PERIODS:
        if start <= h < end:
            return label
    return "晚上"


def get_exact_time(dt: Optional[datetime] = None) -> str:
    """当前具体时间 HH:mm（北京时间，渡想知道时兜底注入）。"""
    if dt is None:
        dt = _now_beijing()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)
    return dt.strftime("%H:%M")


def get_date_only(dt: Optional[datetime] = None) -> str:
    """今日日期 YYYY-MM-DD（北京时间）。"""
    if dt is None:
        dt = _now_beijing()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)
    return dt.strftime("%Y-%m-%d")


def iso_to_display_time(iso_str: Optional[str]) -> str:
    """
    把 ISO 时间（如 2026-03-07T14:41:58.912533Z）转成给人看的版本（如 2026年03月07日 14:41）。
    用于归档写入 Notion 时存成可读时间；解析失败返回空串。
    """
    dt = parse_iso_to_beijing(iso_str)
    if dt is None:
        return ""
    return dt.strftime("%Y年%m月%d日 %H:%M")


def display_time_to_iso(display_str: Optional[str]) -> str:
    """
    把给人看的时间（如 2026年03月07日 14:41）解析回北京时间的 ISO 串，供 R2/内部使用。
    若已是 ISO 或解析失败，返回原字符串（不丢数据）。
    """
    if not display_str or not isinstance(display_str, str):
        return ""
    s = display_str.strip()
    if not s:
        return ""
    # 已是 ISO 格式则直接返回
    if parse_iso_to_beijing(s) is not None:
        return s
    # 匹配 2026年03月07日 14:41 或 2026年3月7日 14:41
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})", s)
    if m:
        y, mon, d, h, mi = m.groups()
        try:
            dt = datetime(int(y), int(mon), int(d), int(h), int(mi), 0, 0, tzinfo=BEIJING_TZ)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except Exception:
            pass
    return s


def get_weekday_cn(dt: Optional[datetime] = None) -> str:
    """周几（北京时间），如 周三。"""
    if dt is None:
        dt = _now_beijing()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)
    # Python: Monday=0
    return _WEEKDAY_CN[dt.weekday()]


def get_lunar_and_terms(dt: Optional[datetime] = None) -> str:
    """
    农历 + 节气 + 宜忌 一行文案（渡想知道时才注入）；日期按北京时间。
    农历用 zhdate；节气/宜忌优先调用外部黄历 API（按日缓存），失败时回退为占位。
    """
    if dt is None:
        dt = _now_beijing()
    elif dt.tzinfo is not None:
        dt = dt.astimezone(BEIJING_TZ)
    else:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    # 农历
    if _HAS_ZHDATE:
        try:
            z = ZhDate.from_datetime(dt)
            lunar = z.chinese()  # 如 "农历二零二六年二月初四"
        except Exception:
            lunar = "农历（暂不可用）"
    else:
        lunar = "农历（需安装 zhdate）"
    # 节气 / 宜忌：优先调用黄历 API（按日缓存），失败或未配置时回退为占位
    almanac_text = ""
    try:
        from services.weather_almanac import fetch_almanac

        # 按北京时间的「今日」做缓存键
        day = today_beijing()
        global _ALMANAC_CACHE
        if _ALMANAC_CACHE.get("date") != day:
            text = fetch_almanac(day) or ""
            _ALMANAC_CACHE = {"date": day, "text": text}
        almanac_text = _ALMANAC_CACHE.get("text") or ""
    except Exception:
        almanac_text = ""

    if almanac_text:
        # fetch_almanac 已返回宜忌等完整文案，这里直接拼在农历后面
        return f"{lunar} {almanac_text}".strip()

    solar_term = "节气：见黄历"
    yi_ji = "宜忌：见黄历"
    return f"{lunar} {solar_term} {yi_ji}".strip()
