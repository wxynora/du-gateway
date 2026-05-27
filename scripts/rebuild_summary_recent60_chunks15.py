"""
Rebuild the global realtime summary from the latest raw conversation rounds.

This one-off repair script:
- reads the latest 60 rounds for a window from R2;
- groups them as 15 x 4-round chunks;
- asks DeepSeek only for each chunk's new_chunk, without running conveyor moves;
- writes chunks as older 4 / slightly 8 / recent 3 when --apply is passed.

Default mode is a dry run.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL
from services.deepseek_summary import (
    _SUMMARY_JSON_RETRY_INSTRUCTION,
    _SUMMARY_OLDER_LEVEL,
    _SUMMARY_OLDER_MAX_CHUNKS,
    _SUMMARY_RECENT_LEVEL,
    _SUMMARY_RECENT_MAX_CHUNKS,
    _SUMMARY_RETRY_INSTRUCTION,
    _SUMMARY_SLIGHTLY_LEVEL,
    _SUMMARY_SLIGHTLY_MAX_CHUNKS,
    _clean_summary_chunk_text,
    _extract_summary_json,
    _summary_json_has_forbidden_second_person,
    _summary_rounds_meta,
    _trim_summary_to_budget,
    build_summary_prompt,
    render_summary_from_chunks,
)
from storage import r2_store
from utils.time_aware import now_beijing_iso
from utils.tokens import memory_summary_budget


GROUP_SIZE = 4


def _default_window_id() -> str:
    uid = str(os.environ.get("TELEGRAM_PROACTIVE_TARGET_USER_ID") or "").strip()
    return f"tg_{uid}" if uid else ""


def _round_index(raw: object) -> int:
    if not isinstance(raw, dict):
        return 0
    try:
        return int(raw.get("index") or 0)
    except Exception:
        return 0


def _groups_from_rounds(rounds: list[dict], group_size: int, group_count: int) -> list[list[dict]]:
    wanted = group_size * group_count
    selected = list(rounds or [])[-wanted:]
    full_groups: list[list[dict]] = []
    for i in range(0, len(selected), group_size):
        group = selected[i : i + group_size]
        if len(group) == group_size:
            full_groups.append(group)
    return full_groups[-group_count:]


def _rounds_by_exact_range(window_id: str, start: int, end: int) -> list[dict]:
    rounds: list[dict] = []
    missing: list[int] = []
    for idx in range(start, end + 1):
        item = r2_store.get_conversation_round_by_index(window_id, idx)
        if isinstance(item, dict):
            rounds.append(item)
        else:
            missing.append(idx)
    if missing:
        raise RuntimeError(f"missing rounds: {missing[:8]}")
    return rounds


def _request_new_chunk(group: list[dict], *, attempts: int = 3) -> str | None:
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        print("错误：缺少 DEEPSEEK_API_KEY 或 DEEPSEEK_API_URL。", file=sys.stderr)
        return None

    base_prompt = build_summary_prompt(
        recent_4_rounds=group,
        chunk_to_compress_to_slightly=None,
        chunk_to_compress_to_older=None,
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    retry_suffix = ""
    last_error = ""
    for attempt in range(1, attempts + 1):
        payload = {
            "model": DEEPSEEK_CHAT_MODEL,
            "messages": [{"role": "user", "content": base_prompt + retry_suffix}],
            "max_tokens": 1400,
        }
        try:
            resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            parsed = _extract_summary_json(content)
            if not parsed:
                last_error = "返回非 JSON"
                retry_suffix = _SUMMARY_JSON_RETRY_INSTRUCTION
            elif _summary_json_has_forbidden_second_person(parsed):
                last_error = "命中第二人称违规"
                retry_suffix = _SUMMARY_RETRY_INSTRUCTION
            else:
                text = _clean_summary_chunk_text(parsed.get("new_chunk"), 700)
                if text:
                    return text
                last_error = "new_chunk 为空"
                retry_suffix = _SUMMARY_JSON_RETRY_INSTRUCTION
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts:
            print(f"  第 {attempt} 次失败：{last_error}，5 秒后重试...", flush=True)
            time.sleep(5)
    print(f"错误：DeepSeek 生成小段失败：{last_error}", file=sys.stderr)
    return None


def _assign_levels(chunks: list[dict]) -> list[dict]:
    total = len(chunks)
    recent_start = max(0, total - _SUMMARY_RECENT_MAX_CHUNKS)
    slightly_start = max(0, recent_start - _SUMMARY_SLIGHTLY_MAX_CHUNKS)
    out: list[dict] = []
    for idx, item in enumerate(chunks):
        next_item = dict(item)
        if idx >= recent_start:
            next_item["level"] = _SUMMARY_RECENT_LEVEL
        elif idx >= slightly_start:
            next_item["level"] = _SUMMARY_SLIGHTLY_LEVEL
            next_item["rebuilt_to_slightly"] = True
        else:
            next_item["level"] = _SUMMARY_OLDER_LEVEL
            next_item["rebuilt_to_older"] = True
        out.append(next_item)
    return out


def _preserved_update_count() -> int:
    state = r2_store.get_summary_chunks("") or {}
    try:
        return max(0, int(state.get("update_count") or 0))
    except Exception:
        chunks = state.get("chunks") if isinstance(state, dict) else []
        return len(chunks) if isinstance(chunks, list) else 0


def _print_preview(chunks_state: dict, summary: str) -> None:
    chunks = chunks_state.get("chunks") or []
    counts = Counter(str(item.get("level") or "") for item in chunks)
    print("\n===== 15 段重建预览 =====")
    print(
        "levels: "
        f"older={counts.get(_SUMMARY_OLDER_LEVEL, 0)} "
        f"slightly={counts.get(_SUMMARY_SLIGHTLY_LEVEL, 0)} "
        f"recent={counts.get(_SUMMARY_RECENT_LEVEL, 0)}"
    )
    print(f"update_count preserved: {chunks_state.get('update_count')}")
    for idx, item in enumerate(chunks, 1):
        text = str(item.get("text") or "").replace("\n", " ")
        if len(text) > 96:
            text = text[:96].rstrip() + "..."
        print(
            f"{idx:02d}. {item.get('level')} "
            f"rounds {item.get('round_start')}-{item.get('round_end')} "
            f"{item.get('bucket') or ''}: {text}"
        )
    print("\n===== summary.txt 预览 =====")
    print(summary)
    print("===== 预览结束 =====\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="用最近 60 轮原文重建 15 段实时层近期记忆")
    parser.add_argument("--window-id", default=_default_window_id(), help="窗口 id，如 tg_8260066512")
    parser.add_argument("--group-count", type=int, default=15, help="4 轮小段数量，默认 15")
    parser.add_argument("--end-round", type=int, default=0, help="固定结束 round_index；用于重建精确窗口")
    parser.add_argument("--apply", action="store_true", help="写回 global/summary.txt 和 global/summary_chunks.json")
    args = parser.parse_args()

    window_id = str(args.window_id or "").strip()
    if not window_id:
        print("错误：缺少 --window-id，也没有 TELEGRAM_PROACTIVE_TARGET_USER_ID。", file=sys.stderr)
        return 2

    max_chunks = _SUMMARY_OLDER_MAX_CHUNKS + _SUMMARY_SLIGHTLY_MAX_CHUNKS + _SUMMARY_RECENT_MAX_CHUNKS
    group_count = max(1, min(int(args.group_count or max_chunks), max_chunks))
    total_rounds = GROUP_SIZE * group_count
    if args.end_round:
        end_round = int(args.end_round)
        start_round = end_round - total_rounds + 1
        if start_round <= 0:
            print(f"错误：--end-round {end_round} 不足以回溯 {total_rounds} 轮。", file=sys.stderr)
            return 2
        try:
            rounds = _rounds_by_exact_range(window_id, start_round, end_round)
        except Exception as exc:
            print(f"错误：读取固定轮次 {start_round}-{end_round} 失败：{exc}", file=sys.stderr)
            return 2
    else:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=total_rounds) or []
    if len(rounds) < total_rounds:
        print(f"错误：窗口 {window_id} 只有 {len(rounds)} 轮，不足 {total_rounds} 轮。", file=sys.stderr)
        return 2

    groups = _groups_from_rounds(rounds, GROUP_SIZE, group_count)
    if len(groups) != group_count:
        print(f"错误：分组异常 groups={len(groups)} expected={group_count}。", file=sys.stderr)
        return 2

    print(
        f"读取窗口 {window_id} 最近 {total_rounds} 轮："
        f"{_round_index(groups[0][0])}..{_round_index(groups[-1][-1])}",
        flush=True,
    )

    chunks: list[dict] = []
    for idx, group in enumerate(groups, 1):
        meta = _summary_rounds_meta(group)
        t0 = str(group[0].get("timestamp") or "")[:19]
        t1 = str(group[-1].get("timestamp") or "")[:19]
        print(
            f"重算第 {idx}/{group_count} 组 rounds {meta.get('round_start')}-{meta.get('round_end')} "
            f"timestamp {t0} ~ {t1} ...",
            flush=True,
        )
        text = _request_new_chunk(group)
        if not text:
            print("未写回。", file=sys.stderr)
            return 1
        chunks.append(
            {
                **meta,
                "sequence": idx - 1,
                "text": text,
                "source": "recent60_chunks15_rebuild",
            }
        )

    chunks = _assign_levels(chunks)
    chunks_state = {
        "version": 2,
        "update_count": _preserved_update_count(),
        "chunks": chunks,
        "rebuilt_at": now_beijing_iso(),
        "rebuilt_from": {
            "script": "scripts/rebuild_summary_recent60_chunks15.py",
            "window_id": window_id,
            "round_count": total_rounds,
            "group_size": GROUP_SIZE,
        },
    }
    summary = render_summary_from_chunks(chunks_state)
    summary = _trim_summary_to_budget(summary, memory_summary_budget())
    _print_preview(chunks_state, summary)

    if not args.apply:
        print("dry-run：未写回 R2。加 --apply 才会覆盖 global/summary.txt 和 global/summary_chunks.json。")
        return 0

    if not r2_store.save_summary(window_id, summary):
        print("错误：save_summary 写入 R2 失败。", file=sys.stderr)
        return 1
    if not r2_store.save_summary_chunks(window_id, chunks_state):
        print("错误：save_summary_chunks 写入 R2 失败。", file=sys.stderr)
        return 1
    print("已写回 global/summary.txt 和 global/summary_chunks.json。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
