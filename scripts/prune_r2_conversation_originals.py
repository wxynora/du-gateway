#!/usr/bin/env python3
"""Prune old R2 conversation originals by month.

Default target month is three months before the current Beijing month:
running in 2026-06 targets 2026-03, running in 2026-07 targets 2026-04.

Dry-run by default. Pass --apply to delete/rewrite R2 objects.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import R2_BUCKET_NAME  # noqa: E402
from storage import r2_store  # noqa: E402
from utils.time_aware import BEIJING_TZ, now_beijing_iso  # noqa: E402


def _month_offset(year: int, month: int, offset: int) -> tuple[int, int]:
    zero_based = year * 12 + (month - 1) + offset
    return zero_based // 12, zero_based % 12 + 1


def _default_target_month(retention_months: int) -> str:
    now = datetime.now(BEIJING_TZ)
    year, month = _month_offset(now.year, now.month, -int(retention_months))
    return f"{year:04d}-{month:02d}"


def _validate_month(value: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y-%m")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("month must be YYYY-MM, e.g. 2026-03") from exc
    return text


def _new_client():
    client = r2_store._s3_client()
    if not client:
        raise RuntimeError("R2 is not configured")
    return client


def _iter_objects(client, prefix: str):
    token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if key:
                yield {"key": key, "size": int(obj.get("Size") or 0)}
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break


def _read_json_key(key: str) -> tuple[Any | None, str]:
    client = _new_client()
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


def _scan_round_key(obj: dict[str, Any], target_month: str) -> dict[str, Any]:
    key = str(obj.get("key") or "")
    data, err = _read_json_key(key)
    if err:
        return {"kind": "round_read_error", "key": key, "size": int(obj.get("size") or 0), "error": err}
    if not isinstance(data, dict):
        return {"kind": "round_skip", "key": key, "size": int(obj.get("size") or 0), "reason": "not_json_object"}
    timestamp = str(data.get("timestamp") or "")
    if timestamp.startswith(target_month):
        return {
            "kind": "delete_key",
            "source": "windows_round",
            "key": key,
            "size": int(obj.get("size") or 0),
            "timestamp": timestamp,
            "round_index": data.get("index"),
        }
    return {"kind": "round_skip", "key": key, "size": int(obj.get("size") or 0), "timestamp": timestamp}


def _scan_legacy_conversation(obj: dict[str, Any], target_month: str) -> dict[str, Any]:
    key = str(obj.get("key") or "")
    data, err = _read_json_key(key)
    if err:
        return {"kind": "legacy_read_error", "key": key, "size": int(obj.get("size") or 0), "error": err}
    if not isinstance(data, dict):
        return {"kind": "legacy_skip", "key": key, "size": int(obj.get("size") or 0), "reason": "not_json_object"}
    rounds = data.get("rounds")
    if not isinstance(rounds, list):
        return {"kind": "legacy_skip", "key": key, "size": int(obj.get("size") or 0), "reason": "no_rounds_list"}
    remove = []
    keep = []
    for round_entry in rounds:
        if isinstance(round_entry, dict) and str(round_entry.get("timestamp") or "").startswith(target_month):
            remove.append(round_entry)
        else:
            keep.append(round_entry)
    if not remove:
        return {
            "kind": "legacy_skip",
            "key": key,
            "size": int(obj.get("size") or 0),
            "total_rounds": len(rounds),
            "reason": "no_target_month_rounds",
        }
    removed_indices = []
    for round_entry in remove:
        if isinstance(round_entry, dict):
            removed_indices.append(round_entry.get("index"))
    return {
        "kind": "legacy_rewrite",
        "source": "windows_legacy_conversation",
        "key": key,
        "size": int(obj.get("size") or 0),
        "total_rounds": len(rounds),
        "remove_rounds": len(remove),
        "keep_rounds": len(keep),
        "removed_indices": removed_indices[:200],
        "payload_after": {**data, "rounds": keep},
    }


def _delete_keys(client, keys: list[str]) -> int:
    deleted = 0
    for i in range(0, len(keys), 1000):
        chunk = keys[i : i + 1000]
        if not chunk:
            continue
        client.delete_objects(
            Bucket=R2_BUCKET_NAME,
            Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
        )
        deleted += len(chunk)
    return deleted


def _manifest_for_output(manifest: dict[str, Any]) -> dict[str, Any]:
    out = dict(manifest)
    legacy = []
    for item in out.get("legacy_rewrites", []):
        slim = dict(item)
        slim.pop("payload_after", None)
        legacy.append(slim)
    out["legacy_rewrites"] = legacy
    return out


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    client = _new_client()
    target_month = args.month or _default_target_month(args.retention_months)
    delete_keys: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if not args.skip_date_backups:
        for obj in _iter_objects(client, f"conversations/{target_month}"):
            key = str(obj.get("key") or "")
            if key.startswith(f"conversations/{target_month}"):
                delete_keys.append({**obj, "source": "conversations_date_backup"})

    window_objects = []
    if not args.skip_round_files or not args.skip_legacy:
        window_objects = list(_iter_objects(client, "windows/"))

    if args.max_round_objects is not None and args.apply:
        raise SystemExit("--max-round-objects is for dry-run/smoke only; do not combine it with --apply")

    if not args.skip_round_files:
        round_candidates = [
            obj
            for obj in window_objects
            if "/rounds/" in str(obj.get("key") or "") and str(obj.get("key") or "").endswith(".json")
        ]
        if args.max_round_objects is not None:
            round_candidates = round_candidates[: max(0, int(args.max_round_objects))]
        if round_candidates:
            with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
                futures = [executor.submit(_scan_round_key, obj, target_month) for obj in round_candidates]
                for idx, future in enumerate(as_completed(futures), start=1):
                    result = future.result()
                    if result.get("kind") == "delete_key":
                        delete_keys.append(result)
                    elif result.get("kind") == "round_read_error":
                        errors.append(result)
                    if args.progress_every and idx % int(args.progress_every) == 0:
                        print(
                            f"scanned round files {idx}/{len(round_candidates)}; matched={sum(1 for x in delete_keys if x.get('source') == 'windows_round')}",
                            file=sys.stderr,
                        )

    legacy_rewrites: list[dict[str, Any]] = []
    if not args.skip_legacy:
        legacy_candidates = [
            obj for obj in window_objects if str(obj.get("key") or "").endswith("/conversation.json")
        ]
        if legacy_candidates:
            with ThreadPoolExecutor(max_workers=max(1, min(int(args.workers), 4))) as executor:
                futures = [executor.submit(_scan_legacy_conversation, obj, target_month) for obj in legacy_candidates]
                for future in as_completed(futures):
                    result = future.result()
                    if result.get("kind") == "legacy_rewrite":
                        legacy_rewrites.append(result)
                    elif result.get("kind") == "legacy_read_error":
                        errors.append(result)

    total_delete_bytes = sum(int(item.get("size") or 0) for item in delete_keys)
    legacy_removed_rounds = sum(int(item.get("remove_rounds") or 0) for item in legacy_rewrites)
    return {
        "schema_version": 1,
        "generated_at": now_beijing_iso(),
        "target_month": target_month,
        "default_rule": f"current Beijing month minus {int(args.retention_months)} months",
        "apply": bool(args.apply),
        "delete_keys": sorted(delete_keys, key=lambda item: str(item.get("key") or "")),
        "legacy_rewrites": sorted(legacy_rewrites, key=lambda item: str(item.get("key") or "")),
        "errors": errors,
        "stats": {
            "delete_key_count": len(delete_keys),
            "delete_key_bytes": total_delete_bytes,
            "delete_key_mib": round(total_delete_bytes / 1024 / 1024, 2),
            "legacy_rewrite_key_count": len(legacy_rewrites),
            "legacy_removed_rounds": legacy_removed_rounds,
        },
    }


def apply_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    client = _new_client()
    keys = [str(item.get("key") or "") for item in manifest.get("delete_keys", []) if str(item.get("key") or "")]
    rewritten = 0
    deleted = _delete_keys(client, keys)
    for item in manifest.get("legacy_rewrites", []):
        key = str(item.get("key") or "")
        payload = item.get("payload_after")
        if key and isinstance(payload, dict):
            _write_json_key(client, key, payload)
            rewritten += 1
    return {"deleted_keys": deleted, "rewritten_legacy_keys": rewritten}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune old R2 conversation original archives by month.")
    parser.add_argument("--month", type=_validate_month, help="Target month YYYY-MM. Default: current Beijing month minus retention.")
    parser.add_argument("--retention-months", type=int, default=3, help="Default target offset in months. Default: 3.")
    parser.add_argument("--apply", action="store_true", help="Actually delete/rewrite R2 data. Default is dry-run.")
    parser.add_argument("--manifest", help="Write manifest JSON to this path.")
    parser.add_argument("--workers", type=int, default=12, help="Concurrent R2 readers for round files. Default: 12.")
    parser.add_argument("--progress-every", type=int, default=500, help="Print scan progress every N round files. 0 disables.")
    parser.add_argument("--skip-date-backups", action="store_true", help="Skip conversations/YYYY-MM* date backup keys.")
    parser.add_argument("--skip-round-files", action="store_true", help="Skip windows/*/rounds/*.json files.")
    parser.add_argument("--skip-legacy", action="store_true", help="Skip rewriting windows/*/conversation.json legacy packs.")
    parser.add_argument("--max-round-objects", type=int, help="Dry-run smoke limit for windows/*/rounds scans.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args)
    apply_result = None
    if args.apply:
        apply_result = apply_manifest(manifest)
        manifest["apply_result"] = apply_result

    output_manifest = _manifest_for_output(manifest)
    if args.manifest:
        path = Path(args.manifest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"stats": output_manifest["stats"], "errors": output_manifest["errors"], "apply_result": apply_result}, ensure_ascii=False, indent=2))
    if output_manifest["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
