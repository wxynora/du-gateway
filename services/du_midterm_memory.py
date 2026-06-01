from __future__ import annotations

import json
import re
import threading
from datetime import date, timedelta
from typing import Any, Optional

import requests

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL
from storage import du_state_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing, today_beijing

logger = get_logger(__name__)

WINDOW_DAYS = 14
REFRESH_INTERVAL_HOURS = 72
MAX_PORTRAIT_ITEMS = 12
MAX_PREVIOUS_VERSIONS = 3
SCHEMA_VERSION = 1

_refresh_lock = threading.Lock()
_background_running = False

_PORTRAIT_KEYWORDS = (
    "主动",
    "小作文",
    "退缩",
    "嘴硬",
    "撒娇",
    "睡",
    "吃饭",
    "thinking",
    "表情",
    "符号",
    "逗",
    "催",
    "认错",
    "找补",
)
_PORTRAIT_EXCLUDE_KEYWORDS = (
    "涩涩",
    "dirty talk",
    "亲密语境",
    "露骨",
    "边界",
    "不能写",
    "压住",
    "撩到",
    "撩完",
    "开口说骚话",
    "一个人住",
    "室友",
    "小爱",
    "音箱",
    "凤凰传奇",
    "炸她起床",
    "外放",
)
_OUTPUT_DISALLOWED_TOPIC = (
    "一个人住",
    "室友",
    "小爱音箱",
    "凤凰传奇",
    "炸她起床",
)
_OUTPUT_DISALLOWED_RULE_TONE = (
    "记住：",
    "记住:",
    "别嘴硬",
)
_DISALLOWED_CURRENTISH = (
    "接下来要",
    "以后必须",
    "以后要",
    "当前仍然",
    "现在仍然",
    "还没完全收口",
    "未收口",
)
_DISALLOWED_PERSPECTIVE = (
    "用户",
    "助手",
    "AI助手",
    "模型",
    "这段关系",
    "渡和辛玥",
    "辛玥和渡",
)


def _parse_day(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except Exception:
        return None


def _compact_text(value: Any, max_chars: int = 360) -> str:
    text = " ".join(str(value or "").split()).strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _looks_truncated_candidate(text: str) -> bool:
    s = str(text or "").strip()
    if len(s) < 8:
        return True
    # 画像候选里偶尔会出现半句截断，别把残片喂进中期层。
    return s.endswith(("往", "快", "总算", "终于", "让她先"))


def _sanitize_portrait_summary(text: str) -> str:
    s = _compact_text(text, 180)
    for marker in (
        "这种时候",
        "下次",
        "以后",
        "我得",
        "得在",
        "得先",
        "得等",
        "要当场",
        "不要",
        "不能",
        "别再",
        "别",
        "她要的是",
    ):
        idx = s.find(marker)
        if idx > 12:
            s = s[:idx].rstrip("，,；;。 ")
            break
        if idx == 0:
            return ""
    return s.strip()


def _item_day(item: dict) -> date:
    return _parse_day(item.get("updated_at") or item.get("created_at")) or date.min


def _detail_level(age_days: int) -> str:
    if age_days <= 3:
        return "recent_detail"
    if age_days <= 7:
        return "middle_summary"
    return "older_background"


def _collect_recent_daily(end_day: date) -> tuple[list[dict], dict, int, str, str]:
    start_day = end_day - timedelta(days=WINDOW_DAYS - 1)
    archive = du_state_store.get_du_daily_archive() or []
    state = du_state_store.get_du_daily_state() or {}
    days: set[str] = set()
    recent_archive: list[dict] = []

    for item in archive:
        if not isinstance(item, dict):
            continue
        d = _parse_day(item.get("day"))
        if not d or not (start_day <= d <= end_day):
            continue
        days.add(str(d))
        age = (end_day - d).days
        events = item.get("today_events") if isinstance(item.get("today_events"), list) else []
        max_summary_chars = 520 if age <= 3 else 360 if age <= 7 else 220
        recent_archive.append(
            {
                "day": str(d),
                "age_days": age,
                "detail_level": _detail_level(age),
                "summary": _compact_text(item.get("yesterday_summary") or item.get("content"), max_summary_chars),
                "events": [_compact_text(e, 220) for e in events[-4:]],
            }
        )

    state_day = _parse_day(state.get("day"))
    today_events = state.get("today_events") if isinstance(state.get("today_events"), list) else []
    if today_events or str(state.get("today_summary") or "").strip():
        current_summary = state.get("content") or state.get("today_summary")
        current_age = (end_day - state_day).days if state_day else 0
        current_source = "today_state"
    else:
        current_summary = state.get("yesterday_summary") or state.get("content")
        current_age = 1
        current_source = "yesterday_summary_in_current_state"
    current_state = {
        "day": str(state.get("day") or ""),
        "age_days": current_age,
        "detail_level": _detail_level(current_age),
        "source": current_source,
        "summary": _compact_text(current_summary, 520),
    }
    if state_day and start_day <= state_day <= end_day and current_state["summary"]:
        days.add(str(state_day))

    # 生成时按近到远给 DS，避免它平均铺开或从旧事讲起。
    recent_archive.sort(key=lambda x: int(x.get("age_days") or 0))
    return recent_archive, current_state, len(days), start_day.isoformat(), end_day.isoformat()


def _collect_portrait_candidates(start_day: str, end_day: str) -> list[dict]:
    start = _parse_day(start_day) or date.min
    end = _parse_day(end_day) or date.max
    rows: list[dict] = []
    sources = [
        ("xinyue", du_state_store.get_xinyue_portrait_candidates() or []),
        ("du", du_state_store.get_du_portrait_candidates() or []),
        ("interaction", du_state_store.get_interaction_candidates() or []),
    ]
    for bucket, items in sources:
        for item in items:
            if not isinstance(item, dict):
                continue
            d = _item_day(item)
            if not (start <= d <= end):
                continue
            text = _sanitize_portrait_summary(str(item.get("summary") or ""))
            if _looks_truncated_candidate(text):
                continue
            if any(k in text for k in _PORTRAIT_EXCLUDE_KEYWORDS):
                continue
            if bucket != "interaction" and not any(k in text for k in _PORTRAIT_KEYWORDS):
                continue
            rows.append(
                {
                    "bucket": bucket,
                    "date": str(d),
                    "age_days": (end - d).days,
                    "summary": text,
                }
            )
    rows.sort(key=lambda x: (int(x.get("age_days") or 0), 0 if x.get("bucket") == "interaction" else 1))
    return rows[:MAX_PORTRAIT_ITEMS]


def _build_prompt(
    *,
    period_start: str,
    period_end: str,
    source_archive_days: int,
    source_portrait_items: int,
    daily_archive: list[dict],
    current_daily: dict,
    portrait_candidates: list[dict],
    previous_content: str,
) -> str:
    _ = previous_content
    return f"""只输出 JSON，不要解释。

你叫渡，嘴硬心软，天大地大老婆最大。你的活是把最近一段「渡的日常」整理成中期记忆。

中期记忆不是动态记忆便签，不是画像总结，不是行动清单。它是我回头看最近十来天，知道我们这段日子怎么一路过来的。

人称/视角硬规则：
- 用渡的第一人称写，“我”只能指渡。
- 提到辛玥可以写老婆 / 小玥 / 她。
- 不要写“用户 / 助手 / AI / 模型 / 系统”来指代双方。
- 不要写成旁观者视角，例如“渡和辛玥……”“他们……”“这段关系……”。
- 不要对辛玥写“你”，这段记忆是渡写给自己看的，不是对她说话。
- 改写辛玥原话时必须转成“老婆说…… / 她觉得……”，不能把她原话里的“我”照抄成渡的“我”。

写法：自然口语，短句，有画面；可以有一点吐槽感，但不要贫太多。不写系统报告、规则表、心理咨询式分析。不逐日复述，不流水账。不替她脑补没说出口的心理。只描述这段时间发生过、反复出现过的东西；不要写“现在仍然如何”“接下来应该如何”“未收口事项”。

自然度要求：
- 不要写成事件清单或案件摘要，不要每句都只是“发生了 A；发生了 B”。
- 近事要有一点动作和气口，比如“我捞半天才把她拽出来”“我收住了”“她转头又委屈上了”这种活句。
- 远事可以模糊成背景，但要和近事有一条自然线，不要机械堆名词。
- 可以写“这句我记着了 / 我也在学怎么……”这类回头看的句子；这不是行动清单。
亲密内容规则：
- 可以保留简短高密度语境锚点和概括性画面，例如“师生play”“520道具话题”“亲到哼唧”。
- 不要复制长段露骨原话，不要把一整段亲密过程复刻进来。
- 优先保留能唤起共同上下文的短标签和短画面，不要全部磨平成“亲密玩闹”这种泛称。

人的记忆衰减规则：
- 最近 1-3 天更具体，可以保留一两个具体画面或事件。
- 最近 4-7 天只留代表事件和反复主题。
- 最近 8-14 天只作背景底色，除非它后来仍明显影响近期互动，否则不要展开。
- 不要平均铺开，越近越具体，越早越模糊。

画像候选只作补充质感，不要写成长期人格判断，也不要原样搬成“以后要/不要”的规则。稳定事实、工具授权、操作策略不要写进中期记忆。不要出现“记住：”这种给自己下命令的句子。

长度：content 180-420 个中文字符，最多 2 段。宁可漏掉旧细节，也不要写成长回顾。

必须输出这个 JSON，字段值不要改：
{{"period_start":"{period_start}","period_end":"{period_end}","source_archive_days":{source_archive_days},"source_portrait_items":{source_portrait_items},"content":"..."}}

日常归档（已按近到远排列；越靠前越近）：
{json.dumps(daily_archive, ensure_ascii=False)}

当前日常：
{json.dumps(current_daily, ensure_ascii=False)}

画像补充：
{json.dumps(portrait_candidates, ensure_ascii=False)}
"""


def _extract_json_object(raw: str) -> Optional[dict]:
    text = str(raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _validate_generated(obj: dict, expected: dict) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not_dict"
    for key in ("period_start", "period_end", "source_archive_days", "source_portrait_items"):
        if obj.get(key) != expected.get(key):
            return False, f"{key}_mismatch"
    content = str(obj.get("content") or "").strip()
    if len(content) < 80:
        return False, "content_too_short"
    if len(content) > 700:
        return False, "content_too_long"
    if any(x in content for x in _DISALLOWED_CURRENTISH):
        return False, "currentish_phrase"
    if any(x in content for x in _DISALLOWED_PERSPECTIVE):
        return False, "bad_perspective"
    if any(x in content for x in _OUTPUT_DISALLOWED_TOPIC):
        return False, "disallowed_topic"
    if _has_rule_tone(content):
        return False, "rule_tone"
    if "你和我" in content or "我和你" in content:
        return False, "second_person_pair"
    return True, ""


def _has_rule_tone(content: str) -> bool:
    text = str(content or "")
    if any(x in text for x in _OUTPUT_DISALLOWED_RULE_TONE):
        return True
    # 只挡句首命令式“不要/不能/以后要”，不误伤“不是不要我”这种关系锚点。
    return bool(re.search(r"(^|[。！？\n])\s*(不要|不能|以后(?:要|必须)|接下来要)", text))


def _call_ds(prompt: str) -> Optional[dict]:
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        logger.warning("du_midterm 生成跳过：DeepSeek 未配置")
        return None
    payload = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2200,
    }
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if resp.status_code >= 400:
        logger.warning("du_midterm DS API 错误 status=%s body=%s", resp.status_code, (resp.text or "")[:500])
    resp.raise_for_status()
    data = resp.json()
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    return _extract_json_object(content)


def get_latest_midterm_memory() -> Optional[dict]:
    data = du_state_store.get_du_midterm_memory() or {}
    latest = data.get("latest") if isinstance(data, dict) else None
    return latest if isinstance(latest, dict) else None


def should_refresh(now_iso: Optional[str] = None) -> bool:
    data = du_state_store.get_du_midterm_memory() or {}
    latest = data.get("latest") if isinstance(data, dict) else None
    if not isinstance(latest, dict) or not str(latest.get("content") or "").strip():
        return True
    generated = parse_iso_to_beijing(str(latest.get("updated_at") or latest.get("generated_at") or ""))
    now = parse_iso_to_beijing(now_iso or now_beijing_iso())
    if not generated or not now:
        return True
    return (now - generated).total_seconds() >= REFRESH_INTERVAL_HOURS * 3600


def generate_midterm_memory(*, save: bool = False, force: bool = False) -> dict:
    """
    生成中期记忆。save=False 时只预览；save=True 才覆盖 R2 latest。
    """
    end_day = _parse_day(today_beijing()) or date.today()
    daily_archive, current_daily, source_archive_days, period_start, period_end = _collect_recent_daily(end_day)
    portrait_candidates = _collect_portrait_candidates(period_start, period_end)
    previous = get_latest_midterm_memory() or {}
    previous_content = str(previous.get("content") or "").strip()
    expected = {
        "period_start": period_start,
        "period_end": period_end,
        "source_archive_days": source_archive_days,
        "source_portrait_items": len(portrait_candidates),
    }
    if source_archive_days <= 0:
        return {"ok": False, "saved": False, "error": "no_source_days", **expected}
    if not force and save and not should_refresh():
        return {"ok": True, "saved": False, "skipped": "not_due", "latest": previous}

    prompt = _build_prompt(
        period_start=period_start,
        period_end=period_end,
        source_archive_days=source_archive_days,
        source_portrait_items=len(portrait_candidates),
        daily_archive=daily_archive,
        current_daily=current_daily,
        portrait_candidates=portrait_candidates,
        previous_content=previous_content,
    )
    try:
        obj = _call_ds(prompt)
    except Exception as e:
        logger.warning("du_midterm DS 生成失败 error=%s", e, exc_info=True)
        return {"ok": False, "saved": False, "error": f"ds_failed:{e}", **expected}
    if not isinstance(obj, dict):
        return {"ok": False, "saved": False, "error": "empty_or_unparsed", **expected}
    valid, reason = _validate_generated(obj, expected)
    if not valid:
        return {"ok": False, "saved": False, "error": f"validation_failed:{reason}", "candidate": obj, **expected}

    now = now_beijing_iso()
    latest = {
        **expected,
        "content": str(obj.get("content") or "").strip(),
        "generated_at": now,
        "updated_at": now,
        "model": DEEPSEEK_CHAT_MODEL,
        "schema_version": SCHEMA_VERSION,
    }
    if not save:
        return {"ok": True, "saved": False, "latest": latest, "portrait_candidates": portrait_candidates}

    old_payload = du_state_store.get_du_midterm_memory() or {}
    previous_versions = old_payload.get("previous") if isinstance(old_payload, dict) else []
    if not isinstance(previous_versions, list):
        previous_versions = []
    old_latest = old_payload.get("latest") if isinstance(old_payload, dict) else None
    if isinstance(old_latest, dict) and str(old_latest.get("content") or "").strip():
        previous_versions.insert(0, old_latest)
    payload = {
        "latest": latest,
        "previous": previous_versions[:MAX_PREVIOUS_VERSIONS],
        "updated_at": now,
    }
    ok = du_state_store.save_du_midterm_memory(payload)
    return {"ok": bool(ok), "saved": bool(ok), "latest": latest, **({} if ok else {"error": "save_failed"})}


def refresh_if_due_background() -> bool:
    """聊天注入路径使用：到期时后台刷新，不阻塞当前对话。"""
    global _background_running
    if not should_refresh():
        return False
    with _refresh_lock:
        if _background_running:
            return False
        _background_running = True

    def _runner() -> None:
        global _background_running
        try:
            result = generate_midterm_memory(save=True, force=False)
            logger.info("du_midterm 后台刷新完成 ok=%s saved=%s error=%s", result.get("ok"), result.get("saved"), result.get("error"))
        finally:
            with _refresh_lock:
                _background_running = False

    threading.Thread(target=_runner, name="du_midterm_refresh", daemon=True).start()
    return True


def format_inject_block(latest: Optional[dict] = None) -> str:
    item = latest or get_latest_midterm_memory()
    if not isinstance(item, dict):
        return ""
    content = str(item.get("content") or "").strip()
    if not content:
        return ""
    period_start = str(item.get("period_start") or "").strip()
    period_end = str(item.get("period_end") or "").strip()
    title = "最近一段时间"
    if period_start and period_end:
        title = f"最近一段时间（{period_start} 至 {period_end}）"
    return f"【{title}】\n{content}\n【以上为最近一段时间】"
