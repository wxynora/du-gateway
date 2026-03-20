# R2 存储（S3 兼容 API）
# 与需求文档十一「R2 存储结构」对齐：global/、conversations/、dynamic_memory/、core_cache/
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

from utils.time_aware import today_beijing, now_beijing_iso, BEIJING_TZ

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
# MiniApp 可编辑核心 Prompt（全局注入）
R2_KEY_CORE_PROMPT = "global/core_prompt_316.txt"
# MiniApp 背景配置与图片（跨设备同步）
R2_KEY_MINIAPP_BG_CONFIG = "global/miniapp_bg_config.json"
R2_KEY_MINIAPP_BG_IMAGE = "global/miniapp_bg_image"
R2_KEY_MINIAPP_BG_IMAGE_PREFIX = "global/miniapp_bg_image_v"
# MiniApp 首页「渡今天想说的话」（按日缓存）
R2_KEY_MINIAPP_DAILY_WHISPER = "global/miniapp_daily_whisper.json"
# MiniApp 每周小报告（按周缓存）
R2_KEY_MINIAPP_WEEKLY_REPORT = "global/miniapp_weekly_report.json"
# MiniApp 心情温度计（今日 + 历史）
R2_KEY_MINIAPP_MOOD_METER = "global/miniapp_mood_meter.json"
# MiniApp 纪念日配置
R2_KEY_MINIAPP_ANNIVERSARY = "global/miniapp_anniversary.json"
# 渡的记事本：固定注入记忆（按条目维护）
R2_KEY_DU_NOTEBOOK = "global/du_notebook.json"
# MiniApp 赛博种树：开始日期等元信息
R2_KEY_CYBER_TREE_META = "global/cyber_tree_meta.json"
# 小渡的记忆文档：固定文本，供以后版本读取（不参与检索/注入逻辑）
R2_KEY_DU_MEMORY_DOC = "docs/du_memory_doc_v1.txt"
# 主动发消息：上一次成功主动联系的时间（北京时间 ISO）
R2_KEY_LAST_PROACTIVE_CONTACT_AT = "global/last_proactive_contact_at.txt"
# 主动发消息：目标用户最近一次在 TG 发消息的时间（北京时间 ISO），用于「正在聊天时不主动发」
R2_KEY_LAST_TELEGRAM_USER_ACTIVITY_AT = "global/last_telegram_user_activity_at.txt"
# Telegram：TodoList（每个 tg 窗口一份 JSON）
R2_KEY_TG_TODOS = "tg/todos.json"
# 日历/提醒（V2 第一批：只读 + 禁用）
R2_KEY_SCHEDULE_ITEMS = "schedule/items.json"
R2_KEY_SCHEDULE_FIRED = "schedule/fired.json"
# 动态记忆召回调试记录（用于 MiniApp 可视化排查）
R2_KEY_DYNAMIC_RECALL_DEBUG = "dynamic_memory/recall_debug.json"

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


# 连接/超时类错误时重试（与 Notion 类似）
_R2_RETRY_TIMES = 3
_R2_RETRY_SLEEP = 2


def _write_json(client, key: str, data: Any):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    last_err = None
    for attempt in range(_R2_RETRY_TIMES):
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
            return
        except Exception as e:
            last_err = e
            if attempt < _R2_RETRY_TIMES - 1:
                logger.warning("R2 write_json 第 %s 次失败 key=%s error=%s，%s 秒后重试", attempt + 1, key, e, _R2_RETRY_SLEEP)
                time.sleep(_R2_RETRY_SLEEP)
    logger.error("R2 write_json 失败 key=%s error=%s", key, last_err, exc_info=True)
    raise last_err


# ---------- 对话原文存档 ----------
# 主存：windows/<id>/conversation.json（按窗口读最近 N 轮、总结用）
# 备份：conversations/YYYY-MM-DD/window_<id>.json（按日期归档，与文档十一一致）


def _conversations_key_for_date(window_id: str, date: str) -> str:
    """conversations/日期/window_<id>.json，用于按日期备份。"""
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in window_id)
    return f"conversations/{date}/window_{safe_id}.json"


def append_conversation_round(window_id: str, round_index: int, messages: list, timestamp: str = "") -> bool:
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
        ts = (timestamp or "").strip() or now_beijing_iso()
        round_entry = {"index": round_index, "timestamp": ts, "messages": messages}
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


def overwrite_conversation_rounds(window_id: str, rounds: list[dict]) -> bool:
    """
    覆盖写入某个窗口的对话存档（windows/<id>/conversation.json），用于重放/纠偏。
    - rounds 结构需为 [{ "index": int, "messages": [...] }, ...]。
    - 不改 conversations/YYYY-MM-DD/ 下面的按日备份（避免误删历史备份）。
    """
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 overwrite_conversation_rounds window_id=%s", window_id)
        return False
    try:
        # 仅覆盖主存 windows/<id>/conversation.json
        prefix = _prefix(window_id)
        key = _get_key(prefix, "conversation.json")
        payload = {"rounds": rounds or []}
        _write_json(client, key, payload)
        logger.info(
            "overwrite_conversation_rounds 完成 window_id=%s rounds=%s key=%s",
            window_id,
            len(rounds or []),
            key,
        )
        return True
    except Exception as e:
        logger.error("overwrite_conversation_rounds 失败 window_id=%s error=%s", window_id, e, exc_info=True)
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


def notebook_delete_entry_by_timestamp(timestamp: str) -> bool:
    """按 timestamp 删除一条小本本记录（用于手机端管理）。"""
    ts = (timestamp or "").strip()
    if not ts:
        return False
    client = _s3_client()
    if not client:
        return False
    with _notebook_write_lock:
        try:
            data = _read_json(client, R2_KEY_NOTEBOOK)
            if data is None:
                return False
            entries = data.get("entries") or []
            before = len(entries)
            entries = [e for e in entries if (e.get("timestamp") or "").strip() != ts]
            if len(entries) == before:
                return False
            entries.sort(key=lambda e: e.get("timestamp", ""))
            data["entries"] = entries
            _write_json(client, R2_KEY_NOTEBOOK, data)
            logger.info("notebook_delete_entry_by_timestamp 已删除 ts=%s 剩余=%s", ts, len(entries))
            return True
        except Exception as e:
            logger.error("notebook_delete_entry_by_timestamp 失败 ts=%s error=%s", ts, e, exc_info=True)
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


def get_conversation_round_by_index(window_id: str, round_index: int) -> Optional[dict]:
    """读取该窗口指定 index 的轮次（返回 {index,timestamp,messages} 或 None）。"""
    if round_index < 1:
        return None
    client = _s3_client()
    if not client:
        return None
    prefix = _prefix(window_id)
    key = _get_key(prefix, "conversation.json")
    data = _read_json(client, key)
    if not data or not data.get("rounds"):
        return None
    for r in data.get("rounds") or []:
        if (r.get("index") or 0) == round_index:
            return r
    return None


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


def get_last_proactive_contact_at() -> Optional[str]:
    """读取上次主动联系时间（北京时间 ISO）。未配置 R2 或不存在则返回 None。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_LAST_PROACTIVE_CONTACT_AT)
        v = resp["Body"].read().decode("utf-8").strip()
        return v or None
    except Exception:
        return None


def save_last_proactive_contact_at(iso_str: str) -> bool:
    """保存上次主动联系时间（覆盖）。多窗口写同一 key 时加锁。"""
    client = _s3_client()
    if not client:
        return False
    s = (iso_str or "").strip()
    if not s:
        return False
    with _global_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_LAST_PROACTIVE_CONTACT_AT,
                Body=s.encode("utf-8"),
                ContentType="text/plain",
            )
            return True
        except Exception:
            return False


def get_last_telegram_user_activity_at() -> Optional[str]:
    """读取目标用户最近一次在 Telegram 发消息的时间（北京时间 ISO）。未配置 R2 或不存在则返回 None。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_LAST_TELEGRAM_USER_ACTIVITY_AT)
        v = resp["Body"].read().decode("utf-8").strip()
        return v or None
    except Exception:
        return None


def save_last_telegram_user_activity_at(iso_str: str) -> bool:
    """保存目标用户最近一次在 Telegram 发消息的时间（覆盖）。Bot 收到该用户消息时调用。"""
    client = _s3_client()
    if not client:
        return False
    s = (iso_str or "").strip()
    if not s:
        return False
    with _global_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_LAST_TELEGRAM_USER_ACTIVITY_AT,
                Body=s.encode("utf-8"),
                ContentType="text/plain",
            )
            return True
        except Exception:
            return False


def get_tg_todos(window_id: str) -> list[dict]:
    """读取 Telegram 窗口的 TodoList。window_id 应为 tg_{user_id}。"""
    if not (window_id and window_id.strip()):
        return []
    client = _s3_client()
    if not client:
        return []
    prefix = _prefix(window_id)
    key = _get_key(prefix, R2_KEY_TG_TODOS)
    data = _read_json(client, key)
    if not data:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def save_tg_todos(window_id: str, items: list[dict]) -> bool:
    """保存 Telegram 窗口的 TodoList（覆盖）。"""
    if not (window_id and window_id.strip()):
        return False
    client = _s3_client()
    if not client:
        return False
    prefix = _prefix(window_id)
    key = _get_key(prefix, R2_KEY_TG_TODOS)
    payload = {"items": items or []}
    with _global_write_lock:
        try:
            _write_json(client, key, payload)
            return True
        except Exception:
            return False


def get_schedule_items() -> list[dict]:
    """读取日历/提醒条目列表。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_SCHEDULE_ITEMS)
    if not data or not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out = [x for x in items if isinstance(x, dict)]
    out.sort(key=lambda x: (str(x.get("datetime") or ""), str(x.get("id") or "")))
    return out


def save_schedule_items(items: list[dict]) -> bool:
    """保存日历/提醒条目列表（覆盖）。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"items": items or []}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_SCHEDULE_ITEMS, payload)
            return True
        except Exception as e:
            logger.error("save_schedule_items 失败 error=%s", e, exc_info=True)
            return False


def disable_schedule_item(item_id: str) -> bool:
    """禁用某条提醒：enabled=false，未来不再触发。"""
    iid = (item_id or "").strip()
    if not iid:
        return False
    items = get_schedule_items()
    if not items:
        return False
    changed = False
    now_iso = now_beijing_iso()
    for it in items:
        if str(it.get("id") or "").strip() != iid:
            continue
        if bool(it.get("enabled")):
            it["enabled"] = False
            it["disabled_at"] = now_iso
            changed = True
        break
    if not changed:
        return False
    return save_schedule_items(items)


def enable_schedule_item(item_id: str) -> bool:
    """启用某条提醒：enabled=true。"""
    iid = (item_id or "").strip()
    if not iid:
        return False
    items = get_schedule_items()
    if not items:
        return False
    changed = False
    now_iso = now_beijing_iso()
    for it in items:
        if str(it.get("id") or "").strip() != iid:
            continue
        if not bool(it.get("enabled")):
            it["enabled"] = True
            it["enabled_at"] = now_iso
            changed = True
        break
    if not changed:
        return False
    return save_schedule_items(items)


def create_schedule_item(
    title: str,
    datetime_str: str,
    repeat: str = "once",
    note: str = "",
    enabled: bool = True,
    weekly_weekday: Optional[int] = None,
    weekly_time: str = "",
    daily_time: str = "",
    created_by: str = "wife",
    target_role: str = "wife",
) -> Optional[dict]:
    """创建一条提醒并写入 schedule/items.json。"""
    def _parse_hhmm(raw: str) -> tuple[int, int] | None:
        """解析 HH:mm，兼容全角冒号与 0:0 这类输入。"""
        s = str(raw or "").strip()
        if not s:
            return None
        s = s.replace("：", ":")
        if ":" not in s:
            return None
        hh, mm = (s.split(":", 1) + [""])[:2]
        hh = hh.strip()
        mm = mm.strip()
        if not hh.isdigit() or not mm.isdigit():
            return None
        hhi = int(hh)
        mmi = int(mm)
        if hhi < 0 or hhi > 23 or mmi < 0 or mmi > 59:
            return None
        return hhi, mmi

    def _norm_hhmm(raw: str) -> str:
        parsed = _parse_hhmm(raw)
        if not parsed:
            return ""
        hhi, mmi = parsed
        return f"{hhi:02d}:{mmi:02d}"

    t = (title or "").strip()
    dt = (datetime_str or "").strip()
    rep = (repeat or "once").strip().lower() or "once"
    n = (note or "").strip()
    creator = (created_by or "wife").strip().lower() or "wife"
    if creator not in ("wife", "du"):
        creator = "wife"
    target = (target_role or "wife").strip().lower() or "wife"
    if target not in ("wife", "du"):
        target = "wife"
    if not t:
        return None
    if rep not in ("once", "daily", "weekly"):
        rep = "once"

    wday = weekly_weekday if isinstance(weekly_weekday, int) else None
    wtime = _norm_hhmm(weekly_time)
    dtime = _norm_hhmm(daily_time)
    if rep == "weekly":
        if wday is None or wday < 0 or wday > 6:
            return None
        hm = _parse_hhmm(wtime)
        if not hm:
            return None
        hhi, mmi = hm
        # 计算“下一次该周几该时刻”的北京时间，保存为 datetime 锚点
        now = datetime.now(BEIJING_TZ)
        next_dt = now.replace(hour=hhi, minute=mmi, second=0, microsecond=0)
        delta_days = (wday - next_dt.weekday()) % 7
        next_dt = next_dt + timedelta(days=delta_days)
        if next_dt <= now:
            next_dt = next_dt + timedelta(days=7)
        dt = next_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    elif rep == "daily":
        hm = _parse_hhmm(dtime)
        if not hm:
            return None
        hhi, mmi = hm
        now = datetime.now(BEIJING_TZ)
        next_dt = now.replace(hour=hhi, minute=mmi, second=0, microsecond=0)
        if next_dt <= now:
            next_dt = next_dt + timedelta(days=1)
        dt = next_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    else:
        if not dt:
            return None

    item = {
        "id": str(uuid4()),
        "title": t,
        "datetime": dt,
        "repeat": rep,
        "enabled": bool(enabled),
        "note": n,
        "created_by": creator,
        "target_role": target,
        "created_at": now_beijing_iso(),
    }
    if rep == "weekly" and wday is not None:
        item["weekly_weekday"] = int(wday)
        item["weekly_time"] = wtime
    if rep == "daily":
        item["daily_time"] = dtime
    items = get_schedule_items()
    items.append(item)
    ok = save_schedule_items(items)
    return item if ok else None


def delete_schedule_item(item_id: str) -> bool:
    """删除某条提醒。"""
    iid = (item_id or "").strip()
    if not iid:
        return False
    items = get_schedule_items()
    if not items:
        return False
    new_items = [it for it in items if str(it.get("id") or "").strip() != iid]
    if len(new_items) == len(items):
        return False
    return save_schedule_items(new_items)


def get_schedule_fired_keys() -> set[str]:
    """读取已触发 occurrence_key 集合。"""
    client = _s3_client()
    if not client:
        return set()
    data = _read_json(client, R2_KEY_SCHEDULE_FIRED)
    if not data or not isinstance(data, dict):
        return set()
    keys = data.get("keys")
    if not isinstance(keys, list):
        return set()
    out = set()
    for k in keys:
        s = str(k or "").strip()
        if s:
            out.add(s)
    return out


def add_schedule_fired_key(occurrence_key: str) -> bool:
    """写入一条已触发 occurrence_key（幂等）。"""
    k = (occurrence_key or "").strip()
    if not k:
        return False
    keys = get_schedule_fired_keys()
    if k in keys:
        return True
    keys.add(k)
    payload = {
        "keys": sorted(keys),
        "updated_at": now_beijing_iso(),
    }
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_SCHEDULE_FIRED, payload)
            return True
        except Exception as e:
            logger.error("add_schedule_fired_key 失败 key=%s error=%s", k, e, exc_info=True)
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


def get_dynamic_recall_debug_events(limit: int = 30) -> list[dict]:
    """读取动态记忆召回调试事件（按时间倒序取最近 N 条）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DYNAMIC_RECALL_DEBUG)
    if not isinstance(data, dict):
        return []
    events = data.get("events")
    if not isinstance(events, list):
        return []
    out = [x for x in events if isinstance(x, dict)]
    out.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    try:
        n = int(limit or 30)
    except Exception:
        n = 30
    if n < 1:
        n = 1
    if n > 200:
        n = 200
    return out[:n]


def append_dynamic_recall_debug_event(event: dict, max_keep: int = 200) -> bool:
    """追加一条动态记忆召回调试事件。"""
    if not isinstance(event, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        keep = int(max_keep or 200)
    except Exception:
        keep = 200
    if keep < 20:
        keep = 20
    if keep > 1000:
        keep = 1000
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_DYNAMIC_RECALL_DEBUG)
            events = []
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                events = [x for x in data.get("events") if isinstance(x, dict)]
            events.append(event)
            if len(events) > keep:
                events = events[-keep:]
            _write_json(
                client,
                R2_KEY_DYNAMIC_RECALL_DEBUG,
                {"events": events, "updated_at": now_beijing_iso()},
            )
            return True
        except Exception as e:
            logger.error("append_dynamic_recall_debug_event 失败 error=%s", e, exc_info=True)
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


# ---------- 小渡的记忆文档（固定文本） ----------


def get_du_memory_doc() -> Optional[str]:
    """读取小渡的记忆文档 1.0；不存在时返回 None。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_DU_MEMORY_DOC)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("get_du_memory_doc 失败 error=%s", e, exc_info=True)
        return None
    except Exception as e:
        logger.error("get_du_memory_doc 失败 error=%s", e, exc_info=True)
        return None


def save_du_memory_doc(text: str) -> bool:
    """
    保存/覆盖小渡的记忆文档。
    仅用于固定文档（不加锁；调用频率极低）。
    """
    client = _s3_client()
    if not client:
        return False
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_DU_MEMORY_DOC,
            Body=(text or "").encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return True
    except Exception as e:
        logger.error("save_du_memory_doc 失败 error=%s", e, exc_info=True)
        return False


def get_core_prompt_text() -> Optional[str]:
    """读取全局核心 Prompt（MiniApp 可编辑）；不存在时返回 None。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_CORE_PROMPT)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("get_core_prompt_text 失败 error=%s", e, exc_info=True)
        return None
    except Exception as e:
        logger.error("get_core_prompt_text 失败 error=%s", e, exc_info=True)
        return None


def save_core_prompt_text(text: str) -> bool:
    """保存/覆盖全局核心 Prompt（MiniApp 编辑后实时生效）。"""
    client = _s3_client()
    if not client:
        return False
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_CORE_PROMPT,
            Body=(text or "").encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return True
    except Exception as e:
        logger.error("save_core_prompt_text 失败 error=%s", e, exc_info=True)
        return False


def get_miniapp_bg_config() -> Optional[dict]:
    """读取 MiniApp 背景配置（JSON）。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_BG_CONFIG)
    return data if isinstance(data, dict) else None


def save_miniapp_bg_config(data: dict) -> bool:
    """保存 MiniApp 背景配置（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    try:
        _write_json(client, R2_KEY_MINIAPP_BG_CONFIG, data)
        return True
    except Exception as e:
        logger.error("save_miniapp_bg_config 失败 error=%s", e, exc_info=True)
        return False


def _miniapp_bg_image_versioned_key(image_version: int) -> str:
    return f"{R2_KEY_MINIAPP_BG_IMAGE_PREFIX}_{int(image_version)}"


def save_miniapp_bg_image(content: bytes, content_type: str, image_version: int | None = None) -> bool:
    """保存 MiniApp 背景图片（可选写入版本化键）。"""
    client = _s3_client()
    if not client:
        return False
    if not content:
        return False
    ctype = (content_type or "application/octet-stream").strip() or "application/octet-stream"
    try:
        # 兼容旧逻辑：始终写最新别名键
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_MINIAPP_BG_IMAGE,
            Body=content,
            ContentType=ctype,
        )
        # 新逻辑：额外写版本化键，彻底规避“路径变了但对象仍是旧缓存”
        if image_version and int(image_version) > 0:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=_miniapp_bg_image_versioned_key(int(image_version)),
                Body=content,
                ContentType=ctype,
            )
        return True
    except Exception as e:
        logger.error("save_miniapp_bg_image 失败 error=%s", e, exc_info=True)
        return False


def get_miniapp_bg_image(image_version: int | None = None) -> tuple[Optional[bytes], str]:
    """读取 MiniApp 背景图片，返回 (bytes, content_type)。支持按版本读取。"""
    client = _s3_client()
    if not client:
        return None, ""
    keys: list[str] = []
    if image_version and int(image_version) > 0:
        keys.append(_miniapp_bg_image_versioned_key(int(image_version)))
    # 回退旧键，兼容历史数据
    keys.append(R2_KEY_MINIAPP_BG_IMAGE)
    try:
        for key in keys:
            try:
                resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            except ClientError as e:
                code = (e.response or {}).get("Error", {}).get("Code", "")
                if code == "NoSuchKey":
                    continue
                raise
            body = resp["Body"].read()
            ctype = ((resp.get("ContentType") or "") + "").strip() or "application/octet-stream"
            if body:
                return body, ctype
        return None, ""
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None, ""
        logger.error("get_miniapp_bg_image 失败 error=%s", e, exc_info=True)
        return None, ""
    except Exception as e:
        logger.error("get_miniapp_bg_image 失败 error=%s", e, exc_info=True)
        return None, ""


def get_miniapp_daily_whisper() -> Optional[dict]:
    """读取 MiniApp 每日小气泡文案。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_DAILY_WHISPER)
    return data if isinstance(data, dict) else None


def get_miniapp_weekly_report() -> Optional[dict]:
    """读取 MiniApp 每周小报告。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_WEEKLY_REPORT)
    return data if isinstance(data, dict) else None


def save_miniapp_weekly_report(data: dict) -> bool:
    """保存 MiniApp 每周小报告（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_WEEKLY_REPORT, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_weekly_report 失败 error=%s", e, exc_info=True)
            return False


def get_miniapp_mood_meter() -> Optional[dict]:
    """读取 MiniApp 心情温度计。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_MOOD_METER)
    return data if isinstance(data, dict) else None


def save_miniapp_mood_meter(data: dict) -> bool:
    """保存 MiniApp 心情温度计（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_MOOD_METER, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_mood_meter 失败 error=%s", e, exc_info=True)
            return False


def get_miniapp_anniversary() -> Optional[dict]:
    """读取 MiniApp 纪念日配置。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_ANNIVERSARY)
    return data if isinstance(data, dict) else None


def save_miniapp_anniversary(data: dict) -> bool:
    """保存 MiniApp 纪念日配置（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_ANNIVERSARY, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_anniversary 失败 error=%s", e, exc_info=True)
            return False


def get_du_notebook_entries() -> list[dict]:
    """读取渡的记事本条目（按 updated_at 倒序）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DU_NOTEBOOK)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out = [x for x in items if isinstance(x, dict)]
    out.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return out


def save_du_notebook_entries(items: list[dict]) -> bool:
    """覆盖保存渡的记事本条目。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            payload = {"items": items or [], "updated_at": now_beijing_iso()}
            _write_json(client, R2_KEY_DU_NOTEBOOK, payload)
            return True
        except Exception as e:
            logger.error("save_du_notebook_entries 失败 error=%s", e, exc_info=True)
            return False


def add_du_notebook_entry(content: str) -> Optional[dict]:
    """新增一条渡的记事本条目。"""
    text = (content or "").strip()
    if not text:
        return None
    items = get_du_notebook_entries()
    now = now_beijing_iso()
    entry = {
        "id": str(uuid4()),
        "content": text,
        "created_at": now,
        "updated_at": now,
    }
    items.append(entry)
    ok = save_du_notebook_entries(items)
    return entry if ok else None


def update_du_notebook_entry(entry_id: str, content: str) -> bool:
    """更新一条渡的记事本条目内容。"""
    eid = (entry_id or "").strip()
    text = (content or "").strip()
    if not eid or not text:
        return False
    items = get_du_notebook_entries()
    changed = False
    now = now_beijing_iso()
    for it in items:
        if str(it.get("id") or "").strip() != eid:
            continue
        it["content"] = text
        it["updated_at"] = now
        changed = True
        break
    if not changed:
        return False
    return save_du_notebook_entries(items)


def delete_du_notebook_entry(entry_id: str) -> bool:
    """删除一条渡的记事本条目。"""
    eid = (entry_id or "").strip()
    if not eid:
        return False
    items = get_du_notebook_entries()
    new_items = [it for it in items if str(it.get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_du_notebook_entries(new_items)


def save_miniapp_daily_whisper(data: dict) -> bool:
    """保存 MiniApp 每日小气泡文案（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_DAILY_WHISPER, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_daily_whisper 失败 error=%s", e, exc_info=True)
            return False


def get_cyber_tree_meta() -> Optional[dict]:
    """读取赛博种树元信息。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_CYBER_TREE_META)
    return data if isinstance(data, dict) else None


def save_cyber_tree_meta(data: dict) -> bool:
    """保存赛博种树元信息。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_CYBER_TREE_META, data)
            return True
        except Exception as e:
            logger.error("save_cyber_tree_meta 失败 error=%s", e, exc_info=True)
            return False


def get_total_conversation_rounds() -> int:
    """
    统计 windows/*/conversation.json 的总轮次。
    用于 MiniApp 赛博种树展示（非高频调用）。
    """
    client = _s3_client()
    if not client:
        return 0
    total = 0
    try:
        token = None
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": "windows/"}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in (resp.get("Contents") or []):
                key = str(obj.get("Key") or "")
                if not key.endswith("/conversation.json"):
                    continue
                data = _read_json(client, key)
                rounds = (data or {}).get("rounds") if isinstance(data, dict) else None
                if isinstance(rounds, list):
                    total += len(rounds)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
    except Exception as e:
        logger.warning("get_total_conversation_rounds 失败 error=%s", e)
    return max(0, int(total))


def get_window_conversation_rounds(window_id: str) -> int:
    """
    统计单个窗口的对话轮次数。
    """
    wid = (window_id or "").strip()
    if not wid:
        return 0
    client = _s3_client()
    if not client:
        return 0
    try:
        key = _get_key(_prefix(wid), "conversation.json")
        data = _read_json(client, key)
        rounds = (data or {}).get("rounds") if isinstance(data, dict) else None
        if isinstance(rounds, list):
            return len(rounds)
    except Exception as e:
        logger.warning("get_window_conversation_rounds 失败 window_id=%s error=%s", wid, e)
    return 0


# ---------- 一键清空（测试/重置用） ----------


# 网关在 R2 里使用的所有前缀，清空时只删这些，不动桶里其他 key
_R2_WIPE_PREFIXES = ("windows/", "conversations/", "global/", "dynamic_memory/", "core_cache/", "notebook/", "docs/")


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
