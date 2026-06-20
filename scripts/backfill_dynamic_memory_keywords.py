"""
Backfill the dynamic memory SQLite mirror and keyword index from R2 current.json.

Default is dry-run. Use --write to update the local SQLite mirror.
This script never writes dynamic_memory/current.json.

Usage:
  .venv/bin/python scripts/backfill_dynamic_memory_keywords.py
  .venv/bin/python scripts/backfill_dynamic_memory_keywords.py --write
  .venv/bin/python scripts/backfill_dynamic_memory_keywords.py --status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DYNAMIC_MEMORY_KEYWORD_BACKFILL_DRY_RUN, DYNAMIC_MEMORY_KEYWORD_MAX_TERMS
from services.dynamic_memory_keywords import extract_keywords_for_memories
from storage import dynamic_memory_mirror_store, r2_store


def _json_print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill dynamic memory keyword mirror.")
    parser.add_argument("--write", action="store_true", help="Write SQLite mirror instead of dry-run.")
    parser.add_argument("--status", action="store_true", help="Show mirror status and exit.")
    parser.add_argument("--list", action="store_true", help="List recent mirrored items and exit.")
    parser.add_argument("--limit", type=int, default=20, help="List limit for --list.")
    parser.add_argument("--max-terms", type=int, default=DYNAMIC_MEMORY_KEYWORD_MAX_TERMS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.status:
        _json_print(dynamic_memory_mirror_store.get_status())
        return 0
    if args.list:
        _json_print({"items": dynamic_memory_mirror_store.list_items(limit=args.limit)})
        return 0

    memories = r2_store.get_dynamic_memory_list() or []
    terms_by_id = extract_keywords_for_memories(memories, max_terms=args.max_terms)
    dry_run = DYNAMIC_MEMORY_KEYWORD_BACKFILL_DRY_RUN and not args.write
    result = dynamic_memory_mirror_store.sync_memories(
        memories,
        terms_by_id=terms_by_id,
        source="dynamic_memory_keyword_backfill",
        dry_run=dry_run,
    )
    result["r2_write"] = False
    result["sqlite_write"] = not dry_run
    result["note"] = "R2 current.json is read only; SQLite mirror is rebuildable."
    _json_print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
