"""
一次性脚本：用事先整理好的 rounds JSON，走「清洗 → 窗口总结 → 动态层」，**跳过原文存 R2**。

适用场景：
- 已有 data/rikka_main_rounds.json 这类文件（由 convert_rikka_export_to_json 生成）；
- 想让这段历史进「渡的回忆 + 动态层 / 核心缓存 / 卧室 / 小本本」；
- 但不想在 R2 对话存档里重复追加轮次。

用法示例（在项目根目录）：
  python -m scripts.replay_json_rounds_to_memory ^
    --file "data/rikka_main_rounds.json" ^
    --window-id "rikka_main"

说明：
- JSON 结构需为：
  {
    "conversation_id": "...",
    "rounds": [
      { "index": 1, "messages": [ {user...}, {assistant...} ] },
      ...
    ]
  }
  与 convert_rikka_export_to_json 的输出一致。
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
    p = argparse.ArgumentParser(description="重放 rounds JSON 到窗口总结 + 动态层（不写对话存档）")
    p.add_argument("--file", required=True, help="rounds JSON 文件路径（由 convert_rikka_export_to_json 生成）")
    p.add_argument("--window-id", required=True, help="在网关中使用的 window_id（如 rikka_main）")
    p.add_argument(
        "--max-rounds",
        type=int,
        default=0,
        help="最多重放的轮数（0 表示全部）",
    )
    return p.parse_args()


def _load_rounds(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rounds = data.get("rounds") or []
    if not isinstance(rounds, list) or not rounds:
        raise SystemExit("JSON 中未找到 rounds 列表。")
    # 按 index 升序
    rounds = sorted(
        [r for r in rounds if isinstance(r, dict) and "messages" in r],
        key=lambda r: int(r.get("index") or 0),
    )
    return rounds


def main() -> None:
    args = _parse_args()
    window_id = args.window_id
    rounds = _load_rounds(args.file)
    max_rounds = int(args.max_rounds or 0)
    total = len(rounds) if max_rounds <= 0 else min(len(rounds), max_rounds)
    logger.info("replay_json_rounds_to_memory file=%s window_id=%s total_rounds=%s use=%s", args.file, window_id, len(rounds), total)

    # 为总结构造「最近 N 轮」的 in-memory 列表，结构与 r2_store.get_conversation_rounds 返回值一致：
    # [{ "index": n, "messages": [user, assistant] }, ...]
    all_rounds_for_summary: List[Dict[str, Any]] = []

    from pipeline.cleaner import build_round_cleaned_for_r2

    for i, r in enumerate(rounds[:total], start=1):
        msgs = r.get("messages") or []
        if not (isinstance(msgs, list) and len(msgs) >= 2):
            continue
        user_msg, asst_msg = msgs[0], msgs[1]
        # 用现有清洗逻辑得到 round_messages（与正常存档时一致）
        round_messages = build_round_cleaned_for_r2(user_msg, asst_msg)
        all_rounds_for_summary.append({"index": i, "messages": round_messages})

        # 窗口总结：每 SUMMARY_EVERY_N_ROUNDS 轮，用最近 4 轮 + 当前 summary 调 DeepSeek，总结写回 R2
        if i % SUMMARY_EVERY_N_ROUNDS == 0:
            recent = all_rounds_for_summary[-4:]
            if recent:
                current = r2_store.get_summary(window_id) or ""

                def _summarize(cur: str, rec: List[Dict[str, Any]]) -> None:
                    new_summary = fetch_new_summary(cur, rec)
                    if new_summary:
                        r2_store.save_summary(window_id, new_summary)
                    else:
                        logger.warning("replay_json_rounds_to_memory 触发总结但 DeepSeek 未返回新总结 window_id=%s", window_id)

                _summarize(current, recent)

        # 动态层演化：直接调用 _step_dynamic_layer_evolve（不写对话存档）
        try:
            _step_dynamic_layer_evolve(window_id, i, round_messages)
        except Exception as e:
            logger.error("replay_json_rounds_to_memory 动态层第 %s 轮失败 error=%s", i, e, exc_info=True)

        if i % 50 == 0 or i == total:
            logger.info("已重放轮次 %s/%s（summary+dynamic）", i, total)


if __name__ == "__main__":
    main()

