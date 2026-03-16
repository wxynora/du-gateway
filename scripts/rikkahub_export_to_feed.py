#!/usr/bin/env python3
"""
把 RikkaHub 数据库导出的 JSON 转成 feed_conversation_for_memory 用的 feed_input.json。
导出格式：顶层数组，每项 { conversation_id, id, messages, node_index }，messages 为字符串化的 JSON 数组（单条消息）。
每条约 message 含 role、parts：[{ type: "text"|"reasoning", text: "..." }]，只取 type=text 的 content。
按 node_index 顺序，相邻的 user+assistant 配成一轮。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _extract_text_from_parts(parts: list) -> str:
    if not parts:
        return ""
    texts = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text" and "text" in p:
            texts.append(p.get("text", ""))
        if p.get("type") == "reasoning":
            continue  # 不把 reasoning 当对话正文
    return "\n".join(texts).strip()


def parse_rikkahub_export(data: list, allowed_model_ids: list | None = None) -> list[dict]:
    """
    从 RikkaHub 导出数组解析出 rounds: [ {user, assistant, timestamp?}, ... ]。
    allowed_model_ids：若非空，只保留 assistant 的 modelId 在此列表中的轮次（初筛，避免混入别的助手）。
    """
    rounds = []
    allowed = set(allowed_model_ids or [])
    # 按 node_index 排序，然后两两配对 user -> assistant
    items = sorted(data, key=lambda x: x.get("node_index", 0))
    i = 0
    while i < len(items):
        raw = items[i]
        try:
            msgs = json.loads(raw.get("messages") or "[]")
        except (json.JSONDecodeError, TypeError):
            i += 1
            continue
        if not msgs or not isinstance(msgs, list):
            i += 1
            continue
        first = msgs[0]
        role = (first.get("role") or "").lower()
        parts = first.get("parts") or []
        text = _extract_text_from_parts(parts)

        if role == "user":
            user_text = text
            # 下一项应为 assistant
            if i + 1 < len(items):
                raw2 = items[i + 1]
                try:
                    msgs2 = json.loads(raw2.get("messages") or "[]")
                except (json.JSONDecodeError, TypeError):
                    i += 1
                    continue
                ast = (msgs2 or [{}])[0] if msgs2 else {}
                if (ast.get("role") or "").lower() == "assistant":
                    # 初筛：若配置了 allowed_model_ids，只保留该助手
                    if allowed:
                        mid = (ast.get("modelId") or "").strip()
                        if mid and mid not in allowed:
                            i += 2
                            continue
                    ast_parts = ast.get("parts") or []
                    assistant_text = _extract_text_from_parts(ast_parts)
                    round_obj = {"user": user_text, "assistant": assistant_text}
                    if ast.get("createdAt"):
                        round_obj["timestamp"] = ast["createdAt"]
                    rounds.append(round_obj)
                    i += 2
                    continue
            rounds.append({"user": user_text, "assistant": ""})
            i += 1
        else:
            i += 1
    return rounds


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="RikkaHub 导出的 JSON 文件路径")
    parser.add_argument("--out", type=Path, default=ROOT / "scripts" / "feed_input.json")
    parser.add_argument("--window-id", default="")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        # 常见桌面路径
        for desktop in [
            Path.home() / "Desktop" / path.name,
            Path("C:/Users/doraemon/Desktop") / path.name,
        ]:
            if desktop.exists():
                path = desktop
                break
    if not path.exists():
        print(f"找不到文件: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]

    rounds = parse_rikkahub_export(data)
    if not rounds:
        print("未解析出任何一轮", file=sys.stderr)
        sys.exit(1)

    out = {"window_id": args.window_id, "rounds": rounds}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已解析 {len(rounds)} 轮 -> {args.out}")
    return args.out


if __name__ == "__main__":
    main()
