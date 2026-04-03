"""
手动/定时触发动态记忆离线慢整理。

用法：
python3 scripts/run_memory_maintenance.py
python3 scripts/run_memory_maintenance.py --dry-run
python3 scripts/run_memory_maintenance.py --limit-candidates 10
"""

import argparse
import json

from services.memory_maintenance import run_memory_maintenance


def main() -> None:
    parser = argparse.ArgumentParser(description="运行动态记忆离线慢整理")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不落盘")
    parser.add_argument("--limit-candidates", type=int, default=20, help="最多返回多少组疑似平行条候选")
    args = parser.parse_args()

    report = run_memory_maintenance(
        limit_candidates=max(1, int(args.limit_candidates or 20)),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
