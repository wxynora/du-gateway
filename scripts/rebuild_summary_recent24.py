"""
用指定窗口最近 24 轮原文重建全局实时层近期记忆。

流程：
- 读取最近 24 轮；
- 按 4 轮一组跑 6 次 fetch_new_summary_update；
- 从空小段队列开始重建；
- 最后覆盖 global/summary.txt 和 global/summary_chunks.json。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from services.deepseek_summary import fetch_new_summary_update
from storage import r2_store


def _default_window_id() -> str:
    uid = str(os.environ.get("TELEGRAM_PROACTIVE_TARGET_USER_ID") or "").strip()
    return f"tg_{uid}" if uid else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="用最近 24 轮重建全局实时层近期记忆")
    parser.add_argument("--window-id", default=_default_window_id(), help="窗口 id，如 tg_8260066512")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写回 R2")
    args = parser.parse_args()

    window_id = str(args.window_id or "").strip()
    if not window_id:
        print("错误：缺少 --window-id，也没有 TELEGRAM_PROACTIVE_TARGET_USER_ID。", file=sys.stderr)
        return 2

    rounds = r2_store.get_conversation_rounds(window_id, last_n=24) or []
    if len(rounds) < 24:
        print(f"错误：窗口 {window_id} 只有 {len(rounds)} 轮，不足 24 轮。", file=sys.stderr)
        return 2

    rounds = rounds[-24:]
    print(
        f"读取窗口 {window_id} 最近 24 轮：{rounds[0].get('index')}..{rounds[-1].get('index')}",
        flush=True,
    )

    current = ""
    chunks_state = {"version": 1, "chunks": []}
    for i in range(0, 24, 4):
        group = rounds[i : i + 4]
        start = group[0].get("index")
        end = group[-1].get("index")
        t0 = str(group[0].get("timestamp") or "")[:19]
        t1 = str(group[-1].get("timestamp") or "")[:19]
        print(f"重算第 {i // 4 + 1}/6 组 rounds {start}-{end} timestamp {t0} ~ {t1} ...", flush=True)
        new_summary = None
        new_chunks = None
        for attempt in range(1, 4):
            new_summary, new_chunks = fetch_new_summary_update(current, group, chunks_state)
            if new_summary and new_chunks:
                break
            if attempt < 3:
                print(f"  第 {attempt} 次失败，5 秒后重试...", flush=True)
                time.sleep(5)
        if not new_summary or not new_chunks:
            print(f"错误：rounds {start}-{end} 总结失败，未写回。", file=sys.stderr)
            return 1
        current = new_summary
        chunks_state = new_chunks
        print(f"  当前总结长度：{len(current)} 字符，chunks={len(chunks_state.get('chunks') or [])}", flush=True)

    print("\n===== 重建后的近期记忆预览 =====")
    print(current)
    print("===== 预览结束 =====\n")

    if args.dry_run:
        print("dry-run：未写回 R2。", flush=True)
        return 0

    if not r2_store.save_summary(window_id, current):
        print("错误：save_summary 写入 R2 失败。", file=sys.stderr)
        return 1
    if not r2_store.save_summary_chunks(window_id, chunks_state):
        print("错误：save_summary_chunks 写入 R2 失败。", file=sys.stderr)
        return 1
    print(
        f"已覆盖写入 global/summary.txt 和 global/summary_chunks.json，最终长度 {len(current)} 字符。",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
