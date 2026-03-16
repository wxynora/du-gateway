#!/usr/bin/env python3
"""
把 RikkaHub 导出的 md/文本 转成 feed_conversation_for_memory.py 需要的 JSON。
用法：python scripts/md_to_feed_json.py input.md [--out feed_input.json]
支持格式（按行或块）：识别 User/用户 和 Assistant/助手/渡 的交替出现，每对为一轮。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def parse_md_to_rounds(text: str) -> list[dict]:
    """
    从 md 或纯文本中解析出 rounds。
    尝试多种常见格式：User:/Assistant:、### User、[USER]、**User** 等。
    """
    text = text.strip()
    if not text:
        return []

    rounds = []
    # 按可能的分隔拆成块（--- 或 多个换行）
    blocks = re.split(r"\n---+\n|\n\n\n+", text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 尝试匹配 "User: 内容" 或 "**User**: 内容" 或 "### User\n内容"
        user_content = None
        assistant_content = None

        # 格式1: User: xxx \n Assistant: xxx 或 用户: / 助手:
        m = re.search(
            r"(?:User|用户|human)\s*[：:]\s*(.*?)(?=Assistant|助手|渡|assistant|AI\s*[：:]|\Z)",
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            user_content = m.group(1).strip()
        m2 = re.search(
            r"(?:Assistant|助手|渡|assistant|AI)\s*[：:]\s*(.*)",
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if m2:
            assistant_content = m2.group(1).strip()

        # 格式2: ### User \n 内容 \n ### Assistant \n 内容
        if user_content is None or assistant_content is None:
            parts = re.split(r"\n###\s*(?:User|用户|Assistant|助手|渡)\s*\n", block, flags=re.IGNORECASE)
            if len(parts) >= 3:
                user_content = (user_content or parts[1]).strip()
                assistant_content = (assistant_content or parts[2]).strip()

        # 格式3: [USER] 或 **User** 下一行开始是内容，直到 [ASSISTANT] 或 **Assistant**
        if user_content is None or assistant_content is None:
            user_m = re.search(r"(\[USER\]|\*\*User\*\*|用户)\s*\n(.*?)(?=\[ASSISTANT\]|\*\*Assistant\*\*|助手|渡|\Z)", block, re.DOTALL | re.IGNORECASE)
            ast_m = re.search(r"(\[ASSISTANT\]|\*\*Assistant\*\*|助手|渡)\s*\n(.*)", block, re.DOTALL | re.IGNORECASE)
            if user_m:
                user_content = (user_content or user_m.group(2)).strip()
            if ast_m:
                assistant_content = (assistant_content or ast_m.group(2)).strip()

        if user_content or assistant_content:
            rounds.append({"user": user_content or "", "assistant": assistant_content or ""})

    return rounds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="导出的 .md 或 .txt")
    parser.add_argument("--out", type=Path, default=Path("scripts/feed_input.json"), help="输出 JSON 路径")
    parser.add_argument("--window-id", default="", help="window_id")
    args = parser.parse_args()

    path = args.input
    if not path.exists():
        path = ROOT / path
    if not path.exists():
        print(f"文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    rounds = parse_md_to_rounds(text)
    if not rounds:
        print("未解析出任何一轮，请检查格式。可发一段示例让我适配。", file=sys.stderr)
        sys.exit(1)

    data = {"window_id": args.window_id, "rounds": rounds}
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已解析 {len(rounds)} 轮 -> {out_path}")


if __name__ == "__main__":
    main()
