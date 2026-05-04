"""
从 R2 读取指定窗口最近 12 轮原文，按 4 轮一组共 3 组，链式调用 DeepSeek 实时层小段总结，
把「漏跑的三组」补进窗口总结，与线上每满 4 轮触发一次的行为一致。

存储说明：全局总结展示文本写入 global/summary.txt；结构化小段队列写入 global/summary_chunks.json。

适用于 RikkaHub 默认窗口（__default__）或任意 window_id。

用法（项目根目录）：
  python -m scripts.replay_rikkahub_summary_last12
  python -m scripts.replay_rikkahub_summary_last12 --from-empty   # 仅调试：忽略已有总结

说明：
- 不修改 conversation.json，只读 R2（读取时会自动迁移 legacy windows// 主存）；
- 默认以当前全局总结为起点；需配置 DEEPSEEK_API_KEY、R2 凭证，与线上一致。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from services.deepseek_summary import fetch_new_summary_update
from storage import r2_store


def main() -> int:
    p = argparse.ArgumentParser(
        description="在最近 12 轮上补跑 3 次窗口小段总结"
    )
    p.add_argument(
        "--window-id",
        default=r2_store.WINDOW_ID_DEFAULT,
        help=f"R2 窗口 ID，默认 {r2_store.WINDOW_ID_DEFAULT}（RikkaHub 未传 id 时网关使用的 id）",
    )
    p.add_argument(
        "--from-empty",
        action="store_true",
        help="调试：小段队列从空开始（会丢掉当前 global/summary 已有内容，一般不用于补跑）",
    )
    args = p.parse_args()
    wid = r2_store.normalize_window_id((args.window_id or "").strip())

    rounds = r2_store.get_conversation_rounds(wid, last_n=12)
    n = len(rounds)
    if n < 12:
        print(
            f"错误：该窗口最近仅有 {n} 轮，需要至少 12 轮才能跑满 3 组总结。"
            f"（window_id={wid!r}，若数据在旧路径 windows//，读取时会自动迁移到 windows/{wid}/）",
            file=sys.stderr,
        )
        return 1

    groups: list[list] = []
    for i in range(0, 12, 4):
        chunk = rounds[i : i + 4]
        if len(chunk) != 4:
            print(f"错误：分组异常 i={i} len={len(chunk)}", file=sys.stderr)
            return 1
        groups.append(chunk)

    old_summary = (r2_store.get_summary("") or "").strip()
    if args.from_empty:
        current = ""
        chunks_state = {"version": 1, "chunks": []}
        print(
            f"已指定 --from-empty：上文总结从空开始（当前磁盘上的总结长 {len(old_summary)} 字符，本流程不使用）",
            flush=True,
        )
    else:
        current = old_summary
        chunks_state = r2_store.get_summary_chunks("") or {}
        print(
            f"起点：当前全局总结 {len(current)} 字符；将在当前小段队列上分 3 组融入最近 12 轮",
            flush=True,
        )
    for gi, g in enumerate(groups, 1):
        start_i = (gi - 1) * 4 + 1
        end_i = gi * 4
        t0 = (g[0].get("timestamp") or "")[:19]
        t1 = (g[-1].get("timestamp") or "")[:19]
        print(
            f"第 {gi}/3 组：本批第 {start_i}-{end_i} 轮  timestamp {t0} ~ {t1}  "
            f"(index 字段 {g[0].get('index')!r}~{g[-1].get('index')!r})",
            flush=True,
        )
        new_summary, new_chunks = fetch_new_summary_update(current, g, chunks_state)
        if not new_summary or not new_chunks:
            print(f"错误：第 {gi} 组 DeepSeek 未返回总结（检查 DEEPSEEK_API_KEY 与网络）。", file=sys.stderr)
            return 2
        current = new_summary
        chunks_state = new_chunks
        print(f"  → 本组后总结长度: {len(current)} 字符", flush=True)

    ok = r2_store.save_summary("", current)
    if not ok:
        print("错误：save_summary 写入 R2 失败。", file=sys.stderr)
        return 3
    if not r2_store.save_summary_chunks("", chunks_state):
        print("错误：save_summary_chunks 写入 R2 失败。", file=sys.stderr)
        return 3
    print(
        f"已更新 global/summary.txt 和 global/summary_chunks.json。最终长度 {len(current)} 字符。",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
