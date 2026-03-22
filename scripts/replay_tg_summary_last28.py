"""
一次性脚本：从 R2 读取指定 Telegram 窗口（tg_*）最近 28 轮原文，
按 4 轮一组共 7 组，链式调用 DeepSeek 实时层总结，最后覆盖写入全局窗口总结（global/summary.txt）。

用法（项目根目录）：
  python -m scripts.replay_tg_summary_last28 --window-id tg_你的数字ID

说明：
- 不修改 conversation.json，只读 R2；
- 第一轮的上文总结为空串，与「首次总结」行为一致；
- 需配置 DEEPSEEK_API_KEY / R2 凭证，与线上一致。
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

from services.deepseek_summary import fetch_new_summary
from storage import r2_store


def main() -> int:
    p = argparse.ArgumentParser(description="用最近 28 轮 TG 原文重算并覆盖全局窗口总结")
    p.add_argument(
        "--window-id",
        required=True,
        help="R2 中的窗口 ID，例如 tg_8260066512",
    )
    args = p.parse_args()
    wid = (args.window_id or "").strip()
    if not wid.startswith("tg_"):
        print("WARN: window-id 通常应以 tg_ 开头", file=sys.stderr)

    rounds = r2_store.get_conversation_rounds(wid, last_n=28)
    n = len(rounds)
    if n < 28:
        print(f"错误：该窗口最近仅有 {n} 轮，需要至少 28 轮才能跑满 7 组。", file=sys.stderr)
        return 1

    groups: list[list] = []
    for i in range(0, 28, 4):
        chunk = rounds[i : i + 4]
        if len(chunk) != 4:
            print(f"错误：分组异常 i={i} len={len(chunk)}", file=sys.stderr)
            return 1
        groups.append(chunk)

    old_summary = (r2_store.get_summary("") or "").strip()
    print(f"当前全局总结长度: {len(old_summary)} 字符（将被覆盖）", flush=True)

    current = ""
    for gi, g in enumerate(groups, 1):
        # 下标为在最近 28 轮切片内的序号（1..28），避免 R2 里 index 字段重复时误导
        start_i = (gi - 1) * 4 + 1
        end_i = gi * 4
        t0 = (g[0].get("timestamp") or "")[:19]
        t1 = (g[-1].get("timestamp") or "")[:19]
        print(
            f"第 {gi}/7 组：本批第 {start_i}-{end_i} 轮  timestamp {t0} ~ {t1}  "
            f"(index 字段 {g[0].get('index')!r}~{g[-1].get('index')!r}，若重复属历史 bug，不影响本脚本正文)",
            flush=True,
        )
        new_summary = fetch_new_summary(current, g)
        if not new_summary:
            print(f"错误：第 {gi} 组 DeepSeek 未返回总结（检查密钥与网络）。", file=sys.stderr)
            return 2
        current = new_summary
        print(f"  → 本组后总结长度: {len(current)} 字符", flush=True)

    ok = r2_store.save_summary("", current)
    if not ok:
        print("错误：save_summary 写入 R2 失败。", file=sys.stderr)
        return 3
    print(f"已写入 global/summary.txt，完成。最终长度 {len(current)} 字符。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
