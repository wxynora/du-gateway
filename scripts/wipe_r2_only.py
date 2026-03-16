#!/usr/bin/env python3
"""仅清空 R2 中网关使用的所有 key（归档前用）。不删本地数据。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import r2_store

if __name__ == "__main__":
    ok, deleted, err = r2_store.delete_all_gateway_data()
    if not ok:
        print(f"清空失败: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"R2 已清空，删除 key 数: {deleted}")
