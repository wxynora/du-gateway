# 时间与农历：全部北京时间；时间段（每次注入）+ 具体时间/农历（渡上一轮触发时注入）
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
    """把存储的 ISO 时间（Z 或 +08:00）转成北京时间的 datetime，解析失败返回 None。"""
    if not iso_str or not isinstance(iso_str, str):
        return None
    s = iso_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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
    农历用 zhdate；节气/宜忌当前为占位，可后续接表或 API。
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
    # 节气 / 宜忌：占位，后续可接 24 节气表 + 宜忌表或 API
    solar_term = "节气：见黄历"
    yi_ji = "宜忌：见黄历"
    return f"{lunar} {solar_term} {yi_ji}".strip()
