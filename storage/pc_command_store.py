"""R2 storage helpers for the desktop PC command queue."""
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from utils.log import get_logger

R2_KEY_PC_COMMAND_QUEUE = "pc_commands/queue.json"

_pc_command_write_lock = threading.Lock()

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def get_pc_command_queue() -> dict:
    """读取电脑指令队列，不存在时返回空队列结构。"""
    client = _s3_client()
    if not client:
        return {"pending": []}
    data = _read_json(client, R2_KEY_PC_COMMAND_QUEUE)
    if not isinstance(data, dict):
        return {"pending": []}
    pending = data.get("pending")
    if not isinstance(pending, list):
        return {"pending": []}
    cleaned = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        cmd = str(item.get("cmd") or "").strip()
        created_at = str(item.get("createdAt") or "").strip()
        if not item_id or not cmd:
            continue
        cleaned.append({"id": item_id, "cmd": cmd, "createdAt": created_at})
    return {"pending": cleaned}


def append_pc_command(cmd: str) -> Optional[dict]:
    """向电脑指令队列追加一条命令并返回新增项。"""
    command = (cmd or "").strip()
    if not command:
        return None
    client = _s3_client()
    if not client:
        return None
    item = {
        "id": str(uuid4()),
        "cmd": command,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with _pc_command_write_lock:
        try:
            data = _read_json(client, R2_KEY_PC_COMMAND_QUEUE)
            if not isinstance(data, dict):
                data = {"pending": []}
            pending = data.get("pending")
            if not isinstance(pending, list):
                pending = []
            pending.append(item)
            data["pending"] = pending
            _write_json(client, R2_KEY_PC_COMMAND_QUEUE, data)
            return item
        except Exception as e:
            logger.error("append_pc_command 失败 cmd=%s error=%s", command, e, exc_info=True)
            return None


def mark_pc_commands_done(done_ids: list[str]) -> int:
    """按 id 删除已执行命令，返回实际删除数量（幂等）。"""
    if not isinstance(done_ids, list):
        return 0
    target_ids = {str(x or "").strip() for x in done_ids if str(x or "").strip()}
    if not target_ids:
        return 0
    client = _s3_client()
    if not client:
        return 0
    with _pc_command_write_lock:
        try:
            data = _read_json(client, R2_KEY_PC_COMMAND_QUEUE)
            if not isinstance(data, dict):
                return 0
            pending = data.get("pending")
            if not isinstance(pending, list) or not pending:
                return 0
            new_pending = []
            removed = 0
            for item in pending:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                if item_id and item_id in target_ids:
                    removed += 1
                    continue
                new_pending.append(item)
            if removed > 0:
                data["pending"] = new_pending
                _write_json(client, R2_KEY_PC_COMMAND_QUEUE, data)
            return removed
        except Exception as e:
            logger.error("mark_pc_commands_done 失败 done_ids=%s error=%s", list(target_ids), e, exc_info=True)
            return 0
