#!/usr/bin/env python3
"""只清空动态层 + 核心缓存（供归档重跑前用）。不动对话、总结、小本本等其它 R2 数据。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import r2_store

if __name__ == "__main__":
    r2_store.save_dynamic_memory_list([])
    r2_store.save_core_cache_pending([])
    print("已清空：dynamic_memory/current.json、core_cache/pending.json")
    print("其它 R2 数据（对话、总结、小本本等）未动。")
