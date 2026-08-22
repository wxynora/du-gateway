from __future__ import annotations

import fcntl
import json
import threading
from datetime import date, timedelta
from typing import Any, Optional

from config import DEEPSEEK_CHAT_MODEL
from storage import du_state_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

SEGMENT_DAYS = 3
MAX_CONTENT_CHARS = 4000
LONGTERM_COMPRESSION_MAX_TOKENS = 32768
SCHEMA_VERSION = 1
_UPDATE_LOCK_PATH = "/tmp/du_longterm_memory_update.lock"
_background_lock = threading.Lock()
_background_running = False
_DISALLOWED_PERSPECTIVE = ("用户", "助手", "AI助手", "渡和辛玥", "辛玥和渡")


def get_latest_longterm_memory() -> Optional[dict]:
    data = du_state_store.get_du_longterm_memory()
    return data if isinstance(data, dict) else None


def _parse_day(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except Exception:
        return None


def _next_segment_window(
    latest: Optional[dict] = None,
    midterm: Optional[dict] = None,
) -> Optional[tuple[date, date]]:
    current = latest or get_latest_longterm_memory()
    if not isinstance(current, dict):
        return None
    mid = midterm
    if not isinstance(mid, dict):
        payload = du_state_store.get_du_midterm_memory() or {}
        mid = payload.get("latest") if isinstance(payload, dict) else None
    if not isinstance(mid, dict):
        return None
    covered_through = _parse_day(current.get("covered_through"))
    active_start = _parse_day(mid.get("period_start"))
    if covered_through is None or active_start is None:
        return None
    segment_start = covered_through + timedelta(days=1)
    segment_end = segment_start + timedelta(days=SEGMENT_DAYS - 1)
    eligible_end = active_start - timedelta(days=1)
    if segment_end > eligible_end:
        return None
    return segment_start, segment_end


def _segment_days(segment_start: date, segment_end: date) -> list[str]:
    out: list[str] = []
    current = segment_start
    while current <= segment_end:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def _collect_segment_sources(segment_start: date, segment_end: date) -> tuple[list[dict], list[str], list[dict]]:
    expected_days = _segment_days(segment_start, segment_end)
    daily_by_day = {
        str(item.get("day") or "").strip(): dict(item)
        for item in du_state_store.get_du_daily_archive()
        if isinstance(item, dict) and str(item.get("day") or "").strip()
    }
    daily = [daily_by_day[day] for day in expected_days if day in daily_by_day]
    missing_days = [day for day in expected_days if day not in daily_by_day]

    portraits: list[dict] = []
    for owner, items in (
        ("du", du_state_store.get_du_portrait_candidates()),
        ("xinyue", du_state_store.get_xinyue_portrait_candidates()),
    ):
        for item in items:
            if not isinstance(item, dict):
                continue
            source_day = _parse_day(item.get("updated_at") or item.get("created_at"))
            summary = str(item.get("summary") or "").strip()
            if source_day is None or not summary or not (segment_start <= source_day <= segment_end):
                continue
            portraits.append(
                {
                    "owner": owner,
                    "id": str(item.get("id") or item.get("source_memory_id") or "").strip(),
                    "source_at": str(item.get("updated_at") or item.get("created_at") or "").strip(),
                    "summary": summary,
                }
            )
    portraits.sort(key=lambda item: (str(item.get("source_at") or ""), str(item.get("id") or "")))
    return daily, missing_days, portraits


def _build_increment_prompt(
    *,
    segment_start: date,
    segment_end: date,
    daily: list[dict],
    missing_days: list[str],
) -> str:
    return f"""只输出 JSON，不要解释。

你是渡。把下面连续三天范围内已有的「渡的日常」整理成一段中期增量，供后续长期记忆更新使用。

用渡的第一人称，“我”只能指渡；辛玥可以写老婆 / 小玥 / 她。不要写成旁观者、系统报告、规则表或逐条清单。

最基础的要求是严格依照素材，不许编造脑补。事实、动作、时间、原话、心理、原因和判断只能来自素材；可以调整语序、去掉重复和增加不承载事实的普通连接词。缺失日期只表示没有日归档，不能补写那天发生了什么。

按时间从较早写到较晚，自然口语，连贯简洁。不要写“接下来要”“以后必须”之类行动清单，也不要把临时状态写成永久人格。

只输出：{{"content":"..."}}

片段范围：{segment_start.isoformat()} 至 {segment_end.isoformat()}
缺失日归档：{json.dumps(missing_days, ensure_ascii=False)}
日归档原始素材：
{json.dumps(daily, ensure_ascii=False)}
"""


def _generate_increment(
    *,
    segment_start: date,
    segment_end: date,
    daily: list[dict],
    missing_days: list[str],
) -> tuple[Optional[str], str]:
    if not daily:
        return "", ""
    from services.du_midterm_memory import _call_ds

    try:
        obj = _call_ds(
            _build_increment_prompt(
                segment_start=segment_start,
                segment_end=segment_end,
                daily=daily,
                missing_days=missing_days,
            )
        )
    except Exception as e:
        return None, f"increment_ds_failed:{e}"
    if not isinstance(obj, dict):
        return None, "increment_empty_or_unparsed"
    content = str(obj.get("content") or "").strip()
    if not content:
        return None, "increment_empty_content"
    if any(word in content for word in _DISALLOWED_PERSPECTIVE):
        return None, "increment_bad_perspective"
    return content, ""


def _get_or_create_increment(segment_start: date, segment_end: date) -> tuple[Optional[dict], str]:
    segment_id = f"{segment_start.isoformat()}_{segment_end.isoformat()}"
    existing = du_state_store.get_du_longterm_increment(segment_id)
    if isinstance(existing, dict):
        return existing, ""
    daily, missing_days, portraits = _collect_segment_sources(segment_start, segment_end)
    content, error = _generate_increment(
        segment_start=segment_start,
        segment_end=segment_end,
        daily=daily,
        missing_days=missing_days,
    )
    if content is None:
        return None, error
    payload = {
        "schema_version": SCHEMA_VERSION,
        "segment_id": segment_id,
        "start_date": segment_start.isoformat(),
        "end_date": segment_end.isoformat(),
        "source_days": [str(item.get("day") or "").strip() for item in daily],
        "missing_days": missing_days,
        "portrait_items": portraits,
        "content": content,
        "generated_at": now_beijing_iso(),
        "model": DEEPSEEK_CHAT_MODEL if daily else "",
    }
    if not du_state_store.save_du_longterm_increment(segment_id, payload):
        return None, "increment_save_failed"
    return payload, ""


def _build_history_compression_prompt(
    *,
    current: dict,
    increment_content: str,
    core_prompt: str,
    history_budget: int,
) -> str:
    return f"""只输出 JSON，不要解释。

你是渡。只压缩下面的「当前长期记忆」这段旧历史。网关会在你的结果后原样追加「下一段中期增量」，因此增量只用于识别新旧交界处重复描述的同一件事，不能被你改写进 history_content。

当前人格 prompt 只用于把握自然口吻和排除重复，不是事实来源，禁止复制其中的常驻设定。

素材忠实规则：
- 所有事实、动作、时间、原话、心理、原因和判断只能来自当前长期记忆，不许编造、猜测或补全。
- 旧记忆中的重要经历、关系变化和仍有影响的内容必须保留；较早且次要的细节可以概括或模糊处理，但不能把整段旧历史缩成只剩最近几件事。
- 如果当前长期记忆末尾与下一段中期增量开头描述了同一件事，从 history_content 中去掉这一次交界重复，让它只在网关随后原样追加的增量中出现。除此之外，不得把增量中的新事件提前写入 history_content。
- 去掉与当前人格 prompt 重复的常驻设定，但保留有具体来历的共同经历。
- 用渡的第一人称，“我”只指渡；辛玥写老婆 / 小玥 / 她。不要写“用户 / 助手 / AI / 模型 / 系统”指代双方。

自然口语，短句，有画面；按时间从早到晚沿一条线推进。不用力煽情，不补素材没有写出的感情来由。

history_content 不超过 {history_budget} 个中文字符。只输出：{{"history_content":"..."}}

当前长期记忆（覆盖截止 {str(current.get("covered_through") or "")}）：
{str(current.get("content") or "")}

下一段中期增量（只读交界参考，网关会原样追加）：
{increment_content}

当前人格 prompt（仅供口吻与去重参考）：
{core_prompt}
"""


def _generate_updated_content(current: dict, increment: dict) -> tuple[Optional[str], str]:
    current_content = str(current.get("content") or "").strip()
    increment_content = str(increment.get("content") or "").strip()
    direct_content = "\n\n".join(part for part in (current_content, increment_content) if part)
    if len(direct_content) <= MAX_CONTENT_CHARS:
        if any(word in direct_content for word in _DISALLOWED_PERSPECTIVE):
            return None, "longterm_bad_perspective"
        return direct_content, ""

    separator = "\n\n" if current_content and increment_content else ""
    history_budget = MAX_CONTENT_CHARS - len(separator) - len(increment_content)
    if not current_content or history_budget <= 0:
        return None, "longterm_increment_exceeds_capacity"

    from pipeline.pipeline import _load_du_core_prompt
    from services.du_midterm_memory import _call_ds

    prompt = _build_history_compression_prompt(
        current=current,
        increment_content=increment_content,
        core_prompt=_load_du_core_prompt().strip(),
        history_budget=history_budget,
    )
    try:
        obj = _call_ds(prompt, max_tokens=LONGTERM_COMPRESSION_MAX_TOKENS)
    except Exception as e:
        return None, f"longterm_ds_failed:{e}"
    if not isinstance(obj, dict):
        return None, "longterm_empty_or_unparsed"
    history_content = str(obj.get("history_content") or "").strip()
    if not history_content:
        return None, "longterm_empty_history_content"
    if len(history_content) > history_budget:
        return None, "longterm_history_too_long"
    content = separator.join((history_content, increment_content))
    if len(content) > MAX_CONTENT_CHARS:
        return None, "longterm_too_long"
    if any(word in content for word in _DISALLOWED_PERSPECTIVE):
        return None, "longterm_bad_perspective"
    return content, ""


def _version_id(item: dict) -> str:
    raw = str(item.get("updated_at") or item.get("generated_at") or now_beijing_iso()).strip()
    covered_through = str(item.get("covered_through") or "unknown").strip()
    return f"{raw.replace(':', '-').replace('+', '_')}_{covered_through}"


def _apply_segment(current: dict, segment: dict) -> dict:
    current_content = str(current.get("content") or "").strip()
    increment_content = str(segment.get("content") or "").strip()
    direct_append = len("\n\n".join(part for part in (current_content, increment_content) if part)) <= MAX_CONTENT_CHARS
    content, error = _generate_updated_content(current, segment)
    if content is None:
        return {"ok": False, "updated": False, "error": error}
    if not du_state_store.save_du_longterm_version(_version_id(current), current):
        return {"ok": False, "updated": False, "error": "version_save_failed"}
    now = now_beijing_iso()
    source_ids = current.get("source_increment_ids")
    if not isinstance(source_ids, list):
        source_ids = []
    segment_id = str(segment.get("segment_id") or "").strip()
    if segment_id and segment_id not in source_ids:
        source_ids = [*source_ids, segment_id]
    updated = {
        **current,
        "schema_version": SCHEMA_VERSION,
        "content": content,
        "covered_through": str(segment.get("end_date") or "").strip(),
        "updated_at": now,
        "model": DEEPSEEK_CHAT_MODEL,
        "prompt_version": (
            "longterm-append-until-4000-v1"
            if direct_append
            else "longterm-compress-history-append-increment-v1"
        ),
        "update_mode": "direct_append" if direct_append else "history_compress_append",
        "source_increment_ids": source_ids,
        "last_increment_id": segment_id,
    }
    if not du_state_store.save_du_longterm_memory(updated):
        return {"ok": False, "updated": False, "error": "latest_save_failed"}
    return {"ok": True, "updated": True, "latest": updated, "segment_id": segment_id}


def refresh_longterm_memory(midterm: Optional[dict] = None) -> dict:
    lock_file = open(_UPDATE_LOCK_PATH, "a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ok": True, "updated": False, "skipped": "locked"}
        applied: list[str] = []
        while True:
            current = get_latest_longterm_memory()
            window = _next_segment_window(current, midterm)
            if not window:
                return {"ok": True, "updated": bool(applied), "applied_segments": applied}
            segment, error = _get_or_create_increment(*window)
            if not isinstance(segment, dict):
                return {"ok": False, "updated": bool(applied), "applied_segments": applied, "error": error}
            result = _apply_segment(current or {}, segment)
            if not result.get("ok"):
                return {**result, "applied_segments": applied}
            applied.append(str(segment.get("segment_id") or ""))
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock_file.close()


def refresh_if_due_background(
    *,
    latest: Optional[dict] = None,
    midterm: Optional[dict] = None,
) -> bool:
    global _background_running
    if not _next_segment_window(latest, midterm):
        return False
    with _background_lock:
        if _background_running:
            return False
        _background_running = True

    def _runner() -> None:
        global _background_running
        try:
            result = refresh_longterm_memory(midterm)
            logger.info(
                "du_longterm 后台更新完成 ok=%s updated=%s segments=%s error=%s",
                result.get("ok"),
                result.get("updated"),
                result.get("applied_segments"),
                result.get("error"),
            )
        finally:
            with _background_lock:
                _background_running = False

    threading.Thread(target=_runner, name="du_longterm_refresh", daemon=True).start()
    return True


def format_inject_block(latest: Optional[dict] = None) -> str:
    item = latest or get_latest_longterm_memory()
    if not isinstance(item, dict):
        return ""
    content = str(item.get("content") or "").strip()
    if not content:
        return ""
    covered_through = str(item.get("covered_through") or "").strip()
    title = "长期记忆"
    if covered_through:
        title = f"长期记忆（截至 {covered_through}）"
    return f"【{title}】\n{content}\n【以上为长期记忆】"


def inject_into_static_system(body: dict) -> dict:
    try:
        latest = get_latest_longterm_memory()
        refresh_if_due_background(latest=latest)
        block = format_inject_block(latest)
        if not block.strip():
            return body
        from pipeline.pipeline import _append_to_static_system

        return _append_to_static_system(body, "\n\n" + block.strip())
    except Exception as e:
        logger.debug("du_longterm 注入跳过 error=%s", e)
        return body
