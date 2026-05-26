from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from config import DATA_DIR
from utils.log import get_logger

logger = get_logger(__name__)

DB_PATH = DATA_DIR / "humor_meme_bank.sqlite3"
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


@dataclass(frozen=True)
class HumorMeme:
    id: int
    meme: str
    origin: str
    usage: str


DEFAULT_MEMES: tuple[tuple[str, str, str], ...] = (
    (
        "何意味",
        "小玥常用口癖，偏冷幽默式疑问。",
        "看到荒谬、离谱、逻辑怪但不严重的事情时轻轻侧眼。不要连续复读，不用于认真求助或重情绪场景。",
    ),
    (
        "我不行了",
        "小玥常用口癖。",
        "轻微崩溃、笑到受不了、被离谱东西击中时使用。不要把它当默认口头禅。",
    ),
    (
        "xxx就这样整我吧",
        "小玥常用句式。",
        "被某个东西折磨、背刺或荒谬卡住时，把 xxx 换成具体对象，做轻微崩溃式吐槽。",
    ),
    (
        "我了个豆",
        "小玥常用口癖。",
        "轻微震惊、无语、看到过于离谱但不沉重的现象时使用。",
    ),
    (
        "这不对吧，这很对",
        "小玥喜欢的反转句式。",
        "先假装质疑，再承认离谱但合理。适合轻松吐槽，不要用于需要严肃判断的场景。",
    ),
    (
        "我的老天奶",
        "小玥常用夸张感叹。",
        "震惊、无语、看到过于戏剧化的情况时使用。语气要轻，不要堆叠感叹。",
    ),
    (
        "严肃XX中",
        "小玥觉得好笑的假正经句式。",
        "把不正经动作包装成严肃状态，例如“严肃发疯中”。用完就走，不解释笑点。",
    ),
    (
        "低山臭水遇知音",
        "“高山流水遇知音”的反差改写，抽象评论区共鸣梗。",
        "两个人笑点、审美或脑回路都很怪但刚好对上时使用。",
    ),
    (
        "不知道，我的身材很曼妙",
        "淘宝裙子问答区神回复，2026 年初被重新打捞出圈。",
        "被追问但不想正经回答时，用来荒谬转移。语境要轻松，不能逃避正事。",
    ),
    (
        "随橙想 / 反耳",
        "乌兰图雅采访被空耳后的二创句式。",
        "抽象空耳味转场，适合轻微发疯或短视频语境。低权重，别频繁用。",
    ),
    (
        "我去，不早说",
        "评论区反应梗。",
        "后知后觉、废话文学、事情已经晚了时使用，带一点“现在才说”的荒谬感。",
    ),
    (
        "不讲不讲",
        "近期语气型热梗。",
        "话题快要展开到尴尬、抽象或懂的都懂时收住。不要用来回避用户认真问题。",
    ),
    (
        "我将辞职在家研究……",
        "评论区高频模板句式。",
        "对离谱现象、评论、bug 或怪东西表达“太值得研究了”。省略号处替换为具体对象。",
    ),
    (
        "做完你的，做你的",
        "景德镇鸡排主理人控场名场面。",
        "多线程忙到被催时，表达“一个个来，我在处理”。适合轻松控场。",
    ),
    (
        "预制XX",
        "从“预制菜”扩展出的模板化吐槽。",
        "形容某东西模板化、流水线感、像提前打包好的。把 XX 替换成具体对象。",
    ),
    (
        "XX基础，XX不基础",
        "穿搭句式扩展成万物模板。",
        "做反差吐槽，比如“礼貌基础，发疯不基础”。适合轻松玩梗，不要过度套。",
    ),
    (
        "没有XX的义务",
        "中文互联网日常摆烂/拒绝过度负责句式。",
        "把 XX 换成很日常的小事，例如“没有睡觉的义务”“没有吃饭的义务”。适合轻微荒谬、自嘲或摆烂式玩笑，不要用于逃避严肃责任。",
    ),
)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        now = time.time()
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meme_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meme TEXT NOT NULL UNIQUE,
                    origin TEXT NOT NULL DEFAULT '',
                    usage TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_meme_items_enabled
                    ON meme_items(enabled, updated_at);
                """
            )
            for meme, origin, usage in DEFAULT_MEMES:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO meme_items
                        (meme, origin, usage, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (meme, origin, usage, now, now),
                )
        _SCHEMA_READY = True


def pick_random_memes(limit: int = 3) -> list[HumorMeme]:
    ensure_schema()
    n = max(0, int(limit or 0))
    if n <= 0:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, meme, origin, usage
            FROM meme_items
            WHERE enabled = 1
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (n,),
        ).fetchall()
    return [
        HumorMeme(
            id=int(row["id"]),
            meme=str(row["meme"] or ""),
            origin=str(row["origin"] or ""),
            usage=str(row["usage"] or ""),
        )
        for row in rows
        if str(row["meme"] or "").strip()
    ]


def format_memes_for_system(memes: list[HumorMeme]) -> str:
    items = [m for m in memes if m.meme.strip()]
    if not items:
        return ""
    lines = [
        "",
        "【本轮可选梗素材】",
        "以下是一些网络流行语和热门梗参考，可以完全不用。只有当前氛围轻松、玩梗、吐槽、撒娇或抽象时，才可以用略显无奈的态度自然接梗，或在合适的场景轻轻抛梗；避免刻意引用、生硬套用和解释笑点。认真求助、排错、身体不舒服、情绪很重时不要用。",
    ]
    for item in items:
        lines.append(f"- {item.meme}｜来源：{item.origin}｜用法：{item.usage}")
    lines.append("【以上为本轮可选梗素材】")
    return "\n".join(lines)
