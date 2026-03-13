# R2 存储（S3 兼容 API）
# 与需求文档十一「R2 存储结构」对齐：global/、conversations/、dynamic_memory/、core_cache/
import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from utils.time_aware import today_beijing, now_beijing_iso

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import (
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_KEY_LATEST_4_ROUNDS,
)

# 实时层：渡的回忆，每 4 轮更新
R2_KEY_GLOBAL_SUMMARY = "global/summary.txt"
# 动态层：重要记忆，7 天有效，权重机制，融合/褪色/保鲜
R2_KEY_DYNAMIC_MEMORY = "dynamic_memory/current.json"
# 核心缓存层：动态层里「更重要」的，待每周筛选进长期层
R2_KEY_CORE_CACHE = "core_cache/pending.json"
# 小本本：网关拎出后按时间先后排序存储
R2_KEY_NOTEBOOK = "notebook/entries.json"

# 多窗口同时写全局 key 时用进程内锁，避免 last-write-wins 覆盖（多进程部署需外部锁）
_global_write_lock = threading.Lock()
_notebook_write_lock = threading.Lock()

# 日志
from utils.log import get_logger
logger = get_logger(__name__)

# 每个窗口在 R2 下的前缀
def _prefix(window_id: str) -> str:
    return f"windows/{window_id}"


def _s3_client():
    """创建 R2 的 S3 兼容客户端。"""
    if not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        return None
    endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _get_key(prefix: str, key: str) -> str:
    return f"{prefix}/{key}" if prefix else key


def _read_json(client, key: str) -> Optional[Any]:
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None  # 首次无文件，正常
        logger.error("R2 read_json 失败 key=%s error=%s", key, e, exc_info=True)
        return None
    except Exception as e:
        logger.error("R2 read_json 失败 key=%s error=%s", key, e, exc_info=True)
        return None


def _write_json(client, key: str, data: Any):
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception as e:
        logger.error("R2 write_json 失败 key=%s error=%s", key, e, exc_info=True)
        raise


# ---------- 对话原文存档 ----------
# 主存：windows/<id>/conversation.json（按窗口读最近 N 轮、总结用）
# 备份：conversations/YYYY-MM-DD/window_<id>.json（按日期归档，与文档十一一致）


def _conversations_key_for_date(window_id: str, date: str) -> str:
    """conversations/日期/window_<id>.json，用于按日期备份。"""
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in window_id)
    return f"conversations/{date}/window_{safe_id}.json"


def append_conversation_round(window_id: str, round_index: int, messages: list) -> bool:
    """
    追加一轮对话原文。
    ① 写 windows/<id>/conversation.json（主存，总结/读轮用）
    ② 写 conversations/YYYY-MM-DD/window_<id>.json（按日期备份，与文档一致）
    """
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 append_conversation_round window_id=%s", window_id)
        logger.info("R2 未存档：未配置 R2 凭证（R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY）")
        return False
    try:
        prefix = _prefix(window_id)
        key = _get_key(prefix, "conversation.json")
        existing = _read_json(client, key)
        if existing is None:
            existing = {"rounds": []}
        round_entry = {"index": round_index, "messages": messages}
        existing.setdefault("rounds", []).append(round_entry)
        _write_json(client, key, existing)
        # 按日期备份到 conversations/（文档十一：原文存档）
        today = today_beijing()
        conv_key = _conversations_key_for_date(window_id, today)
        conv_existing = _read_json(client, conv_key)
        if conv_existing is None:
            conv_existing = {"window_id": window_id, "date": today, "rounds": []}
        conv_existing.setdefault("rounds", []).append(round_entry)
        _write_json(client, conv_key, conv_existing)
        logger.info("R2 已写入 对话轮次 window_id=%s round_index=%s key=%s", window_id, round_index, key)
        return True
    except Exception as e:
        logger.error("append_conversation_round 失败 window_id=%s round_index=%s error=%s", window_id, round_index, e, exc_info=True)
        return False


# ---------- 小本本（按时间先后排序，滚动保留） ----------


def get_notebook_entries() -> list:
    """读取小本本条目列表，按 timestamp 升序。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_NOTEBOOK)
    if not data or not data.get("entries"):
        return []
    return sorted(data.get("entries", []), key=lambda e: e.get("timestamp", ""))


def notebook_append_entry(content: str) -> bool:
    """
    追加一条小本本（原文不动），打时间戳，按时间先后排序写回 R2。
    content: 原文，不删改。
    """
    if not (content or str(content).strip()):
        return False
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 notebook_append_entry")
        return False
    with _notebook_write_lock:
        try:
            data = _read_json(client, R2_KEY_NOTEBOOK)
            if data is None:
                data = {"entries": []}
            entries = data.get("entries") or []
            ts = now_beijing_iso()
            entries.append({"timestamp": ts, "content": str(content).strip()})
            entries.sort(key=lambda e: e.get("timestamp", ""))
            data["entries"] = entries
            _write_json(client, R2_KEY_NOTEBOOK, data)
            logger.info("notebook_append_entry 已写入 R2 条数=%s", len(entries))
            return True
        except Exception as e:
            logger.error("notebook_append_entry 失败 error=%s", e, exc_info=True)
            return False


def get_conversation_rounds(window_id: str, last_n: int = 4) -> list:
    """获取该窗口最近 N 轮对话原文。"""
    client = _s3_client()
    if not client:
        return []
    prefix = _prefix(window_id)
    key = _get_key(prefix, "conversation.json")
    data = _read_json(client, key)
    if not data or not data.get("rounds"):
        return []
    rounds = data["rounds"][-last_n:]
    return rounds


def _content_to_text_for_preview(content) -> str:
    """把 message content（str 或 list of parts）尽量转成纯文本，用于管理端预览。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                else:
                    parts.append(f"[{c.get('type', '')}]")
            else:
                parts.append(str(c))
        return " ".join(parts).strip()
    return str(content).strip()


def list_conversation_rounds_preview(window_id: str, preview_chars: int = 24) -> list[dict]:
    """
    列出该窗口所有轮次的序号 + 前几个字预览（便于管理端定位 round_index）。
    返回：[{ "index": 1, "preview": "user:... | assistant:..." }, ...]
    """
    client = _s3_client()
    if not client:
        return []
    prefix = _prefix(window_id)
    key = _get_key(prefix, "conversation.json")
    data = _read_json(client, key)
    if not data or not data.get("rounds"):
        return []

    out: list[dict] = []
    for r in data.get("rounds") or []:
        idx = r.get("index")
        msgs = r.get("messages") or []
        user_text = ""
        asst_text = ""
        for m in msgs:
            role = (m.get("role") or "").lower()
            t = _content_to_text_for_preview(m.get("content"))
            if role == "user" and not user_text:
                user_text = t
            if role == "assistant" and not asst_text:
                asst_text = t
        preview = f"user:{user_text} | assistant:{asst_text}".strip()
        preview = preview.replace("\n", " ").replace("\r", " ")
        if preview_chars and preview_chars > 0 and len(preview) > preview_chars:
            preview = preview[:preview_chars] + "…"
        out.append({"index": idx, "preview": preview})

    # 按 index 升序
    out.sort(key=lambda x: (x.get("index") or 0))
    return out


def delete_conversation_round(window_id: str, round_index: int) -> bool:
    """
    从该窗口存档中删除指定轮次（老婆在 RikkaHub 删掉该轮后，记忆系统同步删除）。
    删除：
    1) 主存 windows/<id>/conversation.json
    2) 按日期备份 conversations/YYYY-MM-DD/window_<id>.json（全量回溯，最佳努力）
    """
    client = _s3_client()
    if not client:
        return False
    try:
        prefix = _prefix(window_id)
        key = _get_key(prefix, "conversation.json")
        data = _read_json(client, key)
        if not data or not data.get("rounds"):
            return False
        new_rounds = [r for r in data["rounds"] if r.get("index") != round_index]
        if len(new_rounds) == len(data["rounds"]):
            logger.warning("delete_conversation_round 未找到 round_index=%s window_id=%s", round_index, window_id)
            return False
        data["rounds"] = new_rounds
        _write_json(client, key, data)
        # 回溯删除 conversations/ 下按日期备份
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in window_id)
        suffix = f"/window_{safe_id}.json"
        token = None
        deleted_backup_files = 0
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": "conversations/"}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in (resp.get("Contents") or []):
                k = obj.get("Key") or ""
                if not k.endswith(suffix):
                    continue
                conv_data = _read_json(client, k)
                if not conv_data or not conv_data.get("rounds"):
                    continue
                before = len(conv_data.get("rounds") or [])
                conv_data["rounds"] = [r for r in conv_data["rounds"] if r.get("index") != round_index]
                after = len(conv_data["rounds"])
                if after != before:
                    _write_json(client, k, conv_data)
                    deleted_backup_files += 1
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
        logger.info(
            "delete_conversation_round 已删除 window_id=%s round_index=%s backup_files=%s",
            window_id,
            round_index,
            deleted_backup_files,
        )
        return True
    except Exception as e:
        logger.error("delete_conversation_round 失败 window_id=%s round_index=%s error=%s", window_id, round_index, e, exc_info=True)
        return False


# ---------- 窗口总结（全局一份，所有白名单窗口共享） ----------


def get_summary(window_id: str = "") -> Optional[str]:
    """读取全局总结（白名单窗口共享）。window_id 保留参数兼容，未使用。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_GLOBAL_SUMMARY)
        return resp["Body"].read().decode("utf-8").strip()
    except Exception:
        return None


def save_summary(window_id: str, summary: str) -> bool:
    """保存全局总结（覆盖）。多窗口写同一 key 时加锁。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_GLOBAL_SUMMARY,
                Body=summary.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
            return True
        except Exception as e:
            logger.error("save_summary 失败 error=%s", e, exc_info=True)
            return False


# ---------- 全局「最新四轮」供新窗口注入 ----------


def get_latest_4_rounds_global() -> list:
    """获取 R2 中全局保存的最近四轮原文（新窗口注入用）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_LATEST_4_ROUNDS)
    if not data or not data.get("rounds"):
        return []
    return data.get("rounds", [])


def update_latest_4_rounds_global(rounds: list) -> bool:
    """更新全局最近四轮（每次存档后由网关调用）。多窗口写同一 key 时加锁。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"rounds": rounds[-4:]}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_LATEST_4_ROUNDS, payload)
            return True
        except Exception as e:
            logger.error("update_latest_4_rounds_global 失败 error=%s", e, exc_info=True)
            return False


# ---------- 该窗口是否有历史（是否为新窗口） ----------


def has_window_history(window_id: str) -> bool:
    """该窗口是否已有过存档（有则不是新窗口）。空 window_id 视为无历史，走新窗逻辑。"""
    if not (window_id and window_id.strip()):
        return False
    client = _s3_client()
    if not client:
        return False
    prefix = _prefix(window_id)
    key = _get_key(prefix, "conversation.json")
    try:
        client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except Exception:
        return False


# ---------- 动态层 current.json ----------


def get_dynamic_memory_list() -> list:
    """读取动态层记忆列表。结构：[ { id, content, importance, mention_count, last_mentioned, created_at }, ... ]"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DYNAMIC_MEMORY)
    if not data or not data.get("memories"):
        return []
    return data.get("memories", [])


def ensure_dynamic_memory_ids(memories: list) -> tuple[list, bool]:
    """
    确保动态层每条记忆都有稳定 id；如缺失则补 uuid4。
    返回 (memories_new, changed)。
    """
    if not memories:
        return [], False
    changed = False
    out = []
    for m in memories:
        if not isinstance(m, dict):
            continue
        mm = dict(m)
        if not mm.get("id"):
            mm["id"] = str(uuid4())
            changed = True
        if mm.get("mention_count") is None:
            mm["mention_count"] = 0
            changed = True
        out.append(mm)
    return out, changed


def save_dynamic_memory_list(memories: list) -> bool:
    """写回动态层记忆列表。多窗口同时写时加锁。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DYNAMIC_MEMORY, {"memories": memories})
            return True
        except Exception as e:
            logger.error("save_dynamic_memory_list 失败 error=%s", e, exc_info=True)
            return False


# ---------- 核心缓存层 pending.json（待审；importance>=4 存当轮原文，mention_count>=5 存融合版） ----------


def get_core_cache_pending() -> list:
    """读取待审列表。每项含 id, promoted_by, content, importance, mention_count, promoted_at。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_CORE_CACHE)
    if not data or not data.get("pending"):
        return []
    return data.get("pending", [])


def save_core_cache_pending(pending: list) -> bool:
    """写回待审列表。多窗口写时加锁。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_CORE_CACHE, {"pending": pending})
            return True
        except Exception as e:
            logger.error("save_core_cache_pending 失败 error=%s", e, exc_info=True)
            return False


def promote_to_core_cache(
    window_id: str,
    round_index: int,
    round_messages_text: str,
    current_memories: list,
    touched_mem_id: Optional[str] = None,
) -> None:
    """
    动态层写入/更新后调用：满足条件则加入 pending，去重（已存在 id 不重复加）。
    - 条件A：本轮触及的记忆 importance>=4 → 存当轮对话原文，id=imp_{window_id}_{round_index}，promoted_by=importance
    - 条件B：任一条记忆 mention_count>=5 → 存该条融合版 content，id=记忆 id，promoted_by=mention_count
    """
    client = _s3_client()
    if not client:
        return
    pending = get_core_cache_pending()
    existing_ids = {p.get("id") for p in pending if p.get("id")}
    promoted_at = now_beijing_iso()
    added = False

    # 条件A：本轮触及的那条 importance>=4 → 存当轮原文
    if touched_mem_id and round_messages_text:
        for m in current_memories:
            if m.get("id") != touched_mem_id:
                continue
            if int(m.get("importance") or 0) >= 4:
                imp_id = f"imp_{window_id}_{round_index}"
                if imp_id not in existing_ids:
                    pending.append({
                        "id": imp_id,
                        "promoted_by": "importance",
                        "content": round_messages_text,
                        "importance": int(m.get("importance") or 0),
                        "mention_count": int(m.get("mention_count") or 0),
                        "promoted_at": promoted_at,
                        "tag": (m.get("tag") or "").strip(),
                    })
                    existing_ids.add(imp_id)
                    added = True
            break

    # 条件B：mention_count>=5 的存融合版，用记忆 id 去重
    for m in current_memories:
        mid = m.get("id")
        if not mid or int(m.get("mention_count") or 0) < 5:
            continue
        if mid in existing_ids:
            continue
        pending.append({
            "id": mid,
            "promoted_by": "mention_count",
            "content": (m.get("content") or "").strip(),
            "importance": int(m.get("importance") or 0),
            "mention_count": int(m.get("mention_count") or 0),
            "promoted_at": promoted_at,
            "tag": (m.get("tag") or "").strip(),
        })
        existing_ids.add(mid)
        added = True

    if added:
        save_core_cache_pending(pending)
        logger.info("core_cache 提拔 条数=%s", len(pending))


def delete_core_cache_by_id(entry_id: str) -> bool:
    """从 pending 中删除指定 id 的条目（人工审完后调用）。"""
    pending = get_core_cache_pending()
    new_pending = [p for p in pending if p.get("id") != entry_id]
    if len(new_pending) == len(pending):
        return False
    return save_core_cache_pending(new_pending)


# ---------- 图片描述存档 ----------


def save_image_description(window_id: str, message_id: str, description: str) -> bool:
    """将某条消息中图片的文字描述存到 R2。"""
    client = _s3_client()
    if not client:
        return False
    prefix = _prefix(window_id)
    key = _get_key(prefix, f"images/{message_id}.txt")
    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=key,
        Body=description.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    return True


# ---------- 一键清空（测试/重置用） ----------


# 网关在 R2 里使用的所有前缀，清空时只删这些，不动桶里其他 key
_R2_WIPE_PREFIXES = ("windows/", "conversations/", "global/", "dynamic_memory/", "core_cache/", "notebook/")


def delete_all_gateway_data() -> tuple[bool, int, Optional[str]]:
    """
    一键删除当前网关在 R2 中存的所有记录（对话、总结、动态层、核心缓存、小本本、图片描述等）。
    返回 (是否成功, 删除的 key 数量, 错误信息)。
    """
    client = _s3_client()
    if not client:
        return False, 0, "R2 未配置"
    keys_to_delete = []
    try:
        for prefix in _R2_WIPE_PREFIXES:
            token = None
            while True:
                kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
                if token:
                    kwargs["ContinuationToken"] = token
                resp = client.list_objects_v2(**kwargs)
                for obj in (resp.get("Contents") or []):
                    k = obj.get("Key")
                    if k:
                        keys_to_delete.append(k)
                if resp.get("IsTruncated"):
                    token = resp.get("NextContinuationToken")
                else:
                    break
        if not keys_to_delete:
            logger.info("delete_all_gateway_data 无数据可删")
            return True, 0, None
        deleted = 0
        for i in range(0, len(keys_to_delete), 1000):
            chunk = keys_to_delete[i : i + 1000]
            client.delete_objects(
                Bucket=R2_BUCKET_NAME,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )
            deleted += len(chunk)
        logger.info("delete_all_gateway_data 已删除 %s 个 key", deleted)
        return True, deleted, None
    except Exception as e:
        logger.error("delete_all_gateway_data 失败 error=%s", e, exc_info=True)
        return False, 0, str(e)
