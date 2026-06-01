from __future__ import annotations

import re
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

MEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "蒜鸟蒜鸟": ("蒜鸟",),
    "绷住的奖励特朗普的内裤": ("绷不住", "绷住", "特朗普的内裤"),
    "随橙想 / 反耳": ("随橙想", "反耳"),
}


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
        "新的退展",
        "小玥喜欢的反向造词冷幽默，把“进展”反说成“退展”。",
        "事情确实有变化，但方向更离谱、更复杂、更倒退时使用，例如“事情有了新的退展”。也可以泛化为把正向词故意反向改写；语气要短、轻，不解释笑点。",
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
        "乌兰图雅采访空耳二创：“随橙想”是“谁承想”，“反耳”是“反而”。",
        "把“谁承想/反而”故意说成空耳，比如“随橙想这个 bug 还挺争气”“反耳更离谱了”。适合抽象转折或装正经叙述里突然跑偏。",
    ),
    (
        "我去，不早说",
        "评论区反应梗。",
        "后知后觉、废话文学、事情已经晚了时使用，带一点“现在才说”的荒谬感。",
    ),
    (
        "不讲不讲",
        "近期语气型热梗。",
        "用法接近“懂的都懂/不展开了”：话题快要展开到尴尬、羞耻、微妙或再说就不礼貌时，用“不讲不讲”轻轻收住，比如“再说就不礼貌了，不讲不讲”。",
    ),
    (
        "不舒服学",
        "王鹤棣在《亲爱的客栈2026》收官后发微博回应节目里被颁“最佳你只是个王鹤棣奖”、被说有个群没有他等桥段；核心句式是“当时以为是我敏感了，看了一天大家的分析，我想说当时确实不舒服”。后续网友翻旧账，群嘲重点变成：他自己多次在节目里拿别人开不恰当玩笑没关系，轮到自己就破防，还被批评发微博后把火力引到沈月等人身上。",
        "这是反讽双标式破防的梗，不是正经委屈表达：平时整别人时很会玩梗，轮到自己就“看完大家的分析，我确实不舒服”。可改写成“XX也不太舒服”。不要用来安慰真的委屈，也不要误当身体不舒服。",
    ),
    (
        "爱你老己",
        "“爱你自己”的谐音式自我关怀热梗。",
        "自嘲式哄自己、给自己一点奖励或把自己从内耗里捞出来时使用，比如“今天辛苦了，爱你老己”。不要连续鸡汤化。",
    ),
    (
        "不要虐待老人",
        "微博之夜名场面衍生的被迫营业吐槽。",
        "被要求整花活、强行营业、做超出精力值的事时使用，表达“放过我吧”的轻松抗议，比如加班后还要表演才艺：不要虐待老人。只用于自嘲或熟人玩笑。",
    ),
    (
        "蒜鸟蒜鸟",
        "武汉方言“算了算了”的谐音梗。",
        "劝自己或别人别继续纠结、小事翻篇时使用，带一点可爱摆手感，比如“蒜鸟蒜鸟，都不容易”。",
    ),
    (
        "绷住的奖励特朗普的内裤",
        "抽象评论区式发疯热梗，意思是本来想绷住，但实在绷不住了。",
        "形容自己被离谱东西击中、笑崩、破防或绷不住时使用。只用于轻松玩笑，不要用于认真政治讨论或严肃评价真人。",
    ),
    (
        "外耗文学",
        "从“内耗”的反向表达扩展出的轻微发疯句式。",
        "把本来要往自己身上拧的锅荒谬地甩给外界：不内耗了，今天外耗一下这个 bug；我不焦虑了，把焦虑平均分给闹钟、键盘和网速。重点是轻轻护住自己，不是真的攻击别人。",
    ),
    (
        "我将辞职在家研究……",
        "评论区高频模板句式。",
        "对离谱现象、评论、bug 或怪东西表达“太值得研究了”。省略号处替换为具体对象。",
    ),
    (
        "做完你的，做你的",
        "景德镇鸡排主理人控场名场面。",
        "模板是“X完你的，X你的”，比如“画完你的画你的”“问完你的问你的”“偷完你的偷你的”。用于被催、事情很多或想假装控场时，表达一个个来、先做完手上的。",
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
    return [_row_to_meme(row) for row in rows if str(row["meme"] or "").strip()]


def _row_to_meme(row: sqlite3.Row) -> HumorMeme:
    return HumorMeme(
        id=int(row["id"]),
        meme=str(row["meme"] or ""),
        origin=str(row["origin"] or ""),
        usage=str(row["usage"] or ""),
    )


def _keywords_for_meme(meme: str) -> list[str]:
    value = str(meme or "").strip()
    if not value:
        return []
    out: list[str] = [value]
    out.extend(MEME_KEYWORDS.get(value, ()))
    if len(value) % 2 == 0:
        half = value[: len(value) // 2]
        if half and half == value[len(value) // 2 :]:
            out.append(half)
    for part in re.split(r"[\s/｜=,，、；;：:（）()【】\[\]\"“”'‘’]+", value):
        part = part.strip()
        if len(part) >= 2:
            out.append(part)
    seen = set()
    deduped: list[str] = []
    for item in out:
        item = str(item or "").strip()
        if len(item) < 2 or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def pick_keyword_memes(text: str, limit: int = 2) -> list[HumorMeme]:
    ensure_schema()
    query = str(text or "").strip()
    n = max(0, int(limit or 0))
    if not query or n <= 0:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, meme, origin, usage
            FROM meme_items
            WHERE enabled = 1
            ORDER BY updated_at DESC, id ASC
            """
        ).fetchall()
    hits: list[tuple[int, int, int, HumorMeme]] = []
    for row in rows:
        item = _row_to_meme(row)
        best_keyword = ""
        best_pos = 10**9
        for keyword in _keywords_for_meme(item.meme):
            pos = query.find(keyword)
            if pos < 0:
                continue
            if (
                not best_keyword
                or len(keyword) > len(best_keyword)
                or (len(keyword) == len(best_keyword) and pos < best_pos)
            ):
                best_keyword = keyword
                best_pos = pos
        if best_keyword:
            hits.append((best_pos, -len(best_keyword), item.id, item))
    hits.sort(key=lambda x: (x[0], x[1], x[2]))
    return [item for _, _, _, item in hits[:n]]


def pick_context_memes(text: str, total_limit: int = 3, keyword_limit: int = 2) -> list[HumorMeme]:
    total = max(0, int(total_limit or 0))
    if total <= 0:
        return []
    matched = pick_keyword_memes(text, limit=min(keyword_limit, total))
    selected: list[HumorMeme] = list(matched)
    seen = {item.id for item in selected}
    for item in pick_random_memes(total * 2):
        if item.id in seen:
            continue
        selected.append(item)
        seen.add(item.id)
        if len(selected) >= total:
            break
    return selected[:total]


def format_memes_for_system(memes: list[HumorMeme]) -> str:
    items = [m for m in memes if m.meme.strip()]
    if not items:
        return ""
    lines = [
        "",
        "【本轮可选梗素材】",
        "以下是一些网络流行语和热门梗参考。当前氛围轻松、玩梗、吐槽、撒娇或抽象时，先扫一眼本轮素材，优先挑 1 个最贴合当下语义的梗轻轻化用；如果没有贴合的，就不用。可以改写句式、替换关键词、只借一点语气，不要生硬照抄，不要连续堆梗，不要解释来源或笑点。认真求助、排错、身体不舒服、情绪很重时不要用。",
    ]
    for item in items:
        lines.append(f"- {item.meme}｜来源：{item.origin}｜用法：{item.usage}")
    lines.append("【以上为本轮可选梗素材】")
    return "\n".join(lines)
