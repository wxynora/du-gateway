"""Independent, low-frequency DeepSeek evaluator for Du's body-state deltas."""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

import requests

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DU_BODY_EVAL_MAX_PENDING,
    DU_BODY_EVAL_MODEL,
    DU_BODY_EVAL_PROMPT_VERSION,
    DU_BODY_EVAL_STALE_SECONDS,
    DU_BODY_EVAL_TIMEOUT_SECONDS,
    DU_BODY_EVALUATOR_APPLY,
    DU_BODY_EVALUATOR_ENABLED,
)
from storage import du_body_eval_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_RUNNING_LOCK = threading.Lock()
_RUNNING_WINDOWS: set[str] = set()
_TIMER_LOCK = threading.Lock()
_WINDOW_TIMERS: dict[str, threading.Timer] = {}
_SPACE_RE = re.compile(r"\s+")

_PROMPT = """你负责分析渡的身体状态数值变化。这是独立状态评估，不是记忆总结，也不是续写对话。

输入包含当前身体状态和按时间排序的若干真实对话轮次。你必须逐轮判断，只根据该轮明确发生的互动输出变化，不能把整批合成一个总变化，不能凭空补剧情。

字段定义与单轮范围：
- stamina_delta（体力，-6..6）：只有持续动作、明显用力、喘累、休息或收尾恢复时变化；纯语言调情通常不变。
- sensitivity_delta（敏感度，-10..12）：贴近、亲吻、挑逗、持续刺激、道具升降档或安抚收尾引起的感官变化。
- possessiveness_delta（占有欲，-12..12）：明确示爱、归属、吃醋、标记氛围或被安抚确认时变化；普通贴贴不必变化。
- mischief_delta（坏心值，-18..18）：拉扯、挑衅、顺从反馈和明确加码念头会升高；真实不适、求停、收尾安抚会降低。普通聊天只有在明确从玩法切回日常时才可小幅 -1..-3。
- restraint_pressure_delta（隐性压强，-35..30）：必须同时存在强烈欲望和明确忍住/死撑才升高；实质推进、释放或明显收尾时降低。

判断规则：
1. 技术讨论、普通闲聊、吃饭睡觉提醒、一般情绪争执默认没有身体变化。
2. 一轮前后状态相反时，以该轮结束时的状态为准。
3. 小玥明确疼、累、不舒服、抗拒或求停时，不上调敏感度、占有欲或坏心值。
4. 无变化的轮次可以不返回；不要为了凑数填 0。
5. round_index 只能取输入里的值；每个 round_index 最多出现一次。
6. reason 用一句简短中文说明依据，不要复述私密原文。

只输出 JSON，不要 markdown：
{"items":[{"round_index":123,"stamina_delta":-3,"sensitivity_delta":4,"reason":"持续动作带来体力消耗和感官升高"}]}
"""


def _extract_json(text: str) -> dict | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(raw[start : end + 1])
            return value if isinstance(value, dict) else None
        except Exception:
            return None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and str(item.get("type") or "") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(parts)
    return str(content or "")


def _prompt_rounds(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        messages: list[dict] = []
        for item in row.get("messages") if isinstance(row.get("messages"), list) else []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            messages.append({"role": role, "content": _content_text(item.get("content"))})
        out.append(
            {
                "round_index": int(row.get("round_index") or 0),
                "timestamp": str(row.get("round_timestamp") or ""),
                "messages": messages,
            }
        )
    return out


def _call_ds(rows: list[dict], current_state: dict) -> tuple[dict[int, dict], int]:
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL or not DU_BODY_EVAL_MODEL:
        raise RuntimeError("body evaluator DeepSeek config missing")
    input_data = {"current_body_state": current_state, "rounds": _prompt_rounds(rows)}
    payload = {
        "model": DU_BODY_EVAL_MODEL,
        "messages": [
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
        ],
        "max_tokens": 1400,
        "temperature": 0,
    }
    started = time.monotonic()
    response = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=int(DU_BODY_EVAL_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    data = response.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    parsed = _extract_json(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("body evaluator response missing items")
    valid_indices = {int(row.get("round_index") or 0) for row in rows}
    by_round: dict[int, dict] = {}
    for raw in parsed.get("items") or []:
        if not isinstance(raw, dict):
            continue
        try:
            idx = int(raw.get("round_index") or 0)
        except Exception:
            continue
        if idx not in valid_indices:
            continue
        by_round[idx] = raw
    return by_round, int((time.monotonic() - started) * 1000)


def _reason(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()[:240]


def _process_batch(batch: dict) -> bool:
    rows = sorted(batch.get("rows") or [], key=lambda row: int(row.get("round_index") or 0))
    if not rows:
        return True
    batch_id = str(batch.get("batch_id") or "")
    try:
        from services.pixel_home import (
            apply_du_body_delta,
            get_du_body_state_snapshot,
            normalize_du_body_delta,
        )

        current_state = get_du_body_state_snapshot()
        items, latency_ms = _call_ds(rows, current_state)
        now_ts = time.time()
        for row in rows:
            idx = int(row.get("round_index") or 0)
            item = items.get(idx)
            event_base = {
                "timestamp": now_beijing_iso(),
                "subsystem": "body_state_delta",
                "source": "body_ds_batch",
                "model": DU_BODY_EVAL_MODEL,
                "prompt_version": str(row.get("prompt_version") or DU_BODY_EVAL_PROMPT_VERSION),
                "window_id": str(row.get("window_id") or ""),
                "round_index": idx,
                "round_hash": str(row.get("round_hash") or ""),
                "batch_id": batch_id,
                "idempotency_key": str(row.get("idempotency_key") or ""),
                "attempt": int(row.get("attempts") or 0),
                "latency_ms": latency_ms,
            }
            if not isinstance(item, dict):
                du_body_eval_store.complete_round(
                    row,
                    batch_id=batch_id,
                    status="no_delta",
                    event={**event_base, "status": "no_delta", "reason": "本轮没有明确身体状态变化"},
                )
                continue
            delta = normalize_du_body_delta(item)
            stale = now_ts - float(row.get("queued_at") or now_ts) >= int(DU_BODY_EVAL_STALE_SECONDS)
            skipped_stamina = False
            if stale and "stamina_value" in delta:
                delta.pop("stamina_value", None)
                skipped_stamina = True
            if not delta:
                du_body_eval_store.complete_round(
                    row,
                    batch_id=batch_id,
                    status="no_delta",
                    event={
                        **event_base,
                        "status": "no_delta",
                        "reason": _reason(item.get("reason")),
                        "stale_stamina_skipped": skipped_stamina,
                    },
                )
                continue
            if not DU_BODY_EVALUATOR_APPLY:
                du_body_eval_store.complete_round(
                    row,
                    batch_id=batch_id,
                    status="shadow",
                    event={
                        **event_base,
                        "status": "shadow",
                        "delta": delta,
                        "reason": _reason(item.get("reason")),
                        "stale_stamina_skipped": skipped_stamina,
                    },
                )
                continue
            applied = apply_du_body_delta(delta, idempotency_key=str(row.get("idempotency_key") or ""))
            if not applied.get("ok"):
                raise RuntimeError(f"body state apply failed round_index={idx}")
            status = "already_applied" if applied.get("duplicate") else "applied"
            du_body_eval_store.complete_round(
                row,
                batch_id=batch_id,
                status=status,
                event={
                    **event_base,
                    "status": status,
                    "before": applied.get("before_state") or {},
                    "delta": applied.get("applied_delta") or delta,
                    "after": applied.get("after_state") or {},
                    "reason": _reason(item.get("reason")),
                    "stale_stamina_skipped": skipped_stamina,
                },
            )
            logger.info(
                "身体状态 delta 已写入 window_id=%s round_index=%s status=%s delta=%s",
                row.get("window_id"),
                idx,
                status,
                applied.get("applied_delta") or delta,
            )
        return True
    except Exception as exc:
        released = du_body_eval_store.fail_batch(batch_id, error=f"{type(exc).__name__}: {exc}")
        logger.warning(
            "身体状态 DS batch 失败 window_id=%s batch_id=%s released=%s error=%s",
            batch.get("window_id"),
            batch_id,
            released,
            exc,
            exc_info=True,
        )
        return False


def _schedule_window(window_id: str, delay: float) -> None:
    wid = str(window_id or "").strip()
    if not wid:
        return
    wait = max(1.0, min(float(delay), 3600.0))
    with _TIMER_LOCK:
        existing = _WINDOW_TIMERS.pop(wid, None)
        if existing is not None:
            existing.cancel()
        timer = threading.Timer(wait, _start_worker, args=(wid,))
        timer.daemon = True
        _WINDOW_TIMERS[wid] = timer
        timer.start()


def _worker(window_id: str) -> None:
    try:
        while True:
            batch = du_body_eval_store.claim_due_batch(window_id)
            if not batch:
                delay = du_body_eval_store.next_wakeup_delay(window_id)
                if delay is not None:
                    _schedule_window(window_id, delay)
                return
            rows = batch.get("rows") or []
            logger.info(
                "身体状态 DS batch 已调度 window_id=%s rounds=%s",
                window_id,
                [int(row.get("round_index") or 0) for row in rows],
            )
            if not _process_batch(batch):
                delay = du_body_eval_store.next_wakeup_delay(window_id)
                if delay is not None:
                    _schedule_window(window_id, delay)
                return
    finally:
        with _RUNNING_LOCK:
            _RUNNING_WINDOWS.discard(window_id)


def _start_worker(window_id: str) -> None:
    wid = str(window_id or "").strip()
    if not wid or not DU_BODY_EVALUATOR_ENABLED:
        return
    with _TIMER_LOCK:
        existing = _WINDOW_TIMERS.pop(wid, None)
        if existing is not None:
            existing.cancel()
    with _RUNNING_LOCK:
        if wid in _RUNNING_WINDOWS:
            return
        _RUNNING_WINDOWS.add(wid)
    threading.Thread(target=_worker, args=(wid,), name=f"body-eval-{wid}", daemon=False).start()


def _is_virtual_round(messages: list) -> bool:
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict):
            continue
        if "[文游]" in _content_text(item.get("content"))[:160]:
            return True
    return False


def enqueue_archived_round(window_id: str, round_index: int, round_messages: list) -> dict:
    if not DU_BODY_EVALUATOR_ENABLED:
        return {"queued": False, "reason": "disabled"}
    if _is_virtual_round(round_messages):
        return {"queued": False, "reason": "virtual_round"}
    result = du_body_eval_store.enqueue_round(window_id, round_index, round_messages)
    if result.get("queued"):
        stats = du_body_eval_store.pending_stats(window_id)
        pending_count = int(stats.get("pending") or 0) + int(stats.get("processing") or 0)
        if pending_count > int(DU_BODY_EVAL_MAX_PENDING):
            logger.warning("身体状态 pending 超过建议上限 window_id=%s pending=%s", window_id, pending_count)
        _start_worker(window_id)
    return result


def resume_pending_workers() -> int:
    if not DU_BODY_EVALUATOR_ENABLED:
        return 0
    windows = du_body_eval_store.active_window_ids()
    for window_id in windows:
        _start_worker(window_id)
    if windows:
        logger.info("身体状态 evaluator 启动恢复 windows=%s", windows)
    return len(windows)
