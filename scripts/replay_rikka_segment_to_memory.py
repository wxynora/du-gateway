"""
从 RikkaHub 导出的 JSON（数组，每行含 node_index/messages）里，
只取 node_index 在 [start, end] 区间内的消息，按轮走：
- 清洗成 round_messages
- 窗口总结（写 global/summary.txt）
- 动态层演化

不写对话存档（conversation.json / conversations/），避免 R2 中轮次重复。

用法示例（在项目根目录）：

  python -m scripts.replay_rikka_segment_to_memory ^
    --file "C:\\Users\\doraemon\\Desktop\\渡实时.json" ^
    --window-id "rikka_main" ^
    --conversation-id "4380ebe1-d47e-471d-aa4f-53066e6dd1da" ^
    --start 3237 --end 3404
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from pipeline.pipeline import SUMMARY_EVERY_N_ROUNDS, _step_dynamic_layer_evolve
from services.deepseek_summary import fetch_new_summary
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="只重放指定 node_index 区间到总结+动态层（不写原文存档）")
    p.add_argument("--file", required=True, help="RikkaHub 导出的 JSON 文件（数组，每行含 node_index/messages）")
    p.add_argument("--window-id", required=True, help="在网关中使用的 window_id（如 rikka_main）")
    p.add_argument("--conversation-id", required=True, help="只处理该 conversation_id 的记录")
    p.add_argument("--start", type=int, required=True, help="起始 node_index（含）")
    p.add_argument("--end", type=int, required=True, help="结束 node_index（含）")
    return p.parse_args()


def _load_segment(
    path: str, conv_id: str, start_idx: int, end_idx: int
) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        arr = json.load(f)
    if not isinstance(arr, list):
        raise SystemExit("JSON 顶层不是数组。")
    rows: List[Dict[str, Any]] = []
    for row in arr:
        if not isinstance(row, dict):
            continue
        if (row.get("conversation_id") or "").strip() != conv_id:
            continue
        try:
            ni = int(row.get("node_index"))
        except Exception:
            continue
        if ni < start_idx or ni > end_idx:
            continue
        rows.append(row)
    if not rows:
        raise SystemExit("在给定 conversation_id 和 node_index 区间内未找到任何记录。")
    # 按 node_index 升序
    rows.sort(key=lambda r: int(r.get("node_index") or 0))
    return rows


def _build_rounds(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据导出的单条消息列表，组装成轮次：
    [{"index": n, "messages": [user_msg, assistant_msg]}...]
    """
    out: List[Dict[str, Any]] = []
    pending_user: Dict[str, Any] | None = None
    round_idx = 0
    for row in rows:
        raw = row.get("messages") or ""
        try:
            msgs = json.loads(raw)
        except Exception:
            continue
        if not isinstance(msgs, list) or not msgs:
            continue
        msg = msgs[0]
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").lower()
        if role == "user":
            pending_user = msg
        elif role == "assistant":
            if pending_user:
                round_idx += 1
                out.append({"index": round_idx, "messages": [pending_user, msg]})
                pending_user = None
    return out


def main() -> None:
    args = _parse_args()
    window_id = args.window_id
    start_idx, end_idx = int(args.start), int(args.end)
    rows = _load_segment(args.file, args.conversation_id, start_idx, end_idx)
    rounds = _build_rounds(rows)
    if not rounds:
        raise SystemExit("指定区间内未能组装出任何 user+assistant 轮次。")
    logger.info(
        "replay_rikka_segment_to_memory file=%s conv_id=%s window_id=%s node_index=[%s,%s] rounds=%s",
        args.file,
        args.conversation_id,
        window_id,
        start_idx,
        end_idx,
        len(rounds),
    )

    from pipeline.cleaner import build_round_cleaned_for_r2

    all_rounds_for_summary: List[Dict[str, Any]] = []

    total = len(rounds)
    for i, r in enumerate(rounds, start=1):
        msgs = r.get("messages") or []
        if not (isinstance(msgs, list) and len(msgs) >= 2):
            continue
        user_msg, asst_msg = msgs[0], msgs[1]
        round_messages = build_round_cleaned_for_r2(user_msg, asst_msg)
        all_rounds_for_summary.append({"index": i, "messages": round_messages})

        # 窗口总结
        if i % SUMMARY_EVERY_N_ROUNDS == 0:
            recent = all_rounds_for_summary[-4:]
            if recent:
                current = r2_store.get_summary(window_id) or ""
                new_summary = fetch_new_summary(current, recent)
                if new_summary:
                    r2_store.save_summary(window_id, new_summary)
                else:
                    logger.warning(
                        "replay_rikka_segment_to_memory 触发总结但 DeepSeek 未返回新总结 window_id=%s", window_id
                    )

        # 动态层
        try:
            _step_dynamic_layer_evolve(window_id, i, round_messages)
        except Exception as e:
            logger.error(
                "replay_rikka_segment_to_memory 动态层第 %s 轮失败 error=%s", i, e, exc_info=True
            )

        if i % 20 == 0 or i == total:
            logger.info("已重放轮次 %s/%s（summary+dynamic，仅 node_index 区间）", i, total)


if __name__ == "__main__":
    main()

