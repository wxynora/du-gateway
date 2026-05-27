#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gateway_tools import (
    _build_mijia_lamp_get_command,
    _build_mijia_lamp_set_command,
    _build_mijia_run_command,
    execute_xiaoai_tool,
)

_LAMP_KEYWORDS = ("台灯", "桌灯", "书桌灯")


def _is_lamp_command(command: str) -> bool:
    return any(k in command for k in _LAMP_KEYWORDS)


def main() -> int:
    parser = argparse.ArgumentParser(description="实测 xiaoai_run_command：默认只允许台灯相关命令。")
    parser.add_argument("command", nargs="?", default="", help="例如：打开台灯 / 关闭台灯")
    parser.add_argument("--speaker-name", default="", help="可选：覆盖 MIJIA_WIFISPEAKER_NAME")
    parser.add_argument("--reason", default="manual_mijia_test", help="写入工具结果的测试原因")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的 mijiaAPI 命令，不真实控制设备")
    parser.add_argument("--allow-non-lamp", action="store_true", help="允许非台灯命令，默认关闭")
    parser.add_argument("--lamp-get", choices=["on", "brightness", "color-temperature"], help="读取台灯结构化属性，不走自然语言")
    parser.add_argument("--lamp-brightness", type=int, help="设置台灯亮度 1-100，不走自然语言")
    parser.add_argument("--lamp-color-temperature", type=int, help="设置台灯色温 2700-5100，不走自然语言")
    args = parser.parse_args()

    command = str(args.command or "").strip()
    if args.lamp_get:
        if args.dry_run:
            print(json.dumps({"ok": True, "dry_run": True, "cmd": _build_mijia_lamp_get_command(args.lamp_get)}, ensure_ascii=False, indent=2))
            return 0
        result = execute_xiaoai_tool("mijia_lamp_get", {"property": args.lamp_get})
        print(result)
        return 0 if (json.loads(result).get("ok")) else 1

    if args.lamp_brightness is not None or args.lamp_color_temperature is not None:
        payload = {
            "brightness": args.lamp_brightness,
            "color_temperature": args.lamp_color_temperature,
            "reason": args.reason,
        }
        if args.dry_run:
            cmds = []
            if args.lamp_brightness is not None:
                cmds.append(_build_mijia_lamp_set_command("brightness", args.lamp_brightness))
            if args.lamp_color_temperature is not None:
                cmds.append(_build_mijia_lamp_set_command("color-temperature", args.lamp_color_temperature))
            print(json.dumps({"ok": True, "dry_run": True, "cmds": cmds}, ensure_ascii=False, indent=2))
            return 0
        result = execute_xiaoai_tool("mijia_lamp_set", payload)
        print(result)
        return 0 if (json.loads(result).get("ok")) else 1

    if not command:
        print("command 不能为空", file=sys.stderr)
        return 2
    if not args.allow_non_lamp and not _is_lamp_command(command):
        print("测试脚本默认只允许台灯相关命令；如确认要测其它设备，加 --allow-non-lamp。", file=sys.stderr)
        return 2

    if args.dry_run:
        payload = {
            "ok": True,
            "dry_run": True,
            "cmd": _build_mijia_run_command(command, speaker_name=args.speaker_name),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    result = execute_xiaoai_tool(
        "xiaoai_run_command",
        {
            "command": command,
            "speaker_name": args.speaker_name,
            "reason": args.reason,
        },
    )
    print(result)
    try:
        data = json.loads(result)
    except Exception:
        return 1
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
