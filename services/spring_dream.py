from __future__ import annotations

import random
import threading
from datetime import datetime
from typing import Callable, Optional

from storage import runtime_sqlite
from utils.time_aware import now_beijing_iso

SPRING_DREAM_PROBABILITY = 0.35
SPRING_DREAM_MAX_PER_SLEEP = 3

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


_SPRING_DREAM_THEME_PACKS: list[dict] = [
    {
        "id": "maid_dark_room",
        "fragments": [
            "小玥穿着女仆装，站在床边。",
            "女仆围裙的肩带有点滑落，领口被灯影压得很暗。",
            "房间只开着一盏很低的灯。",
            "她低声叫了你一声，尾音像是故意贴近耳边。",
            "门外似乎有人经过，她却还把你的手拉到自己腰侧。",
        ],
    },
    {
        "id": "rain_hotel",
        "fragments": [
            "窗外在下雨，你和小玥在陌生酒店的高层房间里。",
            "她刚洗完澡，只披着一件松松的浴袍。",
            "浴袍下摆被她坐下时带开了一点。",
            "她把湿发拨到一边，抬眼看你。",
            "房间里只有雨声和她很轻的呼吸声。",
        ],
    },
    {
        "id": "late_library",
        "fragments": [
            "闭馆后的图书馆只剩最后一排灯还亮着。",
            "小玥坐在书桌边，裙摆被椅沿压出皱痕。",
            "她把一本书挡在你们之间，像在遮掩什么。",
            "她靠得很近，声音压得很低。",
            "远处偶尔传来巡夜脚步声，她却没有退开。",
        ],
    },
    {
        "id": "car_backseat",
        "fragments": [
            "夜里停在路边的车厢很窄，车窗覆着雾气。",
            "小玥跨坐在你腿上，外套半披在肩上。",
            "安全带扣被她碰得轻响了一声。",
            "她低头看你，指尖慢慢按住你的胸口。",
            "车外有人路过，影子从玻璃上一闪而过。",
        ],
    },
    {
        "id": "private_onsen",
        "fragments": [
            "你们在一间很安静的私汤里，水汽把四周都蒙住了。",
            "小玥从温泉水里靠近你，湿发贴在锁骨旁。",
            "她的浴巾松松搭着，像随时会滑下去。",
            "水面被她靠近时推开一圈圈波纹。",
            "她贴着你笑了一下，声音被水汽压得又软又低。",
        ],
    },
    {
        "id": "dressing_room",
        "fragments": [
            "商场试衣间的帘子只拉到一半。",
            "小玥穿着刚换上的短裙，站在镜子前回头看你。",
            "她让你帮她拉背后的拉链，指尖却按住你的手不放。",
            "外面有人在走动，衣架碰撞声断断续续传进来。",
            "她贴近镜子，像故意让你从镜中看见她的表情。",
        ],
    },
    {
        "id": "stage_aftershow",
        "fragments": [
            "后台化妆间只剩一盏镜前灯。",
            "小玥穿着演出后的礼服，肩带被她自己拨到臂弯。",
            "亮片落在她颈侧和锁骨上。",
            "她坐在化妆台边，把高跟鞋轻轻踢到一旁。",
            "门外还有散场的人声，她却伸手把你拉近。",
        ],
    },
    {
        "id": "office_after_hours",
        "fragments": [
            "深夜办公室里只亮着你们这一张桌子的台灯。",
            "小玥坐在桌沿，衬衫下摆被她自己扯得有点乱。",
            "她把文件推到一边，抬腿轻轻勾住你。",
            "玻璃门外的走廊偶尔亮一下感应灯。",
            "她压低声音问你还要不要继续装正经。",
        ],
    },
    {
        "id": "train_sleeper",
        "fragments": [
            "夜行列车的包厢在轻轻晃。",
            "小玥坐在下铺边，宽大的睡衣从肩头滑下来。",
            "窗外的灯光一段一段掠过她的脸。",
            "她拉住你的手腕，让你坐到她身边。",
            "隔壁铺位传来细微动静，她却更近地贴住你。",
        ],
    },
    {
        "id": "snow_cabin",
        "fragments": [
            "雪夜的小木屋里壁炉烧得很热。",
            "小玥裹着你的衬衫，赤脚踩在地毯上。",
            "衬衫扣子只扣了两颗，随着她弯身时松开一点。",
            "她把你推回沙发里，膝盖抵在你身侧。",
            "窗外全是雪，屋里只剩火光和她的声音。",
        ],
    },
    {
        "id": "locker_room",
        "fragments": [
            "空荡的更衣室里灯光有点白。",
            "小玥披着一件宽大的运动外套，里面像是刚换到一半。",
            "储物柜门被她用手肘轻轻碰上。",
            "她靠在柜门前，抬眼看你，像在等你先靠近。",
            "走廊尽头有人说话，她却把你拉进更暗的一格阴影里。",
        ],
    },
    {
        "id": "balcony_party",
        "fragments": [
            "热闹的派对隔着阳台门变得很远。",
            "小玥穿着贴身的小礼裙，背靠着夜风里的栏杆。",
            "她把酒杯放到一边，指尖带着一点凉意。",
            "裙摆被风吹起来一点，又被她慢慢按住。",
            "室内有人找她，她却只看着你，没立刻回头。",
        ],
    },
]


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with runtime_sqlite.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS spring_dream_sessions (
                    sleep_session_key TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    max_per_sleep INTEGER NOT NULL DEFAULT 3,
                    last_theme_id TEXT NOT NULL DEFAULT '',
                    sleep_source TEXT NOT NULL DEFAULT '',
                    reserved_at TEXT NOT NULL DEFAULT '',
                    last_sent_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_sessions_updated
                    ON spring_dream_sessions(updated_at);
                """
            )
        _SCHEMA_READY = True


def _prune_old_sessions(conn, now_iso: str) -> None:
    day = str(now_iso or "")[:10]
    if not day:
        return
    conn.execute(
        "DELETE FROM spring_dream_sessions WHERE updated_at != '' AND updated_at < date(?, '-14 days')",
        (day,),
    )


def _session_row(session_key: str) -> dict:
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM spring_dream_sessions WHERE sleep_session_key=?",
            (str(session_key or "").strip(),),
        ).fetchone()
    if row is None:
        return {}
    return {
        "sleep_session_key": str(row["sleep_session_key"] or ""),
        "count": int(row["count"] or 0),
        "max_per_sleep": int(row["max_per_sleep"] or 0),
        "last_theme_id": str(row["last_theme_id"] or ""),
        "sleep_source": str(row["sleep_source"] or ""),
        "reserved_at": str(row["reserved_at"] or ""),
        "last_sent_at": str(row["last_sent_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _recent_session_key_for_night(night_date: str) -> str:
    clean_night = str(night_date or "").strip()
    if not clean_night:
        return ""
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT sleep_session_key
            FROM spring_dream_sessions
            WHERE sleep_session_key LIKE ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (f"{clean_night}|%",),
        ).fetchone()
    return str(row["sleep_session_key"] or "").strip() if row is not None else ""


def _reset_night_sessions(night_date: str) -> None:
    clean_night = str(night_date or "").strip()
    if not clean_night:
        return
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "DELETE FROM spring_dream_sessions WHERE sleep_session_key LIKE ?",
            (f"{clean_night}|%",),
        )


def _reserve_spring_dream_slot(
    *,
    session_key: str,
    sleep_source: str,
    max_per_sleep: int,
    rng: random.Random | None = None,
) -> dict | None:
    clean_key = str(session_key or "").strip()
    if not clean_key:
        return None
    limit = max(1, int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP))
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _prune_old_sessions(conn, now_iso)
            row = conn.execute(
                "SELECT * FROM spring_dream_sessions WHERE sleep_session_key=?",
                (clean_key,),
            ).fetchone()
            count = int(row["count"] or 0) if row is not None else 0
            if count >= limit:
                conn.execute("ROLLBACK")
                return None
            previous_theme = str(row["last_theme_id"] or "") if row is not None else ""
            theme = _choose_theme(previous_theme, rng=rng)
            theme_id = str(theme.get("id") or "").strip()
            count_after = count + 1
            if row is None:
                conn.execute(
                    """
                    INSERT INTO spring_dream_sessions (
                        sleep_session_key, count, max_per_sleep, last_theme_id,
                        sleep_source, reserved_at, last_sent_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, '', ?)
                    """,
                    (clean_key, count_after, limit, theme_id, str(sleep_source or "").strip(), now_iso, now_iso),
                )
            else:
                conn.execute(
                    """
                    UPDATE spring_dream_sessions
                    SET count=?, max_per_sleep=?, last_theme_id=?, sleep_source=?,
                        reserved_at=?, updated_at=?
                    WHERE sleep_session_key=?
                    """,
                    (count_after, limit, theme_id, str(sleep_source or "").strip(), now_iso, now_iso, clean_key),
                )
            conn.execute("COMMIT")
            return {
                "count_before": count,
                "count_after": count_after,
                "theme": theme,
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_spring_dream_slot(prepared: dict) -> bool:
    session_key = str((prepared or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        return False
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT count FROM spring_dream_sessions WHERE sleep_session_key=?",
                (session_key,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return False
            count = max(0, int(row["count"] or 0) - 1)
            conn.execute(
                """
                UPDATE spring_dream_sessions
                SET count=?, updated_at=?
                WHERE sleep_session_key=?
                """,
                (count, now_iso, session_key),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _choose_theme(previous_theme_id: str = "", rng: random.Random | None = None) -> dict:
    picker = rng or random
    pool = [item for item in _SPRING_DREAM_THEME_PACKS if item.get("id") != previous_theme_id]
    if not pool:
        pool = list(_SPRING_DREAM_THEME_PACKS)
    return picker.choice(pool)


def build_spring_dream_prompt(fragments: list[str]) -> str:
    lines = ["【春梦触发】", "你正在做一个有关小玥的春梦。", "这个梦里："]
    lines.extend(f"- {str(item).strip()}" for item in fragments if str(item).strip())
    lines.extend(["", "请你自己补全梦里的具体片段和感受。"])
    return "\n".join(lines).strip()


def maybe_prepare_spring_dream_wakeup(
    *,
    now_dt: datetime,
    chance: float = SPRING_DREAM_PROBABILITY,
    max_per_sleep: int = SPRING_DREAM_MAX_PER_SLEEP,
    roll: Callable[[], float] | None = None,
    rng: random.Random | None = None,
) -> Optional[dict]:
    try:
        from services.pixel_home import build_sleep_wakeup_state

        sleep_state = build_sleep_wakeup_state(now_dt)
    except Exception:
        return None

    if not bool((sleep_state or {}).get("is_sleeping")):
        _reset_night_sessions(str((sleep_state or {}).get("night_date") or "").strip())
        return None

    session_key = str((sleep_state or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        return None
    session_key = _recent_session_key_for_night(str((sleep_state or {}).get("night_date") or "").strip()) or session_key

    roller = roll or random.random
    try:
        threshold = max(0.0, min(1.0, float(chance)))
    except Exception:
        threshold = SPRING_DREAM_PROBABILITY
    if float(roller()) >= threshold:
        return None

    reserved = _reserve_spring_dream_slot(
        session_key=session_key,
        sleep_source=str((sleep_state or {}).get("source") or "").strip(),
        max_per_sleep=int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP),
        rng=rng,
    )
    if not reserved:
        return None
    theme = reserved.get("theme") if isinstance(reserved.get("theme"), dict) else {}
    fragments = [str(item).strip() for item in (theme.get("fragments") or []) if str(item).strip()]
    return {
        "prompt": build_spring_dream_prompt(fragments),
        "theme_id": str(theme.get("id") or "").strip(),
        "sleep_session_key": session_key,
        "sleep_source": str((sleep_state or {}).get("source") or "").strip(),
        "count_before": int(reserved.get("count_before") or 0),
        "count_after": int(reserved.get("count_after") or 0),
        "max_per_sleep": int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP),
        "reserved": True,
    }


def record_spring_dream_sent(prepared: dict, *, sent_at: str = "") -> bool:
    session_key = str((prepared or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        return False
    now_iso = str(sent_at or "").strip() or now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE spring_dream_sessions
            SET last_sent_at=?, updated_at=?
            WHERE sleep_session_key=?
            """,
            (now_iso, now_iso, session_key),
        )
    return True
