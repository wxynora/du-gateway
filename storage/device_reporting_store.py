"""SQLite hot store for per-device reporting switches."""
from __future__ import annotations

import threading

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

DEVICE_REPORTING_BUCKETS = ("battery", "screen", "foreground", "location", "usage")
DEFAULT_DEVICE_REPORTING_CONFIG = {key: True for key in DEVICE_REPORTING_BUCKETS}

_write_lock = threading.Lock()

logger = get_logger(__name__)


def normalize_device_reporting_config(config: dict | None) -> dict:
    out = dict(DEFAULT_DEVICE_REPORTING_CONFIG)
    if isinstance(config, dict):
        for key in DEVICE_REPORTING_BUCKETS:
            if key in config:
                out[key] = bool(config.get(key))
    return out


def _json_dict(raw: str | None) -> dict:
    data = runtime_sqlite.json_loads(raw, {})
    return data if isinstance(data, dict) else {}


def has_any_config() -> bool:
    try:
        with runtime_sqlite.connect() as conn:
            return conn.execute("SELECT 1 FROM device_reporting_config LIMIT 1").fetchone() is not None
    except Exception as e:
        logger.warning("device_reporting_sqlite has_any_config failed error=%s", e)
        return False


def import_config_doc(doc: dict | None) -> None:
    src = doc if isinstance(doc, dict) else {}
    devices = src.get("devices") if isinstance(src.get("devices"), dict) else {}
    if not devices:
        return
    now = str(src.get("updatedAt") or "").strip() or now_beijing_iso()
    with _write_lock:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for device_id, raw_config in devices.items():
                    did = str(device_id or "").strip()
                    if not did:
                        continue
                    config = normalize_device_reporting_config(raw_config if isinstance(raw_config, dict) else None)
                    updated_at = (
                        str((raw_config or {}).get("updatedAt") or "").strip()
                        if isinstance(raw_config, dict)
                        else ""
                    ) or now
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO device_reporting_config
                            (device_id, config_json, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (did, runtime_sqlite.json_dumps(config), updated_at),
                    )
                conn.execute("COMMIT")
                logger.info("device_reporting_sqlite_bootstrap imported=%s", len(devices))
            except Exception:
                conn.execute("ROLLBACK")
                raise


def get_config(device_id: str) -> dict | None:
    did = str(device_id or "").strip()
    if not did:
        return dict(DEFAULT_DEVICE_REPORTING_CONFIG)
    try:
        with runtime_sqlite.connect() as conn:
            row = conn.execute(
                "SELECT config_json FROM device_reporting_config WHERE device_id = ?",
                (did,),
            ).fetchone()
        if row is None:
            return None
        return normalize_device_reporting_config(_json_dict(row["config_json"]))
    except Exception as e:
        logger.warning("device_reporting_sqlite get_config failed device_id=%s error=%s", did, e)
        return None


def save_config(device_id: str, config: dict) -> dict | None:
    did = str(device_id or "").strip()
    if not did:
        return None
    next_config = normalize_device_reporting_config(config)
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO device_reporting_config
                            (device_id, config_json, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (did, runtime_sqlite.json_dumps(next_config), now_beijing_iso()),
                    )
                    conn.execute("COMMIT")
                    return next_config
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("device_reporting_sqlite save_config failed device_id=%s error=%s", did, e)
            return None


def update_bucket(device_id: str, bucket: str, enabled: bool) -> dict | None:
    did = str(device_id or "").strip()
    key = str(bucket or "").strip()
    if not did or key not in DEVICE_REPORTING_BUCKETS:
        return None
    current = get_config(did) or dict(DEFAULT_DEVICE_REPORTING_CONFIG)
    current[key] = bool(enabled)
    return save_config(did, current)
