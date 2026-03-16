#!/usr/bin/env python3
"""一键停止归档脚本：写入停止信号，feed_conversation_for_memory.py 会在下一批/下一轮后退出，不再调 DS。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP_FILE = Path(__file__).resolve().parent / "feed_archive.stop"

STOP_FILE.touch()
print("已写入停止信号：", STOP_FILE)
print("若归档脚本正在运行，将在下一批或下一轮后自动退出，不再调用 DS。")
print("（若脚本未在跑，无影响；下次运行前会自动清除该文件。）")
