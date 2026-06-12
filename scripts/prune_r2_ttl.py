#!/usr/bin/env python3
"""Prune R2 objects that should not grow forever.

Dry-run by default. Pass --apply to delete/rewrite R2 objects.

Defaults:
- conversation originals / archived thinking: current Beijing month minus 3 months
- sense history events: older than 24 hours by event upload time (`at`)
- summary backups: older than 24 hours by `summary_YYYYMMDD_HHMMSS.txt`
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import prune_r2_conversation_originals as conversation_pruner  # noqa: E402
from config import R2_BUCKET_NAME  # noqa: E402
from storage import r2_store  # noqa: E402
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing  # noqa: E402

SUMMARY_BACKUP_PREFIX = "global/summary_backups/"
SENSE_HISTORY_PREFIX = "sense/history/"
SUMMARY_BACKUP_RE = re.compile(r"^global/summary_backups/summary_(\d{8}_\d{6})\.txt$")


def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except Exception as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if n <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return n


def _new_client():
    client = r2_store._s3_client()
    if not client:
        raise RuntimeError("R2 is not configured")
    return client


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=BEIJING_TZ)
        return dt.astimezone(BEIJING_TZ).isoformat()
    return value


def _iter_objects(client, prefix: str):
    token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if not key:
                continue
            yield {
                "key": key,
                "size": int(obj.get("Size") or 0),
                "last_modified": _json_safe(obj.get("LastModified")),
            }
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break


def _read_json_key(client, key: str) -> tuple[Any | None, str]:
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8")), ""
    except Exception as exc:
        return None, str(exc)


def _write_json_key(client, key: str, payload: Any) -> None:
    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def _delete_keys(client, keys: list[str]) -> int:
    deleted = 0
    for i in range(0, len(keys), 1000):
        chunk = [key for key in keys[i : i + 1000] if key]
        if not chunk:
            continue
        client.delete_objects(
            Bucket=R2_BUCKET_NAME,
            Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
        )
        deleted += len(chunk)
    return deleted


def _parse_summary_backup_time(key: str) -> datetime | None:
    match = SUMMARY_BACKUP_RE.match(str(key or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=BEIJING_TZ)
    except ValueError:
        return None


def _age_cutoff(hours: int) -> datetime:
    return datetime.now(BEIJING_TZ) - timedelta(hours=int(hours))


def _build_summary_backup_manifest(client, ttl_hours: int) -> dict[str, Any]:
    cutoff = _age_cutoff(ttl_hours)
    delete_keys: list[dict[str, Any]] = []
    skipped = 0
    for obj in _iter_objects(client, SUMMARY_BACKUP_PREFIX):
        key = str(obj.get("key") or "")
        backup_time = _parse_summary_backup_time(key)
        if not backup_time:
            skipped += 1
            continue
        if backup_time < cutoff:
            delete_keys.append(
                {
                    **obj,
                    "source": "summary_backup_ttl",
                    "backup_time": backup_time.isoformat(),
                    "ttl_hours": int(ttl_hours),
                }
            )
    total_bytes = sum(int(item.get("size") or 0) for item in delete_keys)
    return {
        "prefix": SUMMARY_BACKUP_PREFIX,
        "ttl_hours": int(ttl_hours),
        "cutoff": cutoff.isoformat(),
        "delete_keys": sorted(delete_keys, key=lambda item: str(item.get("key") or "")),
        "errors": [],
        "stats": {
            "delete_key_count": len(delete_keys),
            "delete_key_bytes": total_bytes,
            "delete_key_mib": round(total_bytes / 1024 / 1024, 2),
            "skipped_unrecognized_keys": skipped,
        },
    }


def _sense_event_time(row: Any) -> datetime | None:
    if not isinstance(row, dict):
        return None
    return parse_iso_to_beijing(str(row.get("at") or "").strip())


def _filter_sense_history_rows(rows: list[Any], cutoff: datetime) -> tuple[list[Any], int, int]:
    keep: list[Any] = []
    removed = 0
    unknown_time = 0
    for row in rows:
        event_time = _sense_event_time(row)
        if not event_time:
            keep.append(row)
            unknown_time += 1
            continue
        if event_time < cutoff:
            removed += 1
            continue
        keep.append(row)
    return keep, removed, unknown_time


def _build_sense_history_manifest(client, ttl_hours: int) -> dict[str, Any]:
    cutoff = _age_cutoff(ttl_hours)
    delete_keys: list[dict[str, Any]] = []
    rewrites: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    scanned_keys = 0
    removed_events = 0
    kept_unknown_time_events = 0

    for obj in _iter_objects(client, SENSE_HISTORY_PREFIX):
        key = str(obj.get("key") or "")
        if not key.endswith(".json"):
            continue
        scanned_keys += 1
        data, err = _read_json_key(client, key)
        if err:
            errors.append({"kind": "sense_history_read_error", "key": key, "error": err})
            continue
        if not isinstance(data, list):
            errors.append({"kind": "sense_history_skip", "key": key, "reason": "not_json_list"})
            continue

        keep, removed, unknown_time = _filter_sense_history_rows(data, cutoff)
        removed_events += removed
        kept_unknown_time_events += unknown_time
        if removed <= 0:
            continue
        if keep:
            rewrites.append(
                {
                    **obj,
                    "source": "sense_history_ttl",
                    "ttl_hours": int(ttl_hours),
                    "removed_events": removed,
                    "keep_events": len(keep),
                    "payload_after": keep,
                }
            )
        else:
            delete_keys.append(
                {
                    **obj,
                    "source": "sense_history_ttl",
                    "ttl_hours": int(ttl_hours),
                    "removed_events": removed,
                }
            )

    total_delete_bytes = sum(int(item.get("size") or 0) for item in delete_keys)
    return {
        "prefix": SENSE_HISTORY_PREFIX,
        "ttl_hours": int(ttl_hours),
        "cutoff": cutoff.isoformat(),
        "delete_keys": sorted(delete_keys, key=lambda item: str(item.get("key") or "")),
        "rewrites": sorted(rewrites, key=lambda item: str(item.get("key") or "")),
        "errors": errors,
        "stats": {
            "scanned_key_count": scanned_keys,
            "delete_key_count": len(delete_keys),
            "rewrite_key_count": len(rewrites),
            "removed_events": removed_events,
            "kept_unknown_time_events": kept_unknown_time_events,
            "delete_key_bytes": total_delete_bytes,
            "delete_key_mib": round(total_delete_bytes / 1024 / 1024, 2),
        },
    }


def _build_conversation_manifest(args: argparse.Namespace) -> dict[str, Any]:
    conv_args = SimpleNamespace(
        month=args.conversation_month,
        retention_months=args.conversation_retention_months,
        apply=False,
        manifest=None,
        workers=args.workers,
        progress_every=args.progress_every,
        skip_date_backups=args.skip_conversation_date_backups,
        skip_round_files=args.skip_conversation_round_files,
        skip_legacy=args.skip_conversation_legacy,
        max_round_objects=args.max_round_objects,
    )
    return conversation_pruner.build_manifest(conv_args)


def _slim_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    out = dict(manifest)
    if "legacy_rewrites" in out:
        out = conversation_pruner._manifest_for_output(out)
    if "rewrites" in out:
        rewrites = []
        for item in out.get("rewrites", []):
            slim = dict(item)
            slim.pop("payload_after", None)
            rewrites.append(slim)
        out["rewrites"] = rewrites
    return out


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    client = _new_client()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now_beijing_iso(),
        "apply": bool(args.apply),
        "conversations": None,
        "sense_history": None,
        "summary_backups": None,
        "errors": [],
    }

    if not args.skip_conversations:
        manifest["conversations"] = _build_conversation_manifest(args)
    if not args.skip_sense_history:
        manifest["sense_history"] = _build_sense_history_manifest(client, args.sense_history_ttl_hours)
    if not args.skip_summary_backups:
        manifest["summary_backups"] = _build_summary_backup_manifest(client, args.summary_backup_ttl_hours)

    errors: list[dict[str, Any]] = []
    for section in ("conversations", "sense_history", "summary_backups"):
        part = manifest.get(section)
        if isinstance(part, dict):
            for item in part.get("errors") or []:
                errors.append({"section": section, **item})
    manifest["errors"] = errors
    manifest["stats"] = _combined_stats(manifest)
    return manifest


def _combined_stats(manifest: dict[str, Any]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    conv = manifest.get("conversations") if isinstance(manifest.get("conversations"), dict) else {}
    sense = manifest.get("sense_history") if isinstance(manifest.get("sense_history"), dict) else {}
    summary = manifest.get("summary_backups") if isinstance(manifest.get("summary_backups"), dict) else {}
    conv_stats = conv.get("stats") if isinstance(conv.get("stats"), dict) else {}
    sense_stats = sense.get("stats") if isinstance(sense.get("stats"), dict) else {}
    summary_stats = summary.get("stats") if isinstance(summary.get("stats"), dict) else {}
    stats["conversation_delete_keys"] = int(conv_stats.get("delete_key_count") or 0)
    stats["conversation_legacy_rewrites"] = int(conv_stats.get("legacy_rewrite_key_count") or 0)
    stats["conversation_legacy_removed_rounds"] = int(conv_stats.get("legacy_removed_rounds") or 0)
    stats["sense_delete_keys"] = int(sense_stats.get("delete_key_count") or 0)
    stats["sense_rewrite_keys"] = int(sense_stats.get("rewrite_key_count") or 0)
    stats["sense_removed_events"] = int(sense_stats.get("removed_events") or 0)
    stats["summary_backup_delete_keys"] = int(summary_stats.get("delete_key_count") or 0)
    stats["total_delete_keys"] = (
        stats["conversation_delete_keys"]
        + stats["sense_delete_keys"]
        + stats["summary_backup_delete_keys"]
    )
    return stats


def apply_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    client = _new_client()
    result: dict[str, Any] = {}

    conv = manifest.get("conversations")
    if isinstance(conv, dict):
        result["conversations"] = conversation_pruner.apply_manifest(conv)

    for section in ("sense_history", "summary_backups"):
        part = manifest.get(section)
        if not isinstance(part, dict):
            continue
        keys = [str(item.get("key") or "") for item in part.get("delete_keys", []) if str(item.get("key") or "")]
        deleted = _delete_keys(client, keys)
        rewritten = 0
        if section == "sense_history":
            for item in part.get("rewrites", []):
                key = str(item.get("key") or "")
                payload = item.get("payload_after")
                if key and isinstance(payload, list):
                    _write_json_key(client, key, payload)
                    rewritten += 1
        result[section] = {"deleted_keys": deleted, "rewritten_keys": rewritten}

    return result


def output_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    out = dict(manifest)
    for section in ("conversations", "sense_history", "summary_backups"):
        part = out.get(section)
        if isinstance(part, dict):
            out[section] = _slim_manifest(part)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune R2 TTL data without touching hot chat paths.")
    parser.add_argument("--apply", action="store_true", help="Actually delete/rewrite R2 data. Default is dry-run.")
    parser.add_argument("--manifest", help="Write manifest JSON to this path.")
    parser.add_argument("--skip-conversations", action="store_true", help="Skip monthly conversation/thinking cleanup.")
    parser.add_argument("--skip-sense-history", action="store_true", help="Skip sense/history 24h cleanup.")
    parser.add_argument("--skip-summary-backups", action="store_true", help="Skip global/summary_backups 24h cleanup.")
    parser.add_argument("--conversation-month", type=conversation_pruner._validate_month, help="Target month YYYY-MM for conversation originals.")
    parser.add_argument("--conversation-retention-months", type=int, default=3, help="Default conversation target offset in months. Default: 3.")
    parser.add_argument("--summary-backup-ttl-hours", type=_positive_int, default=24, help="TTL for global/summary_backups. Default: 24.")
    parser.add_argument("--sense-history-ttl-hours", type=_positive_int, default=24, help="TTL for sense/history events by upload time. Default: 24.")
    parser.add_argument("--workers", type=int, default=12, help="Concurrent R2 readers for conversation round files. Default: 12.")
    parser.add_argument("--progress-every", type=int, default=500, help="Print conversation scan progress every N round files. 0 disables.")
    parser.add_argument("--skip-conversation-date-backups", action="store_true", help="Skip conversations/YYYY-MM* date backup keys.")
    parser.add_argument("--skip-conversation-round-files", action="store_true", help="Skip windows/*/rounds/*.json files.")
    parser.add_argument("--skip-conversation-legacy", action="store_true", help="Skip rewriting windows/*/conversation.json legacy packs.")
    parser.add_argument("--max-round-objects", type=int, help="Dry-run smoke limit for windows/*/rounds scans.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_round_objects is not None and args.apply:
        raise SystemExit("--max-round-objects is for dry-run/smoke only; do not combine it with --apply")

    manifest = build_manifest(args)
    apply_result = None
    if args.apply:
        apply_result = apply_manifest(manifest)
        manifest["apply_result"] = apply_result

    out = output_manifest(manifest)
    if args.manifest:
        path = Path(args.manifest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "stats": out["stats"],
                "errors": out["errors"],
                "apply_result": apply_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if out["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
