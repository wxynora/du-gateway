"""Per-device reporting configuration with SQLite primary state and R2 compatibility."""

from __future__ import annotations

import threading

from config import R2_BUCKET_NAME
from storage import device_reporting_store
from storage.r2_client import _read_json, _s3_client, _write_json
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

R2_KEY_DEVICE_REPORTING_CONFIG = "global/device_reporting_config.json"
DEVICE_REPORTING_BUCKETS = device_reporting_store.DEVICE_REPORTING_BUCKETS
DEFAULT_DEVICE_REPORTING_CONFIG = device_reporting_store.DEFAULT_DEVICE_REPORTING_CONFIG

_global_write_lock = threading.Lock()
_device_reporting_config_bootstrap_lock = threading.Lock()
_DEVICE_REPORTING_CONFIG_BOOTSTRAPPED = False

def _normalize_device_reporting_config(config: dict | None) -> dict:
    return device_reporting_store.normalize_device_reporting_config(config)


def _device_reporting_config_doc() -> dict:
    client = _s3_client()
    if not client:
        return {"devices": {}}
    data = _read_json(client, R2_KEY_DEVICE_REPORTING_CONFIG)
    return data if isinstance(data, dict) else {"devices": {}}


def _ensure_device_reporting_config_bootstrapped() -> None:
    global _DEVICE_REPORTING_CONFIG_BOOTSTRAPPED
    if _DEVICE_REPORTING_CONFIG_BOOTSTRAPPED:
        return
    with _device_reporting_config_bootstrap_lock:
        if _DEVICE_REPORTING_CONFIG_BOOTSTRAPPED:
            return
        try:
            if device_reporting_store.has_any_config():
                _DEVICE_REPORTING_CONFIG_BOOTSTRAPPED = True
                return
            device_reporting_store.import_config_doc(_device_reporting_config_doc())
        except Exception as e:
            logger.warning("device_reporting_config sqlite bootstrap 失败 error=%s", e)
        _DEVICE_REPORTING_CONFIG_BOOTSTRAPPED = True


def get_device_reporting_config(device_id: str) -> dict:
    """读取单台设备的非健康数据上报开关；默认每类开启。"""
    did = str(device_id or "").strip()
    if not did:
        return dict(DEFAULT_DEVICE_REPORTING_CONFIG)
    _ensure_device_reporting_config_bootstrapped()
    sqlite_config = device_reporting_store.get_config(did)
    if sqlite_config is not None:
        return sqlite_config
    doc = _device_reporting_config_doc()
    devices = doc.get("devices") if isinstance(doc.get("devices"), dict) else {}
    config = _normalize_device_reporting_config(devices.get(did) if isinstance(devices.get(did), dict) else None)
    if did in devices:
        try:
            device_reporting_store.save_config(did, config)
        except Exception as e:
            logger.warning("get_device_reporting_config sqlite 回填失败 device_id=%s error=%s", did, e)
    return config


def save_device_reporting_config(device_id: str, config: dict) -> dict | None:
    """保存单台设备的非健康数据上报开关。"""
    did = str(device_id or "").strip()
    if not did:
        return None
    client = _s3_client()
    if not client:
        return None
    next_config = _normalize_device_reporting_config(config)
    try:
        with _global_write_lock:
            doc = _read_json(client, R2_KEY_DEVICE_REPORTING_CONFIG)
            if not isinstance(doc, dict):
                doc = {}
            devices = doc.get("devices") if isinstance(doc.get("devices"), dict) else {}
            devices[did] = {
                **next_config,
                "updatedAt": now_beijing_iso(),
            }
            doc["devices"] = devices
            doc["updatedAt"] = now_beijing_iso()
            _write_json(client, R2_KEY_DEVICE_REPORTING_CONFIG, doc)
            try:
                device_reporting_store.save_config(did, next_config)
            except Exception as e:
                logger.warning("save_device_reporting_config sqlite 同步失败 device_id=%s error=%s", did, e)
        return next_config
    except Exception as e:
        logger.error("save_device_reporting_config 失败 device_id=%s error=%s", did, e, exc_info=True)
        return None


def update_device_reporting_bucket_config(device_id: str, bucket: str, enabled: bool) -> dict | None:
    """更新单个非健康数据类别的上报开关。"""
    did = str(device_id or "").strip()
    key = str(bucket or "").strip()
    if not did or key not in DEVICE_REPORTING_BUCKETS:
        return None
    client = _s3_client()
    if not client:
        return None
    try:
        with _global_write_lock:
            doc = _read_json(client, R2_KEY_DEVICE_REPORTING_CONFIG)
            if not isinstance(doc, dict):
                doc = {}
            devices = doc.get("devices") if isinstance(doc.get("devices"), dict) else {}
            current = _normalize_device_reporting_config(devices.get(did) if isinstance(devices.get(did), dict) else None)
            current[key] = bool(enabled)
            devices[did] = {
                **current,
                "updatedAt": now_beijing_iso(),
            }
            doc["devices"] = devices
            doc["updatedAt"] = now_beijing_iso()
            _write_json(client, R2_KEY_DEVICE_REPORTING_CONFIG, doc)
            try:
                device_reporting_store.save_config(did, current)
            except Exception as e:
                logger.warning("update_device_reporting_bucket_config sqlite 同步失败 device_id=%s bucket=%s error=%s", did, key, e)
        return current
    except Exception as e:
        logger.error("update_device_reporting_bucket_config 失败 device_id=%s bucket=%s error=%s", did, key, e, exc_info=True)
        return None


def is_device_reporting_bucket_enabled(device_id: str, bucket: str) -> bool:
    """判断某台设备某个非健康数据类别是否允许入库。"""
    key = str(bucket or "").strip()
    if key not in DEVICE_REPORTING_BUCKETS:
        return True
    return bool(get_device_reporting_config(device_id).get(key, True))
