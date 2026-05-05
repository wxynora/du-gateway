# R2 存储（S3 兼容 API）
# 与需求文档十一「R2 存储结构」对齐：global/、conversations/、dynamic_memory/、core_cache/
import json
import threading
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

from utils.time_aware import today_beijing, now_beijing_iso, parse_iso_to_beijing, BEIJING_TZ

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
# 实时层：固定 4 轮小段队列，网关负责滚动/分区/淘汰
R2_KEY_GLOBAL_SUMMARY_CHUNKS = "global/summary_chunks.json"
# 动态层：重要记忆，7 天有效，权重机制，融合/褪色/保鲜
R2_KEY_DYNAMIC_MEMORY = "dynamic_memory/current.json"
# 核心缓存层：动态层里「更重要」的，待每周筛选进长期层
R2_KEY_CORE_CACHE = "core_cache/pending.json"
# 小本本：网关拎出后按时间先后排序存储
R2_KEY_NOTEBOOK = "notebook/entries.json"
# MiniApp 可编辑核心 Prompt（全局注入）
R2_KEY_CORE_PROMPT = "global/core_prompt_316.txt"
R2_KEY_CORE_PROMPT_CONFIG = "global/core_prompt_config.json"
R2_KEY_XINYUE_PORTRAIT_CANDIDATES = "portrait_memory/xinyue_candidates.json"
R2_KEY_DU_PORTRAIT_CANDIDATES = "portrait_memory/du_candidates.json"
R2_KEY_INTERACTION_CANDIDATES = "portrait_memory/interaction_candidates.json"
# MiniApp 背景配置与图片（跨设备同步）
R2_KEY_MINIAPP_BG_CONFIG = "global/miniapp_bg_config.json"
R2_KEY_MINIAPP_BG_IMAGE = "global/miniapp_bg_image"
R2_KEY_MINIAPP_BG_IMAGE_PREFIX = "global/miniapp_bg_image_v"
# MiniApp 语音通话头像与界面配置
R2_KEY_MINIAPP_VOICE_CONFIG = "global/miniapp_voice_config.json"
R2_KEY_MINIAPP_VOICE_AVATAR = "global/miniapp_voice_avatar"
R2_KEY_MINIAPP_VOICE_AVATAR_PREFIX = "global/miniapp_voice_avatar_v"
# MiniApp 通话记录
R2_KEY_MINIAPP_CALL_RECORDS = "global/miniapp_call_records.json"
# MiniApp 首页「渡今天想说的话」（按日缓存）
R2_KEY_MINIAPP_DAILY_WHISPER = "global/miniapp_daily_whisper.json"
# MiniApp 每日小报告（按北京日期缓存）
R2_KEY_MINIAPP_DAILY_REPORT = "global/miniapp_daily_report.json"
# MiniApp 心情温度计（今日 + 历史）
R2_KEY_MINIAPP_MOOD_METER = "global/miniapp_mood_meter.json"
# 渡的记事本：固定注入记忆（按条目维护）
R2_KEY_DU_NOTEBOOK = "global/du_notebook.json"
# Stay with Du：时间线、一起看的电影、一起读的书（固定注入记忆）
R2_KEY_STAY_WITH_DU = "global/stay_with_du.json"
# 共读阅读卡片：一本书一张轻量卡，只在共读请求里注入
R2_KEY_CO_READ_CARDS = "co_read/cards.json"
R2_KEY_CO_READ_BOOK_INDEX = "co_read/books/index.json"
R2_KEY_CO_READ_BOOK_PREFIX = "co_read/books"
R2_KEY_CO_READ_UPLOAD_PREFIX = "co_read/uploads"
# MiniApp 赛博种树：开始日期等元信息
R2_KEY_CYBER_TREE_META = "global/cyber_tree_meta.json"
# 小渡的记忆文档：固定文本，供以后版本读取（不参与检索/注入逻辑）
R2_KEY_DU_MEMORY_DOC = "docs/du_memory_doc_v1.txt"
# 主动发消息：上一次成功主动联系的时间（北京时间 ISO）
R2_KEY_LAST_PROACTIVE_CONTACT_AT = "global/last_proactive_contact_at.txt"
# 主动发消息：目标用户最近一次在 TG 发消息的时间（北京时间 ISO），用于「正在聊天时不主动发」
R2_KEY_LAST_TELEGRAM_USER_ACTIVITY_AT = "global/last_telegram_user_activity_at.txt"
# 最近一次真实对话入口：给手机弹窗回执这类后端事件决定回发通道
R2_KEY_LAST_REPLY_CHANNEL = "global/last_reply_channel.json"
# 主动联络「抽中后问渡」的决策记忆，新在前，最多 5 条（闹钟不参与）
R2_KEY_PROACTIVE_DECISION_MEMORY = "global/proactive_decision_memory.json"
R2_KEY_CONVERSATION_FOLLOWUPS = "global/conversation_followups.json"
# Telegram：TodoList（每个 tg 窗口一份 JSON）
R2_KEY_TG_TODOS = "tg/todos.json"
# 日历/提醒（V2 第一批：只读 + 禁用）
R2_KEY_SCHEDULE_ITEMS = "schedule/items.json"
R2_KEY_SCHEDULE_FIRED = "schedule/fired.json"
# 动态记忆召回调试记录（用于 MiniApp 可视化排查）
R2_KEY_DYNAMIC_RECALL_DEBUG = "dynamic_memory/recall_debug.json"
# 动态记忆离线慢整理最近一次结果
R2_KEY_DYNAMIC_MAINTENANCE_REPORT = "dynamic_memory/maintenance_report.json"
# 设备感知聚合：电量/位置/网络等（POST /api/sense 写入）
R2_KEY_SENSE_LATEST = "sense/latest.json"
# 渡的心事：网关从助手回复截取后写入，仅注入渡侧 system
R2_KEY_DU_THOUGHT_LATEST = "global/du_thought_latest.json"
# 渡的日常：隐藏滚动记忆（昨天缩略 + 今天时间线）
R2_KEY_DU_DAILY_STATE = "global/du_daily_state.json"
# Telegram 表情包：映射表（各 tag 下对象 key 列表）+ 分类元数据（中文名等）
R2_KEY_STICKERS_MAPPING = "stickers/mapping.json"
R2_KEY_STICKERS_META = "stickers/meta.json"
# 电脑控制：待执行指令队列（单设备轮询）
R2_KEY_PC_COMMAND_QUEUE = "pc_commands/queue.json"
# SumiTalk app 原生命令：由安卓壳轮询执行，不经过旧 Tasker 队列。
R2_KEY_APP_ACTION_QUEUE = "sumitalk/app_actions.json"
R2_KEY_TRIP_PLANS_PREFIX = "travel_plans"

# 多窗口同时写全局 key 时用进程内锁，避免 last-write-wins 覆盖（多进程部署需外部锁）
_global_write_lock = threading.Lock()
_notebook_write_lock = threading.Lock()
_pc_command_write_lock = threading.Lock()
_app_action_write_lock = threading.Lock()
_trip_plan_write_lock = threading.Lock()
_co_read_book_write_lock = threading.Lock()
_co_read_upload_write_lock = threading.Lock()

# 日志
from utils.log import get_logger
logger = get_logger(__name__)

# 客户端未传 window_id（如 RikkaHub 默认）时在 R2 中使用的固定 id，与 chat 白名单记录一致
WINDOW_ID_DEFAULT = "__default__"
# 历史 bug：空 window_id 时主存写在 windows//conversation.json（prefix 为 "windows/"）
LEGACY_EMPTY_CONVERSATION_KEY = "windows//conversation.json"


def normalize_window_id(window_id: str) -> str:
    """空或仅空白视为默认窗口，保证轮次累计与总结触发与显式 id 一致。"""
    w = (window_id or "").strip()
    return w if w else WINDOW_ID_DEFAULT


def _prefix(window_id: str) -> str:
    return f"windows/{normalize_window_id(window_id)}"


def _read_conversation_data_with_legacy_migrate(window_id: str) -> dict:
    """
    读取主存 conversation.json；若默认窗口在新路径无数据而 legacy（windows//）有，则迁移到新路径后返回。
    """
    client = _s3_client()
    if not client:
        return {}
    wid = normalize_window_id(window_id)
    prefix = _prefix(wid)
    key = _get_key(prefix, "conversation.json")
    data = _read_json(client, key) or {}
    rounds = data.get("rounds")
    if isinstance(rounds, list) and len(rounds) > 0:
        return data
    if wid == WINDOW_ID_DEFAULT:
        legacy = _read_json(client, LEGACY_EMPTY_CONVERSATION_KEY) or {}
        leg_rounds = legacy.get("rounds")
        if isinstance(leg_rounds, list) and len(leg_rounds) > 0:
            try:
                _write_json(client, key, legacy)
                logger.info("已迁移对话主存 %s -> %s", LEGACY_EMPTY_CONVERSATION_KEY, key)
            except Exception as e:
                logger.error("迁移 legacy 对话失败 error=%s", e, exc_info=True)
                return legacy
            return legacy
    return data


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
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in normalize_window_id(window_id))
    return f"conversations/{date}/window_{safe_id}.json"


def append_conversation_round(window_id: str, round_index: int, messages: list, timestamp: str = "", action_note: str = "") -> bool:
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
        wid_norm = normalize_window_id(window_id)
        prefix = _prefix(window_id)
        key = _get_key(prefix, "conversation.json")
        existing = _read_conversation_data_with_legacy_migrate(window_id)
        if not existing.get("rounds"):
            existing = {"rounds": []}
        ts = (timestamp or "").strip() or now_beijing_iso()
        round_entry = {"index": round_index, "timestamp": ts, "messages": messages}
        if str(action_note or "").strip():
            round_entry["action_note"] = str(action_note).strip()
        existing.setdefault("rounds", []).append(round_entry)
        _write_json(client, key, existing)
        # 按日期备份到 conversations/（文档十一：原文存档）
        today = today_beijing()
        conv_key = _conversations_key_for_date(window_id, today)
        conv_existing = _read_json(client, conv_key)
        if conv_existing is None:
            conv_existing = {"window_id": wid_norm, "date": today, "rounds": []}
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


def get_next_round_index(window_id: str) -> int:
    """
    根据主存全文计算下一轮应使用的 round index（从 1 起）。
    不可用「最近 1000 轮的条数 + 1」：超过 1000 轮时该长度恒为 1000，会导致 index 卡在 1001，
    round_index % 4 永远不为 0，实时层总结不再触发。
    """
    client = _s3_client()
    if not client:
        return 1
    data = _read_conversation_data_with_legacy_migrate(window_id)
    if not data or not data.get("rounds"):
        return 1
    rounds = data.get("rounds") or []
    if not isinstance(rounds, list) or not rounds:
        return 1
    max_idx = 0
    for r in rounds:
        if not isinstance(r, dict):
            continue
        idx = r.get("index")
        if isinstance(idx, int) and idx > max_idx:
            max_idx = idx
    if max_idx == 0:
        return len(rounds) + 1
    return max_idx + 1


def get_conversation_rounds(window_id: str, last_n: int = 4) -> list:
    """获取该窗口最近 N 轮对话原文（只读对象尾部，避免整文件过大时一次载入全部 rounds）。"""
    if not _s3_client():
        return []
    data = _read_conversation_data_with_legacy_migrate(window_id)
    if not data or not data.get("rounds"):
        return []
    rounds = data["rounds"][-last_n:]
    return rounds


def get_conversation_round_by_index(window_id: str, round_index: int) -> Optional[dict]:
    """读取该窗口指定 index 的轮次（返回 {index,timestamp,messages} 或 None）。"""
    if round_index < 1:
        return None
    if not _s3_client():
        return None
    data = _read_conversation_data_with_legacy_migrate(window_id)
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
    if not _s3_client():
        return []
    data = _read_conversation_data_with_legacy_migrate(window_id)
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
        data = _read_conversation_data_with_legacy_migrate(window_id)
        if not data or not data.get("rounds"):
            return False
        new_rounds = [r for r in data["rounds"] if r.get("index") != round_index]
        if len(new_rounds) == len(data["rounds"]):
            logger.warning("delete_conversation_round 未找到 round_index=%s window_id=%s", round_index, window_id)
            return False
        data["rounds"] = new_rounds
        _write_json(client, key, data)
        # 回溯删除 conversations/ 下按日期备份
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in normalize_window_id(window_id))
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
            try:
                old = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_GLOBAL_SUMMARY)
                old_body = old["Body"].read()
                if old_body:
                    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
                    backup_key = f"global/summary_backups/summary_{ts}.txt"
                    client.put_object(
                        Bucket=R2_BUCKET_NAME,
                        Key=backup_key,
                        Body=old_body,
                        ContentType="text/plain; charset=utf-8",
                    )
                    logger.info("save_summary 已备份旧总结 key=%s", backup_key)
            except Exception as e:
                logger.warning("save_summary 备份旧总结失败，继续覆盖 error=%s", e)
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


def get_summary_chunks(window_id: str = "") -> dict:
    """读取全局实时层小段队列。window_id 保留参数兼容，未使用。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_GLOBAL_SUMMARY_CHUNKS)
    if not isinstance(data, dict):
        return {}
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        data["chunks"] = []
    return data


def save_summary_chunks(window_id: str, chunks_state: dict) -> bool:
    """保存全局实时层小段队列。window_id 保留参数兼容，未使用。"""
    client = _s3_client()
    if not client:
        return False
    payload = dict(chunks_state or {})
    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        payload["chunks"] = []
    payload["version"] = 1
    payload["updated_at"] = now_beijing_iso()
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_GLOBAL_SUMMARY_CHUNKS, payload)
            return True
        except Exception as e:
            logger.error("save_summary_chunks 失败 error=%s", e, exc_info=True)
            return False


# ---------- sense/latest.json（设备感知：电量/位置等） ----------


def get_sense_latest() -> dict:
    """读取 sense/latest.json，不存在或格式异常时返回 {}。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_SENSE_LATEST)
    if not isinstance(data, dict):
        return {}
    return data


def _duration_ms_between(started_at: str, ended_at: str) -> int:
    start = parse_iso_to_beijing(str(started_at or "").strip())
    end = parse_iso_to_beijing(str(ended_at or "").strip())
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))


def _closed_app_session(active: dict, ended_at: str, reason: str) -> dict | None:
    if not isinstance(active, dict):
        return None
    pkg = str(active.get("packageName") or "").strip()
    started_at = str(active.get("startedAt") or "").strip()
    if not pkg or not started_at:
        return None
    duration_ms = _duration_ms_between(started_at, ended_at)
    if duration_ms < 1000:
        return None
    item = {
        "deviceId": str(active.get("deviceId") or "").strip(),
        "packageName": pkg,
        "appName": str(active.get("appName") or pkg).strip() or pkg,
        "startedAt": started_at,
        "endedAt": str(ended_at or "").strip(),
        "durationMs": duration_ms,
        "endReason": str(reason or "").strip()[:40] or "unknown",
    }
    class_name = str(active.get("className") or "").strip()
    if class_name:
        item["className"] = class_name
    source = str(active.get("source") or "").strip()
    if source:
        item["source"] = source
    return item


def _compact_app_sessions(items: list, device_id: str, limit: int = 5) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_device = str(item.get("deviceId") or device_id or "").strip()
        if device_id and item_device and item_device != device_id:
            continue
        pkg = str(item.get("packageName") or "").strip()
        started_at = str(item.get("startedAt") or "").strip()
        ended_at = str(item.get("endedAt") or "").strip()
        if not pkg or not started_at or not ended_at:
            continue
        try:
            duration_ms = int(item.get("durationMs") or 0)
        except Exception:
            duration_ms = 0
        if duration_ms <= 0:
            duration_ms = _duration_ms_between(started_at, ended_at)
        if duration_ms <= 0:
            continue
        dedupe_key = (pkg, started_at, ended_at)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned = {
            "deviceId": item_device,
            "packageName": pkg,
            "appName": str(item.get("appName") or pkg).strip() or pkg,
            "startedAt": started_at,
            "endedAt": ended_at,
            "durationMs": duration_ms,
        }
        class_name = str(item.get("className") or "").strip()
        if class_name:
            cleaned["className"] = class_name
        source = str(item.get("source") or "").strip()
        if source:
            cleaned["source"] = source
        end_reason = str(item.get("endReason") or "").strip()
        if end_reason:
            cleaned["endReason"] = end_reason[:40]
        out.append(cleaned)
        if len(out) >= max(1, int(limit or 5)):
            break
    return out


def update_app_sessions_from_foreground(foreground_patch: dict) -> bool:
    """
    用前台 app 切换事件维护最近应用会话。
    不替代 usage 24h 快照：这里只记录“几点打开了什么 app、这次看了多久”。
    """
    if not isinstance(foreground_patch, dict):
        return False
    device_id = str(foreground_patch.get("deviceId") or "").strip()
    pkg = str(foreground_patch.get("packageName") or "").strip()
    if not device_id or not pkg:
        return False
    observed_at = str(foreground_patch.get("observedAt") or "").strip() or now_beijing_iso()
    app_name = str(foreground_patch.get("appName") or pkg).strip() or pkg
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            doc = _read_json(client, R2_KEY_SENSE_LATEST)
            if doc is None or not isinstance(doc, dict):
                doc = {}
            bucket = doc.get("app_sessions")
            if not isinstance(bucket, dict):
                bucket = {}
            active = bucket.get("active")
            if not isinstance(active, dict):
                active = {}
            active_device = str(active.get("deviceId") or device_id).strip()
            active_pkg = str(active.get("packageName") or "").strip()
            if active_device == device_id and active_pkg == pkg:
                return True

            old_recent = bucket.get("recent")
            recent = old_recent if isinstance(old_recent, list) else []
            closed = _closed_app_session(active, observed_at, "app_switch") if active_device == device_id else None
            if closed:
                recent = [closed, *recent]

            next_active = {
                "deviceId": device_id,
                "packageName": pkg,
                "appName": app_name[:80],
                "startedAt": observed_at,
                "source": str(foreground_patch.get("source") or "accessibility").strip()[:40] or "accessibility",
            }
            class_name = str(foreground_patch.get("className") or "").strip()
            if class_name:
                next_active["className"] = class_name[:240]

            next_bucket = {
                "deviceId": device_id,
                "active": next_active,
                "recent": _compact_app_sessions(recent, device_id, limit=5),
                "updatedAt": now_beijing_iso(),
            }
            doc["app_sessions"] = next_bucket
            _write_json(client, R2_KEY_SENSE_LATEST, doc)
            if closed:
                _append_sense_history_event(client, "app_sessions", dict(next_bucket))
            return True
        except Exception as e:
            logger.error("update_app_sessions_from_foreground 失败 error=%s", e, exc_info=True)
            return False


def close_app_session_for_device(device_id: str, ended_at: str = "", reason: str = "screen_off") -> bool:
    did = str(device_id or "").strip()
    if not did:
        return False
    ended = str(ended_at or "").strip() or now_beijing_iso()
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            doc = _read_json(client, R2_KEY_SENSE_LATEST)
            if doc is None or not isinstance(doc, dict):
                doc = {}
            bucket = doc.get("app_sessions")
            if not isinstance(bucket, dict):
                return True
            active = bucket.get("active")
            if not isinstance(active, dict) or not active:
                return True
            active_device = str(active.get("deviceId") or did).strip()
            if active_device != did:
                return True
            recent_raw = bucket.get("recent")
            recent = recent_raw if isinstance(recent_raw, list) else []
            closed = _closed_app_session(active, ended, reason)
            if closed:
                recent = [closed, *recent]
            next_bucket = {
                "deviceId": did,
                "active": None,
                "recent": _compact_app_sessions(recent, did, limit=5),
                "updatedAt": now_beijing_iso(),
            }
            doc["app_sessions"] = next_bucket
            _write_json(client, R2_KEY_SENSE_LATEST, doc)
            if closed:
                _append_sense_history_event(client, "app_sessions", dict(next_bucket))
            return True
        except Exception as e:
            logger.error("close_app_session_for_device 失败 device_id=%s error=%s", did, e, exc_info=True)
            return False


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


_APP_ACTION_ALLOWLIST = {"create_system_alarm", "create_calendar_event", "show_choice_dialog", "request_screen_check"}
_APP_ACTION_HISTORY_MAX = 100
_APP_ACTION_EXPIRES_DEFAULT = 900
_APP_ACTION_EXPIRES_MIN = 30
_APP_ACTION_EXPIRES_MAX = 3600
_APP_ACTION_LEASE_SECONDS = 90
_APP_ACTION_MAX_RETRY = 3


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_iso(value: str) -> Optional[datetime]:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _app_action_queue_raw(client) -> dict:
    data = _read_json(client, R2_KEY_APP_ACTION_QUEUE)
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("pending"), list):
        data["pending"] = []
    if not isinstance(data.get("history"), list):
        data["history"] = []
    if not isinstance(data.get("idempotencyKeys"), dict):
        data["idempotencyKeys"] = {}
    return data


def _trim_app_action_history(history: list) -> list:
    rows = [x for x in (history or []) if isinstance(x, dict)]
    rows.sort(key=lambda x: str(x.get("finishedAt") or x.get("createdAt") or ""), reverse=True)
    return rows[:_APP_ACTION_HISTORY_MAX]


def _parse_app_action_datetime(value) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    return dt


def _normalize_calendar_event_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or src.get("summary") or "渡的行程").strip() or "渡的行程"
    if len(title) > 120:
        title = title[:120]
    all_day = bool(src.get("allDay") if "allDay" in src else src.get("all_day", False))
    start = _parse_app_action_datetime(src.get("startAt") or src.get("start_at") or src.get("start_datetime") or src.get("datetime"))
    if not start:
        return None, "start_datetime/startAt 必须是 ISO 时间"

    end = _parse_app_action_datetime(src.get("endAt") or src.get("end_at") or src.get("end_datetime"))
    if not end:
        try:
            duration_minutes = int(src.get("durationMinutes") if "durationMinutes" in src else src.get("duration_minutes", 1440 if all_day else 60))
        except Exception:
            duration_minutes = 1440 if all_day else 60
        if duration_minutes <= 0:
            return None, "duration_minutes 必须大于 0"
        end = start + timedelta(minutes=duration_minutes)
    if end <= start:
        return None, "end_datetime 必须晚于 start_datetime"

    description = str(src.get("description") or src.get("note") or "").strip()
    if len(description) > 1000:
        description = description[:1000]
    location = str(src.get("location") or "").strip()
    if len(location) > 200:
        location = location[:200]
    try:
        reminder_minutes = int(src.get("reminderMinutes") if "reminderMinutes" in src else src.get("reminder_minutes", 10))
    except Exception:
        reminder_minutes = 10
    reminder_minutes = max(-1, min(10080, reminder_minutes))
    notify = bool(src.get("notify", True))

    start_bj = start.astimezone(BEIJING_TZ)
    end_bj = end.astimezone(BEIJING_TZ)
    return {
        "title": title,
        "startAt": start_bj.isoformat(),
        "endAt": end_bj.isoformat(),
        "startMillis": int(start.timestamp() * 1000),
        "endMillis": int(end.timestamp() * 1000),
        "allDay": all_day,
        "description": description,
        "location": location,
        "reminderMinutes": reminder_minutes,
        "notify": notify,
    }, None


def _normalize_app_action_payload(action_type: str, payload: dict) -> tuple[Optional[dict], Optional[str]]:
    if action_type == "create_calendar_event":
        return _normalize_calendar_event_payload(payload)
    if action_type == "show_choice_dialog":
        return _normalize_choice_dialog_payload(payload)
    if action_type == "request_screen_check":
        return _normalize_screen_check_payload(payload)
    if action_type != "create_system_alarm":
        return None, f"不支持的 app action: {action_type}"
    src = payload if isinstance(payload, dict) else {}
    try:
        hour = int(src.get("hour"))
    except Exception:
        return None, "hour 必须是 0-23"
    try:
        minute = int(src.get("minute"))
    except Exception:
        return None, "minute 必须是 0-59"
    if hour < 0 or hour > 23:
        return None, "hour 必须是 0-23"
    if minute < 0 or minute > 59:
        return None, "minute 必须是 0-59"
    title = str(src.get("title") or "渡的提醒").strip() or "渡的提醒"
    if len(title) > 80:
        title = title[:80]
    skip_ui = bool(src.get("skipUi") if "skipUi" in src else src.get("skip_ui", False))
    notify = bool(src.get("notify", True))
    return {
        "hour": hour,
        "minute": minute,
        "title": title,
        "skipUi": skip_ui,
        "notify": notify,
    }, None


def _normalize_choice_label(value, fallback: str) -> str:
    label = str(value or "").strip() or fallback
    if len(label) > 8:
        label = label[:8]
    return label


def _normalize_choice_dialog_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡").strip() or "渡"
    if len(title) > 60:
        title = title[:60]
    message = str(src.get("message") or src.get("content") or "").strip()
    if not message:
        return None, "message 不能为空"
    if len(message) > 500:
        message = message[:500]

    choice_a = src.get("choice_a") or src.get("choiceA") or src.get("positive")
    choice_b = src.get("choice_b") or src.get("choiceB") or src.get("negative")
    raw_choices = src.get("choices")
    if isinstance(raw_choices, list):
        if len(raw_choices) > 0:
            first = raw_choices[0]
            choice_a = first.get("label") if isinstance(first, dict) else first
        if len(raw_choices) > 1:
            second = raw_choices[1]
            choice_b = second.get("label") if isinstance(second, dict) else second
    label_a = _normalize_choice_label(choice_a, "好的")
    label_b = _normalize_choice_label(choice_b, "知道了")

    level = str(src.get("level") or "info").strip().lower()
    if level not in {"info", "warning", "strict"}:
        level = "info"
    dismissible = bool(src.get("dismissible", level != "strict"))
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 600))
    except Exception:
        timeout_seconds = 600
    timeout_seconds = max(30, min(1800, timeout_seconds))
    notify_du = bool(src.get("notifyDu") if "notifyDu" in src else src.get("notify_du", True))
    return {
        "title": title,
        "message": message,
        "level": level,
        "dismissible": dismissible,
        "timeoutSeconds": timeout_seconds,
        "notifyDu": notify_du,
        "choices": [
            {"id": "choice_a", "label": label_a},
            {"id": "choice_b", "label": label_b},
        ],
    }, None


def _normalize_screen_check_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡想查岗").strip() or "渡想查岗"
    if len(title) > 60:
        title = title[:60]
    message = str(src.get("message") or src.get("reason") or "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。").strip()
    if not message:
        message = "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。"
    if len(message) > 500:
        message = message[:500]
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 120))
    except Exception:
        timeout_seconds = 120
    timeout_seconds = max(30, min(300, timeout_seconds))
    return {
        "title": title,
        "message": message,
        "timeoutSeconds": timeout_seconds,
    }, None


def append_app_action(
    action_type: str,
    payload: dict,
    device_id: str = "",
    expires_in_sec: int = _APP_ACTION_EXPIRES_DEFAULT,
    source: str = "tool",
    idempotency_key: str = "",
) -> tuple[Optional[dict], Optional[str]]:
    """向 SumiTalk app 原生命令队列追加一条动作。"""
    action = str(action_type or "").strip()
    if action not in _APP_ACTION_ALLOWLIST:
        return None, f"不允许的 app action: {action}"
    normalized_payload, err = _normalize_app_action_payload(action, payload if isinstance(payload, dict) else {})
    if err:
        return None, err
    try:
        ttl = int(expires_in_sec or _APP_ACTION_EXPIRES_DEFAULT)
    except Exception:
        ttl = _APP_ACTION_EXPIRES_DEFAULT
    ttl = max(_APP_ACTION_EXPIRES_MIN, min(_APP_ACTION_EXPIRES_MAX, ttl))
    client = _s3_client()
    if not client:
        return None, "R2 不可用"

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")
    idem = str(idempotency_key or "").strip()
    item = {
        "id": str(uuid4()),
        "type": action,
        "payload": normalized_payload,
        "deviceId": str(device_id or "").strip(),
        "source": str(source or "tool").strip()[:40] or "tool",
        "createdAt": now_iso,
        "expiresAt": expires_at,
        "leasedUntil": "",
        "retryCount": 0,
    }
    with _app_action_write_lock:
        try:
            data = _app_action_queue_raw(client)
            idem_keys = data.get("idempotencyKeys") or {}
            if isinstance(idem_keys, dict):
                idem_keys = {
                    k: v for k, v in idem_keys.items()
                    if isinstance(v, dict) and _parse_utc_iso(str(v.get("expiresAt") or "")) and _parse_utc_iso(str(v.get("expiresAt") or "")) > now
                }
                data["idempotencyKeys"] = idem_keys
            if idem and isinstance(idem_keys, dict):
                existing_id = str((idem_keys.get(idem) or {}).get("id") or "").strip()
                if existing_id:
                    for old in data.get("pending") or []:
                        if isinstance(old, dict) and str(old.get("id") or "") == existing_id:
                            return {**old, "duplicate": True}, None
            pending = data.get("pending") if isinstance(data.get("pending"), list) else []
            pending.append(item)
            data["pending"] = pending
            if idem:
                idem_keys[idem] = {"id": item["id"], "expiresAt": expires_at}
                data["idempotencyKeys"] = idem_keys
            _write_json(client, R2_KEY_APP_ACTION_QUEUE, data)
            return item, None
        except Exception as e:
            logger.error("append_app_action 失败 type=%s error=%s", action, e, exc_info=True)
            return None, str(e)


def poll_app_actions(device_id: str = "", limit: int = 10) -> dict:
    """安卓壳轮询待执行 app 原生命令。"""
    device = str(device_id or "").strip()
    client = _s3_client()
    if not client:
        return {"ok": False, "actions": [], "pollAfterSec": 20, "error": "R2 不可用"}
    try:
        max_items = max(1, min(20, int(limit or 10)))
    except Exception:
        max_items = 10
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=_APP_ACTION_LEASE_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    with _app_action_write_lock:
        try:
            data = _app_action_queue_raw(client)
            pending = data.get("pending") if isinstance(data.get("pending"), list) else []
            history = data.get("history") if isinstance(data.get("history"), list) else []
            out = []
            next_pending = []
            changed = False
            for item in pending:
                if not isinstance(item, dict):
                    changed = True
                    continue
                exp = _parse_utc_iso(str(item.get("expiresAt") or ""))
                if exp and exp <= now:
                    history.append({**item, "status": "expired", "finishedAt": now_iso})
                    changed = True
                    continue
                target_device = str(item.get("deviceId") or "").strip()
                if target_device and device and target_device != device:
                    next_pending.append(item)
                    continue
                leased = _parse_utc_iso(str(item.get("leasedUntil") or ""))
                if leased and leased > now:
                    next_pending.append(item)
                    continue
                retry_count = int(item.get("retryCount") or 0)
                if leased and leased <= now:
                    retry_count += 1
                    item["retryCount"] = retry_count
                    changed = True
                if retry_count >= _APP_ACTION_MAX_RETRY:
                    history.append({**item, "status": "abandoned", "finishedAt": now_iso})
                    changed = True
                    continue
                if len(out) < max_items:
                    item["leasedUntil"] = lease_until
                    item["retryCount"] = retry_count
                    out.append({
                        "id": str(item.get("id") or ""),
                        "type": str(item.get("type") or ""),
                        "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
                    })
                    changed = True
                next_pending.append(item)
            if changed:
                data["pending"] = next_pending
                data["history"] = _trim_app_action_history(history)
                _write_json(client, R2_KEY_APP_ACTION_QUEUE, data)
            return {"ok": True, "actions": out, "pollAfterSec": 20}
        except Exception as e:
            logger.error("poll_app_actions 失败 device_id=%s error=%s", device, e, exc_info=True)
            return {"ok": False, "actions": [], "pollAfterSec": 20, "error": str(e)}


def report_app_actions(results: list, device_id: str = "") -> dict:
    """安卓壳回执 app 原生命令执行结果。"""
    if not isinstance(results, list):
        return {"ok": False, "error": "results 必须是数组", "processed": 0}
    device = str(device_id or "").strip()
    client = _s3_client()
    if not client:
        return {"ok": False, "error": "R2 不可用", "processed": 0}
    now_iso = _utc_now_iso()
    result_map = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        if item_id:
            result_map[item_id] = row
    if not result_map:
        return {"ok": True, "processed": 0, "items": []}

    with _app_action_write_lock:
        try:
            data = _app_action_queue_raw(client)
            pending = data.get("pending") if isinstance(data.get("pending"), list) else []
            history = data.get("history") if isinstance(data.get("history"), list) else []
            next_pending = []
            processed_items = []
            for item in pending:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                result = result_map.get(item_id)
                if not result:
                    next_pending.append(item)
                    continue
                target_device = str(item.get("deviceId") or "").strip()
                if target_device and device and target_device != device:
                    next_pending.append(item)
                    continue
                status = str(result.get("status") or "").strip().lower()
                if status not in {"done", "failed"}:
                    status = "failed"
                finished = {
                    **item,
                    "status": status,
                    "finishedAt": now_iso,
                    "deviceId": device or target_device,
                    "result": result.get("detail") if isinstance(result.get("detail"), dict) else {},
                    "error": str(result.get("error") or "").strip(),
                }
                history.append(finished)
                processed_items.append(finished)
            data["pending"] = next_pending
            data["history"] = _trim_app_action_history(history)
            _write_json(client, R2_KEY_APP_ACTION_QUEUE, data)
            return {"ok": True, "processed": len(processed_items), "items": processed_items}
        except Exception as e:
            logger.error("report_app_actions 失败 device_id=%s error=%s", device, e, exc_info=True)
            return {"ok": False, "error": str(e), "processed": 0}


def save_du_thought_latest(at_iso: str, content: str) -> bool:
    """写入 global/du_thought_latest.json（渡上一则心事）。"""
    client = _s3_client()
    if not client:
        return False
    if not content or not str(content).strip():
        return False
    payload = {"at": (at_iso or "").strip(), "content": str(content).strip()}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DU_THOUGHT_LATEST, payload)
            return True
        except Exception as e:
            logger.error("save_du_thought_latest 失败 error=%s", e, exc_info=True)
            return False


def get_du_thought_latest() -> Optional[dict]:
    """读取 global/du_thought_latest.json。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_DU_THOUGHT_LATEST)
    if not isinstance(data, dict):
        return None
    return data


def save_du_daily_state(data: dict) -> bool:
    """写入 global/du_daily_state.json。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DU_DAILY_STATE, data)
            return True
        except Exception as e:
            logger.error("save_du_daily_state 失败 error=%s", e, exc_info=True)
            return False


def get_du_daily_state() -> Optional[dict]:
    """读取 global/du_daily_state.json。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_DU_DAILY_STATE)
    if not isinstance(data, dict):
        return None
    return data


def _get_items_json(key: str) -> list[dict]:
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, key)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def _save_items_json(key: str, items: list[dict]) -> bool:
    client = _s3_client()
    if not client:
        return False
    payload = {"items": items if isinstance(items, list) else []}
    with _global_write_lock:
        try:
            _write_json(client, key, payload)
            return True
        except Exception as e:
            logger.error("save items json 失败 key=%s error=%s", key, e, exc_info=True)
            return False


def get_xinyue_portrait_candidates() -> list[dict]:
    return _get_items_json(R2_KEY_XINYUE_PORTRAIT_CANDIDATES)


def save_xinyue_portrait_candidates(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_XINYUE_PORTRAIT_CANDIDATES, items)


def get_du_portrait_candidates() -> list[dict]:
    return _get_items_json(R2_KEY_DU_PORTRAIT_CANDIDATES)


def save_du_portrait_candidates(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_DU_PORTRAIT_CANDIDATES, items)


def get_interaction_candidates() -> list[dict]:
    return _get_items_json(R2_KEY_INTERACTION_CANDIDATES)


def save_interaction_candidates(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_INTERACTION_CANDIDATES, items)


def append_interaction_candidate(summary: str, source_message_id: str = "") -> Optional[dict]:
    content = str(summary or "").strip()
    if not content:
        return None
    items = get_interaction_candidates()
    now = now_beijing_iso()
    entry = {
        "id": str(uuid4()),
        "summary": content,
        "source_message_id": str(source_message_id or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    items.append(entry)
    ok = save_interaction_candidates(items)
    return entry if ok else None


def delete_xinyue_portrait_candidate(entry_id: str) -> bool:
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    items = get_xinyue_portrait_candidates()
    new_items = [it for it in items if str((it or {}).get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_xinyue_portrait_candidates(new_items)


def delete_du_portrait_candidate(entry_id: str) -> bool:
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    items = get_du_portrait_candidates()
    new_items = [it for it in items if str((it or {}).get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_du_portrait_candidates(new_items)


def delete_interaction_candidate(entry_id: str) -> bool:
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    items = get_interaction_candidates()
    new_items = [it for it in items if str((it or {}).get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_interaction_candidates(new_items)


def merge_and_save_sense_bucket(sense_type: str, patch: dict) -> bool:
    """
    按 sense_type（如 battery）将 patch 合并进对应桶，并写入 updatedAt（UTC，形如 2025-03-23T14:00:00Z）。
    其它顶层键（location、network 等）保持不变。patch 中不应含 type。
    """
    client = _s3_client()
    if not client:
        return False
    key = (sense_type or "").strip()
    if not key:
        return False
    with _global_write_lock:
        try:
            doc = _read_json(client, R2_KEY_SENSE_LATEST)
            if doc is None or not isinstance(doc, dict):
                doc = {}
            bucket = doc.get(key)
            if not isinstance(bucket, dict):
                bucket = {}
            merged = dict(bucket)
            merged.update(patch)
            # battery 桶不保留 power（Tasker 误传或未展开变量时污染快照）
            if key == "battery":
                merged.pop("power", None)
            merged["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            doc[key] = merged
            _write_json(client, R2_KEY_SENSE_LATEST, doc)
            _append_sense_history_event(client, key, dict(merged))
            return True
        except Exception as e:
            logger.error("merge_and_save_sense_bucket 失败 type=%s error=%s", key, e, exc_info=True)
            return False


def _trip_plan_key(plan_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(plan_id or "").strip())
    return f"{R2_KEY_TRIP_PLANS_PREFIX}/{safe}.json" if safe else ""


def get_trip_plan(plan_id: str) -> dict:
    """读取一次出行计划。不存在、未配置 R2 或格式异常时返回 {}。"""
    key = _trip_plan_key(plan_id)
    if not key:
        return {}
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, key)
    return data if isinstance(data, dict) else {}


def save_trip_plan(plan: dict) -> bool:
    """保存一次出行计划，key 取 plan_meta.plan_id。"""
    if not isinstance(plan, dict):
        return False
    meta = plan.get("plan_meta") if isinstance(plan.get("plan_meta"), dict) else {}
    plan_id = str(meta.get("plan_id") or plan.get("plan_id") or "").strip()
    key = _trip_plan_key(plan_id)
    if not key:
        return False
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 save_trip_plan plan_id=%s", plan_id)
        return False
    with _trip_plan_write_lock:
        try:
            _write_json(client, key, plan)
            return True
        except Exception as e:
            logger.error("save_trip_plan 失败 plan_id=%s error=%s", plan_id, e, exc_info=True)
            return False


def update_trip_plan(plan_id: str, patch: dict) -> dict:
    """
    浅合并更新一次出行计划，返回更新后的计划。
    仅用于小范围状态/事实写回；复杂合并在调用方完成后用 save_trip_plan。
    """
    if not isinstance(patch, dict):
        return {}
    existing = get_trip_plan(plan_id)
    if not existing:
        existing = {}
    for key, value in patch.items():
        if isinstance(existing.get(key), dict) and isinstance(value, dict):
            merged = dict(existing.get(key) or {})
            merged.update(value)
            existing[key] = merged
        else:
            existing[key] = value
    save_trip_plan(existing)
    return existing


def _append_sense_history_event(client, sense_type: str, bucket_snapshot: dict) -> None:
    """按北京日期写入 sense/history/YYYY-MM-DD.json，仅归档，失败静默。"""
    try:
        d = today_beijing()
        hk = f"sense/history/{d}.json"
        existing = _read_json(client, hk)
        if not isinstance(existing, list):
            existing = []
        existing.append({"type": sense_type, "at": now_beijing_iso(), "data": bucket_snapshot})
        cap = 3000
        if len(existing) > cap:
            existing = existing[-cap:]
        _write_json(client, hk, existing)
    except Exception as e:
        logger.warning("sense 历史归档失败 type=%s error=%s", sense_type, e)


def get_sense_history_for_date(date_str: str) -> list[dict]:
    """读取某日 sense/history/YYYY-MM-DD.json；失败返回 []。"""
    client = _s3_client()
    if not client:
        return []
    day = str(date_str or "").strip()
    if not day:
        return []
    key = f"sense/history/{day}.json"
    data = _read_json(client, key)
    if not isinstance(data, list):
        return []
    return [dict(x) for x in data if isinstance(x, dict)]


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
    """该窗口是否已有过存档（有则不是新窗口）。空 window_id 等价于默认窗口。"""
    if not _s3_client():
        return False
    data = _read_conversation_data_with_legacy_migrate(window_id)
    rounds = data.get("rounds") if isinstance(data, dict) else None
    return isinstance(rounds, list) and len(rounds) > 0


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


def get_proactive_decision_memory_items() -> list:
    """读取主动决策记忆（新在前），最多 5 条；失败返回 []。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_PROACTIVE_DECISION_MEMORY)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)][:5]


def append_proactive_decision_memory(entry: dict) -> bool:
    """在列表头部插入一条决策记录，整体最多保留 5 条。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(entry, dict):
        return False
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_PROACTIVE_DECISION_MEMORY)
            if not isinstance(data, dict):
                data = {}
            items = data.get("items")
            if not isinstance(items, list):
                items = []
            items.insert(0, dict(entry))
            data["items"] = items[:5]
            _write_json(client, R2_KEY_PROACTIVE_DECISION_MEMORY, data)
            return True
        except Exception as e:
            logger.error("append_proactive_decision_memory 失败 error=%s", e, exc_info=True)
            return False


def get_conversation_followups() -> list[dict]:
    """读取会话级延迟续话任务。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_CONVERSATION_FOLLOWUPS)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [dict(x) for x in items if isinstance(x, dict)]


def save_conversation_followups(items: list[dict]) -> bool:
    """保存会话级延迟续话任务（覆盖）。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"items": [dict(x) for x in (items or []) if isinstance(x, dict)]}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_CONVERSATION_FOLLOWUPS, payload)
            return True
        except Exception as e:
            logger.error("save_conversation_followups 失败 error=%s", e, exc_info=True)
            return False


def append_conversation_followup(item: dict) -> bool:
    """追加一条会话级延迟续话任务。"""
    if not isinstance(item, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_CONVERSATION_FOLLOWUPS)
            if not isinstance(data, dict):
                data = {}
            items = data.get("items")
            if not isinstance(items, list):
                items = []
            items.insert(0, dict(item))
            if len(items) > 200:
                items = items[:200]
            data["items"] = items
            _write_json(client, R2_KEY_CONVERSATION_FOLLOWUPS, data)
            return True
        except Exception as e:
            logger.error("append_conversation_followup 失败 error=%s", e, exc_info=True)
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


def get_last_reply_channel() -> Optional[dict]:
    """读取最近一次真实对话入口。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_LAST_REPLY_CHANNEL)
    return data if isinstance(data, dict) else None


def save_last_reply_channel(channel: str, window_id: str = "", target: str = "", at_iso: str = "") -> bool:
    """保存最近一次真实对话入口，供后端事件按同入口回发。"""
    ch = str(channel or "").strip().lower()
    if ch not in {"tg", "wechat", "qq", "sumitalk"}:
        return False
    payload = {
        "channel": ch,
        "window_id": str(window_id or "").strip(),
        "target": str(target or "").strip(),
        "at": str(at_iso or "").strip() or now_beijing_iso(),
    }
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_LAST_REPLY_CHANNEL, payload)
            return True
        except Exception as e:
            logger.error("save_last_reply_channel 失败 channel=%s error=%s", ch, e, exc_info=True)
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
    out = []
    for x in items:
        if not isinstance(x, dict):
            continue
        out.append(dict(x))
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
    """读取动态层记忆列表。"""
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
        for key in ("emotion_label", "scene_type", "target_type"):
            if key not in mm:
                mm[key] = ""
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


def touch_dynamic_memory_mentions(memory_ids: list[str]) -> int:
    """按 memory_id 给动态记忆 mention_count +1，并刷新 last_mentioned。"""
    ids: list[str] = []
    seen = set()
    for raw in memory_ids or []:
        mid = str(raw or "").strip()
        if not mid or mid.startswith("core::") or mid in seen:
            continue
        seen.add(mid)
        ids.append(mid)
    if not ids:
        return 0

    memories = get_dynamic_memory_list()
    memories, id_changed = ensure_dynamic_memory_ids(memories)
    if not memories:
        return 0

    id_set = set(ids)
    now = now_beijing_iso()
    touched = 0
    for mem in memories:
        if str((mem or {}).get("id") or "").strip() not in id_set:
            continue
        try:
            mention_count = int((mem or {}).get("mention_count") or 0)
        except Exception:
            mention_count = 0
        mem["mention_count"] = mention_count + 1
        mem["last_mentioned"] = now
        touched += 1

    if not touched:
        if id_changed:
            save_dynamic_memory_list(memories)
        return 0
    if not save_dynamic_memory_list(memories):
        return 0
    logger.info("动态记忆引用回写完成 touched=%s ids=%s", touched, ids[:10])
    return touched


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


def get_dynamic_memory_maintenance_report() -> dict:
    """读取最近一次动态记忆离线慢整理结果。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_DYNAMIC_MAINTENANCE_REPORT)
    return data if isinstance(data, dict) else {}


def save_dynamic_memory_maintenance_report(report: dict) -> bool:
    """写入最近一次动态记忆离线慢整理结果。"""
    if not isinstance(report, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DYNAMIC_MAINTENANCE_REPORT, report)
            return True
        except Exception as e:
            logger.error("save_dynamic_memory_maintenance_report 失败 error=%s", e, exc_info=True)
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


def _upsert_core_cache_pending_index_safe(items: list) -> None:
    try:
        from memory_vector.core_pending_index import upsert_core_pending_items

        upsert_core_pending_items(items)
    except Exception as e:
        logger.warning("core_cache pending 索引 upsert 失败 error=%s", e, exc_info=True)


def _remove_core_cache_pending_index_safe(entry_ids: set[str]) -> None:
    try:
        from memory_vector.core_pending_index import remove_core_pending_ids

        remove_core_pending_ids(entry_ids)
    except Exception as e:
        logger.warning("core_cache pending 索引删除失败 error=%s", e, exc_info=True)


def promote_to_core_cache(
    window_id: str,
    round_index: int,
    round_messages_text: str,
    current_memories: list,
    touched_mem_id: Optional[str] = None,
) -> None:
    """
    动态层写入/更新后调用：满足条件则加入 pending，去重（已存在 id 不重复加）。
    只存“动态层总结后的记忆内容”，不存 user/assistant 原始对话。
    - 条件A：本轮触及的记忆 importance>=4 → 存该记忆的 summary content，id=imp_{window_id}_{round_index}，promoted_by=importance
    - 条件B：任一条记忆 mention_count>=5 → 存该条融合版 content，id=记忆 id，promoted_by=mention_count
    """
    client = _s3_client()
    if not client:
        return
    pending = get_core_cache_pending()
    existing_ids = {p.get("id") for p in pending if p.get("id")}
    promoted_at = now_beijing_iso()
    added = False
    added_items = []

    # 条件A：本轮触及记忆 importance>=4，存动态层 summary（不是原始对话）
    if touched_mem_id:
        for m in current_memories:
            if m.get("id") != touched_mem_id:
                continue
            if int(m.get("importance") or 0) >= 4:
                imp_id = f"imp_{window_id}_{round_index}"
                summary_content = str(m.get("content") or "").strip()
                if imp_id not in existing_ids and summary_content:
                    item = {
                        "id": imp_id,
                        "promoted_by": "importance",
                        "content": summary_content,
                        "importance": int(m.get("importance") or 0),
                        "mention_count": int(m.get("mention_count") or 0),
                        "promoted_at": promoted_at,
                        "tag": (m.get("tag") or "").strip(),
                        "emotion_label": (m.get("emotion_label") or "").strip(),
                        "scene_type": (m.get("scene_type") or "").strip(),
                        "target_type": (m.get("target_type") or "").strip(),
                    }
                    pending.append(item)
                    added_items.append(item)
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
        item = {
            "id": mid,
            "promoted_by": "mention_count",
            "content": (m.get("content") or "").strip(),
            "importance": int(m.get("importance") or 0),
            "mention_count": int(m.get("mention_count") or 0),
            "promoted_at": promoted_at,
            "tag": (m.get("tag") or "").strip(),
            "emotion_label": (m.get("emotion_label") or "").strip(),
            "scene_type": (m.get("scene_type") or "").strip(),
            "target_type": (m.get("target_type") or "").strip(),
        }
        pending.append(item)
        added_items.append(item)
        existing_ids.add(mid)
        added = True

    if added:
        if save_core_cache_pending(pending):
            _upsert_core_cache_pending_index_safe(added_items)
        logger.info("core_cache 提拔 条数=%s", len(pending))


def delete_core_cache_by_id(entry_id: str) -> bool:
    """从 pending 中删除指定 id 的条目（人工审完后调用）。"""
    pending = get_core_cache_pending()
    new_pending = [p for p in pending if p.get("id") != entry_id]
    if len(new_pending) == len(pending):
        return False
    ok = save_core_cache_pending(new_pending)
    if ok:
        _remove_core_cache_pending_index_safe({entry_id})
    return ok


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
    cfg = get_core_prompt_config()
    if isinstance(cfg, dict):
        prompts = cfg.get("prompts") if isinstance(cfg.get("prompts"), dict) else {}
        active_key = str(cfg.get("active_key") or "a").strip().lower()
        active_key = "b" if active_key == "b" else "a"
        active_text = str((prompts or {}).get(active_key) or "").strip()
        if active_text:
            return active_text
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
    cfg = get_core_prompt_config()
    if isinstance(cfg, dict):
        prompts = cfg.get("prompts") if isinstance(cfg.get("prompts"), dict) else {}
        active_key = str(cfg.get("active_key") or "a").strip().lower()
        active_key = "b" if active_key == "b" else "a"
        prompts = {
            "a": str(prompts.get("a") or ""),
            "b": str(prompts.get("b") or ""),
        }
        prompts[active_key] = str(text or "")
        return save_core_prompt_config({"active_key": active_key, "prompts": prompts})
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


def get_core_prompt_config() -> Optional[dict]:
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_CORE_PROMPT_CONFIG)
    if isinstance(data, dict):
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        active_key = str(data.get("active_key") or "a").strip().lower()
        active_key = "b" if active_key == "b" else "a"
        return {
            "active_key": active_key,
            "prompts": {
                "a": str(prompts.get("a") or ""),
                "b": str(prompts.get("b") or ""),
            },
        }
    legacy_text = None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_CORE_PROMPT)
        legacy_text = resp["Body"].read().decode("utf-8")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code != "NoSuchKey":
            logger.error("get_core_prompt_config fallback 失败 error=%s", e, exc_info=True)
    except Exception as e:
        logger.error("get_core_prompt_config fallback 失败 error=%s", e, exc_info=True)
    if legacy_text is None:
        return None
    return {
        "active_key": "a",
        "prompts": {
            "a": str(legacy_text or ""),
            "b": "",
        },
    }


def save_core_prompt_config(data: dict) -> bool:
    client = _s3_client()
    if not client:
        return False
    prompts = data.get("prompts") if isinstance(data, dict) and isinstance(data.get("prompts"), dict) else {}
    active_key = str((data or {}).get("active_key") or "a").strip().lower()
    active_key = "b" if active_key == "b" else "a"
    payload = {
        "active_key": active_key,
        "prompts": {
            "a": str(prompts.get("a") or ""),
            "b": str(prompts.get("b") or ""),
        },
    }
    try:
        with _global_write_lock:
            _write_json(client, R2_KEY_CORE_PROMPT_CONFIG, payload)
            active_text = payload["prompts"].get(active_key) or ""
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_CORE_PROMPT,
                Body=active_text.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
        return True
    except Exception as e:
        logger.error("save_core_prompt_config 失败 error=%s", e, exc_info=True)
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


def get_miniapp_voice_config() -> Optional[dict]:
    """读取 MiniApp 语音通话配置（JSON）。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_VOICE_CONFIG)
    return data if isinstance(data, dict) else None


def save_miniapp_voice_config(data: dict) -> bool:
    """保存 MiniApp 语音通话配置（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    try:
        _write_json(client, R2_KEY_MINIAPP_VOICE_CONFIG, data)
        return True
    except Exception as e:
        logger.error("save_miniapp_voice_config 失败 error=%s", e, exc_info=True)
        return False


def _miniapp_voice_avatar_versioned_key(image_version: int) -> str:
    return f"{R2_KEY_MINIAPP_VOICE_AVATAR_PREFIX}_{int(image_version)}"


def save_miniapp_voice_avatar(content: bytes, content_type: str, image_version: int | None = None) -> bool:
    """保存 MiniApp 语音通话头像（可选写入版本化键）。"""
    client = _s3_client()
    if not client:
        return False
    if not content:
        return False
    ctype = (content_type or "application/octet-stream").strip() or "application/octet-stream"
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_MINIAPP_VOICE_AVATAR,
            Body=content,
            ContentType=ctype,
        )
        if image_version and int(image_version) > 0:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=_miniapp_voice_avatar_versioned_key(int(image_version)),
                Body=content,
                ContentType=ctype,
            )
        return True
    except Exception as e:
        logger.error("save_miniapp_voice_avatar 失败 error=%s", e, exc_info=True)
        return False


def get_miniapp_voice_avatar(image_version: int | None = None) -> tuple[Optional[bytes], str]:
    """读取 MiniApp 语音通话头像，返回 (bytes, content_type)。支持按版本读取。"""
    client = _s3_client()
    if not client:
        return None, ""
    keys: list[str] = []
    if image_version and int(image_version) > 0:
        keys.append(_miniapp_voice_avatar_versioned_key(int(image_version)))
    keys.append(R2_KEY_MINIAPP_VOICE_AVATAR)
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
        logger.error("get_miniapp_voice_avatar 失败 error=%s", e, exc_info=True)
        return None, ""
    except Exception as e:
        logger.error("get_miniapp_voice_avatar 失败 error=%s", e, exc_info=True)
        return None, ""


def get_miniapp_call_records() -> list[dict]:
    """读取 MiniApp 通话记录列表。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_MINIAPP_CALL_RECORDS)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def save_miniapp_call_records(items: list[dict]) -> bool:
    """保存 MiniApp 通话记录列表。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"items": items if isinstance(items, list) else []}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_CALL_RECORDS, payload)
            return True
        except Exception as e:
            logger.error("save_miniapp_call_records 失败 error=%s", e, exc_info=True)
            return False


def delete_miniapp_call_record(call_id: str) -> bool:
    """按 id 删除一条 MiniApp 通话记录。"""
    cid = str(call_id or "").strip()
    if not cid:
        return False
    items = get_miniapp_call_records() or []
    before = len(items)
    kept = [item for item in items if str((item or {}).get("id") or "").strip() != cid]
    if len(kept) == before:
        return False
    return save_miniapp_call_records(kept)


def get_miniapp_daily_whisper() -> Optional[dict]:
    """读取 MiniApp 每日小气泡文案。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_DAILY_WHISPER)
    return data if isinstance(data, dict) else None


def get_miniapp_daily_report() -> Optional[dict]:
    """读取 MiniApp 每日小报告。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_DAILY_REPORT)
    return data if isinstance(data, dict) else None


def save_miniapp_daily_report(data: dict) -> bool:
    """保存 MiniApp 每日小报告（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_DAILY_REPORT, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_daily_report 失败 error=%s", e, exc_info=True)
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


def _empty_stay_with_du_data() -> dict:
    return {
        "timeline": [],
        "moviesTodo": [],
        "moviesDone": [],
        "booksTodo": [],
        "booksDone": [],
    }


def _normalize_stay_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _normalize_stay_timeline(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _normalize_stay_text(item.get("title"), 120)
        if not title:
            continue
        out.append(
            {
                "id": _normalize_stay_text(item.get("id"), 80) or str(uuid4()),
                "date": _normalize_stay_text(item.get("date"), 32),
                "title": title,
                "desc": _normalize_stay_text(item.get("desc"), 600),
            }
        )
    out.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    return out[:200]


def _normalize_stay_media(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _normalize_stay_text(item.get("title"), 160)
        if not title:
            continue
        row = {
            "id": _normalize_stay_text(item.get("id"), 80) or str(uuid4()),
            "title": title,
            "note": _normalize_stay_text(item.get("note"), 600),
        }
        date = _normalize_stay_text(item.get("date"), 32)
        if date:
            row["date"] = date
        out.append(row)
    return out[:300]


def normalize_stay_with_du_data(data: Any) -> dict:
    """规整 Stay with Du 数据结构，供 API、注入和 R2 写入共用。"""
    if not isinstance(data, dict):
        return _empty_stay_with_du_data()
    return {
        "timeline": _normalize_stay_timeline(data.get("timeline")),
        "moviesTodo": _normalize_stay_media(data.get("moviesTodo")),
        "moviesDone": _normalize_stay_media(data.get("moviesDone")),
        "booksTodo": _normalize_stay_media(data.get("booksTodo")),
        "booksDone": _normalize_stay_media(data.get("booksDone")),
    }


def get_stay_with_du_data() -> dict:
    """读取 Stay with Du 数据。"""
    client = _s3_client()
    if not client:
        return _empty_stay_with_du_data()
    data = _read_json(client, R2_KEY_STAY_WITH_DU)
    if not isinstance(data, dict):
        return _empty_stay_with_du_data()
    raw = data.get("data") if isinstance(data.get("data"), dict) else data
    return normalize_stay_with_du_data(raw)


def save_stay_with_du_data(data: dict) -> bool:
    """覆盖保存 Stay with Du 数据。"""
    client = _s3_client()
    if not client:
        return False
    payload = {
        "data": normalize_stay_with_du_data(data),
        "updated_at": now_beijing_iso(),
    }
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_STAY_WITH_DU, payload)
            return True
        except Exception as e:
            logger.error("save_stay_with_du_data 失败 error=%s", e, exc_info=True)
            return False


def _normalize_co_read_text(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:limit]


def _normalize_co_read_recent(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippet = _normalize_co_read_text(item.get("snippet"), 420)
        du_reply = _normalize_co_read_text(item.get("du_reply"), 420)
        user_note = _normalize_co_read_text(item.get("user_note"), 180)
        if not (snippet or du_reply or user_note):
            continue
        out.append(
            {
                "at": _normalize_co_read_text(item.get("at"), 40),
                "progress": _normalize_co_read_text(item.get("progress"), 80),
                "snippet": snippet,
                "user_note": user_note,
                "du_reply": du_reply,
            }
        )
    return out[:8]


def _normalize_co_read_story_recent(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        plot = _normalize_co_read_text(item.get("plot"), 1200)
        if not plot:
            continue
        out.append(
            {
                "section_index": _co_read_int(item.get("section_index"), 0),
                "range": _normalize_co_read_text(item.get("range"), 80),
                "plot": plot,
            }
        )
    out.sort(key=lambda x: int(x.get("section_index") or 0))
    return out[-10:]


def _normalize_co_read_story_milestones(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        event = _normalize_co_read_text(item.get("event"), 260)
        why = _normalize_co_read_text(item.get("why_matters"), 220)
        if not event:
            continue
        out.append(
            {
                "section_index": _co_read_int(item.get("section_index"), 0),
                "event": event,
                "why_matters": why,
            }
        )
    return out[:12]


def _normalize_co_read_string_list(items: Any, item_limit: int = 160, count_limit: int = 8) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        text = _normalize_co_read_text(item, item_limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= count_limit:
            break
    return out


def _normalize_co_read_characters(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _normalize_co_read_text(item.get("name"), 80)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "summary": _normalize_co_read_text(item.get("summary"), 120),
                "status": _normalize_co_read_text(item.get("status"), 260),
                "known_facts": _normalize_co_read_string_list(item.get("known_facts"), 160, 10),
                "open_threads": _normalize_co_read_string_list(item.get("open_threads"), 160, 8),
            }
        )
        if len(out) >= 20:
            break
    return out


def normalize_co_read_book_card(card: Any, book_key: str = "", book_title: str = "") -> dict:
    """规整一本书的共读卡片。"""
    now = now_beijing_iso()
    raw = card if isinstance(card, dict) else {}
    key = _normalize_co_read_text(raw.get("book_key") or book_key, 120)
    title = _normalize_co_read_text(raw.get("book_title") or book_title, 200)
    focus_raw = raw.get("xinyue_focus")
    questions_raw = raw.get("open_questions")
    focus = [
        _normalize_co_read_text(x, 160)
        for x in (focus_raw if isinstance(focus_raw, list) else [])
    ]
    questions = [
        _normalize_co_read_text(x, 160)
        for x in (questions_raw if isinstance(questions_raw, list) else [])
    ]
    focus = [x for x in focus if x][:8]
    questions = [x for x in questions if x][:6]
    return {
        "book_key": key,
        "book_title": title,
        "current_progress": _normalize_co_read_text(raw.get("current_progress"), 80),
        "recent_co_read": _normalize_co_read_recent(raw.get("recent_co_read")),
        "story_recent": _normalize_co_read_story_recent(raw.get("story_recent")),
        "story_milestones": _normalize_co_read_story_milestones(raw.get("story_milestones")),
        "characters": _normalize_co_read_characters(raw.get("characters")),
        "xinyue_focus": focus,
        "du_understanding": _normalize_co_read_text(raw.get("du_understanding"), 600),
        "open_questions": questions,
        "created_at": _normalize_co_read_text(raw.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(raw.get("updated_at"), 40) or now,
    }


def get_co_read_cards_payload() -> dict:
    client = _s3_client()
    if not client:
        return {"cards": {}, "updated_at": ""}
    data = _read_json(client, R2_KEY_CO_READ_CARDS)
    if not isinstance(data, dict):
        return {"cards": {}, "updated_at": ""}
    cards = data.get("cards")
    if not isinstance(cards, dict):
        cards = {}
    out = {}
    for key, value in cards.items():
        clean_key = _normalize_co_read_text(key, 120)
        if not clean_key:
            continue
        out[clean_key] = normalize_co_read_book_card(value, book_key=clean_key)
    return {"cards": out, "updated_at": _normalize_co_read_text(data.get("updated_at"), 40)}


def get_co_read_book_card(book_key: str) -> Optional[dict]:
    key = _normalize_co_read_text(book_key, 120)
    if not key:
        return None
    cards = get_co_read_cards_payload().get("cards") or {}
    card = cards.get(key)
    return normalize_co_read_book_card(card, book_key=key) if isinstance(card, dict) else None


def list_co_read_book_cards() -> list[dict]:
    cards = get_co_read_cards_payload().get("cards") or {}
    out = [normalize_co_read_book_card(card, book_key=key) for key, card in cards.items() if isinstance(card, dict)]
    out.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return out


def save_co_read_book_card(card: dict) -> bool:
    clean = normalize_co_read_book_card(card)
    key = str(clean.get("book_key") or "").strip()
    if not key:
        return False
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            payload = get_co_read_cards_payload()
            cards = payload.get("cards") if isinstance(payload.get("cards"), dict) else {}
            cards[key] = clean
            _write_json(client, R2_KEY_CO_READ_CARDS, {"cards": cards, "updated_at": now_beijing_iso()})
            return True
        except Exception as e:
            logger.error("save_co_read_book_card 失败 key=%s error=%s", key, e, exc_info=True)
            return False


def _prepend_unique_text(items: list[str], text: str, limit: int = 8) -> list[str]:
    clean = _normalize_co_read_text(text, 160)
    if not clean:
        return items[:limit]
    out = [clean]
    for item in items or []:
        old = _normalize_co_read_text(item, 160)
        if old and old != clean:
            out.append(old)
        if len(out) >= limit:
            break
    return out


def update_co_read_book_card(
    book_key: str,
    book_title: str,
    current_progress: str,
    snippet: str,
    user_note: str,
    du_reply: str,
) -> Optional[dict]:
    """用一轮共读更新一本书的轻量卡片。"""
    key = _normalize_co_read_text(book_key, 120)
    if not key:
        return None
    now = now_beijing_iso()
    card = get_co_read_book_card(key) or normalize_co_read_book_card({}, book_key=key, book_title=book_title)
    card["book_key"] = key
    card["book_title"] = _normalize_co_read_text(book_title, 200) or card.get("book_title") or key
    card["current_progress"] = _normalize_co_read_text(current_progress, 80) or card.get("current_progress") or ""
    recent = _normalize_co_read_recent(card.get("recent_co_read"))
    recent.insert(
        0,
        {
            "at": now,
            "progress": card.get("current_progress") or "",
            "snippet": _normalize_co_read_text(snippet, 420),
            "user_note": _normalize_co_read_text(user_note, 180),
            "du_reply": _normalize_co_read_text(du_reply, 420),
        },
    )
    card["recent_co_read"] = _normalize_co_read_recent(recent)
    card["du_understanding"] = _normalize_co_read_text(du_reply, 600) or card.get("du_understanding") or ""
    if user_note:
        card["xinyue_focus"] = _prepend_unique_text(card.get("xinyue_focus") or [], user_note, 8)
        if "?" in user_note or "？" in user_note:
            card["open_questions"] = _prepend_unique_text(card.get("open_questions") or [], user_note, 6)
    card["updated_at"] = now
    clean = normalize_co_read_book_card(card, book_key=key, book_title=book_title)
    return clean if save_co_read_book_card(clean) else None


def _normalize_co_read_key(value: Any) -> str:
    text = str(value or "").strip()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() or ch in "-_" else "-")
    return "".join(out).strip("-")[:160]


def _co_read_book_object_key(book_key: str) -> str:
    safe = _normalize_co_read_key(book_key)
    return f"{R2_KEY_CO_READ_BOOK_PREFIX}/{safe}.json" if safe else ""


def _co_read_upload_meta_key(upload_id: str) -> str:
    safe = _normalize_co_read_key(upload_id)
    return f"{R2_KEY_CO_READ_UPLOAD_PREFIX}/{safe}/meta.json" if safe else ""


def _co_read_upload_chunk_key(upload_id: str, index: int) -> str:
    safe = _normalize_co_read_key(upload_id)
    return f"{R2_KEY_CO_READ_UPLOAD_PREFIX}/{safe}/chunks/{max(0, int(index)):05d}.txt" if safe else ""


def _co_read_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def normalize_co_read_book_mark(mark: Any, source: str = "user") -> Optional[dict]:
    if not isinstance(mark, dict):
        return None
    quote = str(mark.get("quote") or "").strip()[:800]
    note = str(mark.get("note") or "").strip()[:1000]
    du_reply = str(mark.get("du_reply") or "").strip()[:1200]
    if not (quote or note):
        return None
    now = now_beijing_iso()
    char_start = _co_read_int(mark.get("char_start"), -1)
    char_end = _co_read_int(mark.get("char_end"), -1)
    if char_start < 0 or char_end <= char_start:
        char_start = -1
        char_end = -1
    clean_source = "du" if source == "du" or mark.get("source") == "du" else "user"
    return {
        "id": _normalize_co_read_text(mark.get("id"), 80) or str(uuid4()),
        "source": clean_source,
        "quote": quote,
        "note": note,
        "du_reply": du_reply,
        "char_start": char_start,
        "char_end": char_end,
        "created_at": _normalize_co_read_text(mark.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(mark.get("updated_at"), 40) or now,
    }


def _normalize_co_read_marks(items: Any, source: str) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        mark = normalize_co_read_book_mark(item, source=source)
        if not mark:
            continue
        key = str(mark.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(mark)
    return out[:200]


def normalize_co_read_section(section: Any) -> Optional[dict]:
    if not isinstance(section, dict):
        return None
    index = max(1, _co_read_int(section.get("index"), 1))
    char_start = max(0, _co_read_int(section.get("char_start"), 0))
    char_end = max(char_start, _co_read_int(section.get("char_end"), char_start))
    if char_end <= char_start:
        return None
    now = now_beijing_iso()
    status = "done" if str(section.get("status") or "").strip() == "done" else "reading"
    return {
        "section_id": _normalize_co_read_text(section.get("section_id"), 80) or f"sec_{index:04d}",
        "index": index,
        "char_start": char_start,
        "char_end": char_end,
        "status": status,
        "user_marks": _normalize_co_read_marks(section.get("user_marks"), "user"),
        "du_marks": _normalize_co_read_marks(section.get("du_marks"), "du"),
        "user_section_note": str(section.get("user_section_note") or "").strip()[:2000],
        "du_section_note": str(section.get("du_section_note") or "").strip()[:2000],
        "created_at": _normalize_co_read_text(section.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(section.get("updated_at"), 40) or now,
        "completed_at": _normalize_co_read_text(section.get("completed_at"), 40),
    }


def normalize_co_read_book_payload(book: Any) -> dict:
    raw = book if isinstance(book, dict) else {}
    now = now_beijing_iso()
    key = _normalize_co_read_key(raw.get("book_key"))
    title = str(raw.get("book_title") or raw.get("title") or "").strip()[:240]
    content = str(raw.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
    sections: list[dict] = []
    sections_raw = raw.get("sections") if isinstance(raw.get("sections"), list) else []
    for item in sections_raw:
        section = normalize_co_read_section(item)
        if section:
            sections.append(section)
    sections.sort(key=lambda x: int(x.get("index") or 0))
    current_index = _co_read_int(raw.get("current_section_index"), 0)
    if sections:
        current_index = max(0, min(len(sections) - 1, current_index))
    else:
        current_index = 0
    return {
        "book_key": key,
        "book_title": title,
        "content": content,
        "sections": sections,
        "current_section_index": current_index,
        "created_at": _normalize_co_read_text(raw.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(raw.get("updated_at"), 40) or now,
    }


def _co_read_book_summary(book: dict) -> dict:
    clean = normalize_co_read_book_payload(book)
    sections = clean.get("sections") if isinstance(clean.get("sections"), list) else []
    done_count = sum(1 for item in sections if str(item.get("status") or "") == "done")
    return {
        "book_key": clean.get("book_key") or "",
        "book_title": clean.get("book_title") or "",
        "content_chars": len(clean.get("content") or ""),
        "section_count": len(sections),
        "done_count": done_count,
        "current_section_index": clean.get("current_section_index") or 0,
        "created_at": clean.get("created_at") or "",
        "updated_at": clean.get("updated_at") or "",
    }


def get_co_read_book_index_payload() -> dict:
    client = _s3_client()
    if not client:
        return {"books": [], "updated_at": ""}
    data = _read_json(client, R2_KEY_CO_READ_BOOK_INDEX)
    if not isinstance(data, dict):
        return {"books": [], "updated_at": ""}
    books_raw = data.get("books") if isinstance(data.get("books"), list) else []
    books = []
    seen: set[str] = set()
    for item in books_raw:
        if not isinstance(item, dict):
            continue
        key = _normalize_co_read_key(item.get("book_key"))
        if not key or key in seen:
            continue
        seen.add(key)
        books.append(
            {
                "book_key": key,
                "book_title": str(item.get("book_title") or "").strip()[:240],
                "content_chars": max(0, _co_read_int(item.get("content_chars"), 0)),
                "section_count": max(0, _co_read_int(item.get("section_count"), 0)),
                "done_count": max(0, _co_read_int(item.get("done_count"), 0)),
                "current_section_index": max(0, _co_read_int(item.get("current_section_index"), 0)),
                "created_at": _normalize_co_read_text(item.get("created_at"), 40),
                "updated_at": _normalize_co_read_text(item.get("updated_at"), 40),
            }
        )
    books.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return {"books": books, "updated_at": _normalize_co_read_text(data.get("updated_at"), 40)}


def list_co_read_books() -> list[dict]:
    return get_co_read_book_index_payload().get("books") or []


def get_co_read_book(book_key: str) -> Optional[dict]:
    key = _normalize_co_read_key(book_key)
    object_key = _co_read_book_object_key(key)
    if not object_key:
        return None
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, object_key)
    if not isinstance(data, dict):
        return None
    clean = normalize_co_read_book_payload(data)
    return clean if clean.get("book_key") else None


def save_co_read_book(book: dict) -> Optional[dict]:
    clean = normalize_co_read_book_payload(book)
    key = _normalize_co_read_key(clean.get("book_key"))
    if not key:
        return None
    clean["book_key"] = key
    clean["updated_at"] = now_beijing_iso()
    object_key = _co_read_book_object_key(key)
    client = _s3_client()
    if not client or not object_key:
        return None
    with _co_read_book_write_lock:
        try:
            _write_json(client, object_key, clean)
            index_payload = get_co_read_book_index_payload()
            books = [item for item in (index_payload.get("books") or []) if item.get("book_key") != key]
            books.insert(0, _co_read_book_summary(clean))
            _write_json(client, R2_KEY_CO_READ_BOOK_INDEX, {"books": books[:500], "updated_at": now_beijing_iso()})
            return clean
        except Exception as e:
            logger.error("save_co_read_book 失败 key=%s error=%s", key, e, exc_info=True)
            return None


def delete_co_read_book(book_key: str) -> bool:
    key = _normalize_co_read_key(book_key)
    object_key = _co_read_book_object_key(key)
    if not key or not object_key:
        return False
    client = _s3_client()
    if not client:
        return False
    with _co_read_book_write_lock:
        try:
            client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
            index_payload = get_co_read_book_index_payload()
            books = [item for item in (index_payload.get("books") or []) if item.get("book_key") != key]
            _write_json(client, R2_KEY_CO_READ_BOOK_INDEX, {"books": books, "updated_at": now_beijing_iso()})
            return True
        except Exception as e:
            logger.error("delete_co_read_book 失败 key=%s error=%s", key, e, exc_info=True)
            return False


def create_co_read_upload(book_title: str, total_chunks: int, book_key: str = "") -> Optional[dict]:
    title = str(book_title or "").strip()[:240]
    total = max(1, _co_read_int(total_chunks, 1))
    if not title or total > 20000:
        return None
    upload_id = str(uuid4())
    now = now_beijing_iso()
    payload = {
        "upload_id": upload_id,
        "book_key": _normalize_co_read_key(book_key),
        "book_title": title,
        "total_chunks": total,
        "received_chunks": [],
        "content_chars": 0,
        "created_at": now,
        "updated_at": now,
    }
    key = _co_read_upload_meta_key(upload_id)
    client = _s3_client()
    if not client or not key:
        return None
    try:
        _write_json(client, key, payload)
        return payload
    except Exception as e:
        logger.error("create_co_read_upload 失败 upload_id=%s error=%s", upload_id, e, exc_info=True)
        return None


def get_co_read_upload(upload_id: str) -> Optional[dict]:
    key = _co_read_upload_meta_key(upload_id)
    client = _s3_client()
    if not client or not key:
        return None
    data = _read_json(client, key)
    if not isinstance(data, dict):
        return None
    uid = _normalize_co_read_key(data.get("upload_id"))
    if not uid:
        return None
    received = data.get("received_chunks") if isinstance(data.get("received_chunks"), list) else []
    return {
        "upload_id": uid,
        "book_key": _normalize_co_read_key(data.get("book_key")),
        "book_title": str(data.get("book_title") or "").strip()[:240],
        "total_chunks": max(1, _co_read_int(data.get("total_chunks"), 1)),
        "received_chunks": sorted({max(0, _co_read_int(x, 0)) for x in received}),
        "content_chars": max(0, _co_read_int(data.get("content_chars"), 0)),
        "created_at": _normalize_co_read_text(data.get("created_at"), 40),
        "updated_at": _normalize_co_read_text(data.get("updated_at"), 40),
    }


def save_co_read_upload_chunk(upload_id: str, index: int, chunk: str) -> Optional[dict]:
    meta = get_co_read_upload(upload_id)
    if not meta:
        return None
    idx = _co_read_int(index, -1)
    total = int(meta.get("total_chunks") or 0)
    if idx < 0 or idx >= total:
        return None
    text = str(chunk or "")
    client = _s3_client()
    chunk_key = _co_read_upload_chunk_key(upload_id, idx)
    meta_key = _co_read_upload_meta_key(upload_id)
    if not client or not chunk_key or not meta_key:
        return None
    with _co_read_upload_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=chunk_key,
                Body=text.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
            received = set(meta.get("received_chunks") or [])
            received.add(idx)
            meta["received_chunks"] = sorted(received)
            meta["content_chars"] = int(meta.get("content_chars") or 0) + len(text)
            meta["updated_at"] = now_beijing_iso()
            _write_json(client, meta_key, meta)
            return meta
        except Exception as e:
            logger.error("save_co_read_upload_chunk 失败 upload_id=%s index=%s error=%s", upload_id, idx, e, exc_info=True)
            return None


def assemble_co_read_upload(upload_id: str) -> tuple[Optional[dict], str]:
    meta = get_co_read_upload(upload_id)
    if not meta:
        return None, ""
    total = int(meta.get("total_chunks") or 0)
    received = set(meta.get("received_chunks") or [])
    if total <= 0 or any(idx not in received for idx in range(total)):
        return meta, ""
    client = _s3_client()
    if not client:
        return meta, ""
    chunks: list[str] = []
    try:
        for idx in range(total):
            key = _co_read_upload_chunk_key(upload_id, idx)
            resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            chunks.append(resp["Body"].read().decode("utf-8"))
        return meta, "".join(chunks)
    except Exception as e:
        logger.error("assemble_co_read_upload 失败 upload_id=%s error=%s", upload_id, e, exc_info=True)
        return meta, ""


def delete_co_read_upload(upload_id: str) -> bool:
    safe = _normalize_co_read_key(upload_id)
    if not safe:
        return False
    client = _s3_client()
    if not client:
        return False
    prefix = f"{R2_KEY_CO_READ_UPLOAD_PREFIX}/{safe}/"
    try:
        continuation = None
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            resp = client.list_objects_v2(**kwargs)
            objects = [{"Key": item["Key"]} for item in resp.get("Contents", []) if item.get("Key")]
            if objects:
                client.delete_objects(Bucket=R2_BUCKET_NAME, Delete={"Objects": objects, "Quiet": True})
            if not resp.get("IsTruncated"):
                break
            continuation = resp.get("NextContinuationToken")
        return True
    except Exception as e:
        logger.error("delete_co_read_upload 失败 upload_id=%s error=%s", upload_id, e, exc_info=True)
        return False


def _stay_with_du_target_for_kind(kind: str) -> Optional[str]:
    raw_kind = (kind or "").strip().lower().replace("-", "_")
    target_map = {
        "timeline": "timeline",
        "node": "timeline",
        "important_node": "timeline",
        "movie_want": "moviesTodo",
        "movie_todo": "moviesTodo",
        "want_movie": "moviesTodo",
        "movie_done": "moviesDone",
        "watched_movie": "moviesDone",
        "book_want": "booksTodo",
        "book_todo": "booksTodo",
        "want_book": "booksTodo",
        "book_done": "booksDone",
        "read_book": "booksDone",
    }
    return target_map.get(raw_kind)


def add_stay_with_du_entry(kind: str, title: str, note: str = "", date: str = "") -> Optional[dict]:
    """向 Stay with Du 追加一条记录。kind: timeline/movie_want/movie_done/book_want/book_done。"""
    target = _stay_with_du_target_for_kind(kind)
    clean_title = _normalize_stay_text(title, 160)
    if not target or not clean_title:
        return None
    clean_note = _normalize_stay_text(note, 600)
    clean_date = _normalize_stay_text(date, 32)
    if target == "timeline" and not clean_date:
        clean_date = today_beijing()
    if target in {"moviesDone", "booksDone"} and not clean_date:
        clean_date = today_beijing()

    data = get_stay_with_du_data()
    item_id = str(uuid4())
    if target == "timeline":
        entry = {
            "id": item_id,
            "date": clean_date,
            "title": clean_title,
            "desc": clean_note,
        }
    else:
        entry = {
            "id": item_id,
            "title": clean_title,
            "note": clean_note,
        }
        if clean_date:
            entry["date"] = clean_date
    items = data.get(target)
    if not isinstance(items, list):
        items = []
    data[target] = [entry] + items
    ok = save_stay_with_du_data(data)
    return entry if ok else None


def delete_stay_with_du_entry(kind: str, entry_id: str = "", title: str = "", date: str = "") -> Optional[dict]:
    """删除 Stay with Du 一条记录。优先按 id；没有 id 时按 title 精确匹配，可用 date 缩小范围。"""
    target = _stay_with_du_target_for_kind(kind)
    if not target:
        return None
    clean_id = _normalize_stay_text(entry_id, 80)
    clean_title = _normalize_stay_text(title, 160)
    clean_date = _normalize_stay_text(date, 32)
    if not clean_id and not clean_title:
        return None

    data = get_stay_with_du_data()
    items = data.get(target)
    if not isinstance(items, list) or not items:
        return None

    delete_index = -1
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if clean_id:
            if str(item.get("id") or "").strip() == clean_id:
                delete_index = idx
                break
            continue
        item_title = str(item.get("title") or "").strip()
        item_date = str(item.get("date") or "").strip()
        if item_title == clean_title and (not clean_date or item_date == clean_date):
            delete_index = idx
            break
    if delete_index < 0:
        return None

    deleted = dict(items[delete_index])
    data[target] = items[:delete_index] + items[delete_index + 1:]
    ok = save_stay_with_du_data(data)
    return deleted if ok else None


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
    wid = normalize_window_id(window_id)
    try:
        data = _read_conversation_data_with_legacy_migrate(window_id)
        rounds = (data or {}).get("rounds") if isinstance(data, dict) else None
        if isinstance(rounds, list):
            return len(rounds)
    except Exception as e:
        logger.warning("get_window_conversation_rounds 失败 window_id=%s error=%s", wid, e)
    return 0


# ---------- 一键清空（测试/重置用） ----------


# ---------- 文游（跑团）：active 局、最近一次归档快照（供 MiniApp 拉取） ----------


def wenyou_active_session_key(user_id: int) -> str:
    return f"wenyou/active/{int(user_id)}/session.json"


def wenyou_last_archive_key(user_id: int) -> str:
    return f"wenyou/last_archive/{int(user_id)}.json"


def get_wenyou_session(user_id: int) -> Optional[Any]:
    """读取进行中的文游局；无则 None。"""
    client = _s3_client()
    if not client:
        return None
    return _read_json(client, wenyou_active_session_key(user_id))


def save_wenyou_session(user_id: int, data: Any) -> bool:
    """保存文游 session 到 R2。"""
    client = _s3_client()
    if not client:
        logger.warning("R2 未配置，跳过 save_wenyou_session user_id=%s", user_id)
        return False
    try:
        _write_json(client, wenyou_active_session_key(user_id), data)
        return True
    except Exception as e:
        logger.error("save_wenyou_session 失败 user_id=%s error=%s", user_id, e, exc_info=True)
        return False


def delete_wenyou_active_session(user_id: int) -> bool:
    """删除进行中的文游 session 文件。"""
    client = _s3_client()
    if not client:
        return False
    key = wenyou_active_session_key(user_id)
    try:
        client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except Exception as e:
        logger.warning("delete_wenyou_active_session 失败 key=%s error=%s", key, e)
        return False


def save_wenyou_archive_copy(user_id: int, game_id: str, data: Any) -> bool:
    """归档一局到 wenyou/archive/{user_id}/{game_id}.json。"""
    client = _s3_client()
    if not client:
        return False
    safe_gid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (game_id or ""))[:80]
    key = f"wenyou/archive/{int(user_id)}/{safe_gid or 'unknown'}.json"
    try:
        _write_json(client, key, data)
        return True
    except Exception as e:
        logger.error("save_wenyou_archive_copy 失败 key=%s error=%s", key, e, exc_info=True)
        return False


def save_wenyou_last_archive(user_id: int, data: Any) -> bool:
    """保存「最近一次结束局」快照，供 MiniApp 只拉一次。"""
    client = _s3_client()
    if not client:
        return False
    try:
        _write_json(client, wenyou_last_archive_key(user_id), data)
        return True
    except Exception as e:
        logger.error("save_wenyou_last_archive 失败 user_id=%s error=%s", user_id, e, exc_info=True)
        return False


def get_wenyou_last_archive(user_id: int) -> Optional[Any]:
    """读取最近一次结束局的快照。"""
    client = _s3_client()
    if not client:
        return None
    return _read_json(client, wenyou_last_archive_key(user_id))


def list_wenyou_archives(user_id: int, limit: int = 20) -> list[dict]:
    """按结束时间倒序返回文游归档列表（含基础摘要）。"""
    client = _s3_client()
    if not client:
        return []
    lim = max(1, min(100, int(limit or 20)))
    prefix = f"wenyou/archive/{int(user_id)}/"
    objs: list[dict] = []
    token = None
    try:
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in (resp.get("Contents") or []):
                key = str(obj.get("Key") or "")
                if key.endswith(".json"):
                    objs.append(
                        {
                            "key": key,
                            "last_modified": obj.get("LastModified"),
                        }
                    )
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
    except Exception as e:
        logger.warning("list_wenyou_archives 列 key 失败 user_id=%s error=%s", user_id, e)
        return []

    # 优先按对象更新时间倒序，随后再按归档 endedAt 二次排序
    objs.sort(key=lambda x: str(x.get("last_modified") or ""), reverse=True)
    out: list[dict] = []
    for row in objs[: max(lim * 3, lim)]:
        key = row.get("key") or ""
        if not key:
            continue
        data = _read_json(client, key)
        if not isinstance(data, dict):
            continue
        fw = data.get("framework") if isinstance(data.get("framework"), dict) else {}
        st = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        p1 = st.get("player1") if isinstance(st.get("player1"), dict) else {}
        p2 = st.get("player2") if isinstance(st.get("player2"), dict) else {}
        out.append(
            {
                "key": key,
                "gameId": str(data.get("gameId") or ""),
                "endedAt": str(data.get("endedAt") or ""),
                "instance_code": str(fw.get("instance_code") or ""),
                "instance_name": str(fw.get("instance_name") or ""),
                "instance_genre": str(fw.get("instance_genre") or ""),
                "difficulty": str(fw.get("difficulty") or ""),
                "points": int(st.get("points") or 0),
                "player1_name": str(fw.get("player1_name") or "玩家一"),
                "player2_name": str(fw.get("player2_name") or "渡"),
                "player1_level": int(p1.get("level") or 1),
                "player2_level": int(p2.get("level") or 1),
                "history_count": len(data.get("history") or []) if isinstance(data.get("history"), list) else 0,
            }
        )
        if len(out) >= lim:
            break
    out.sort(key=lambda x: str(x.get("endedAt") or ""), reverse=True)
    return out[:lim]


def get_wenyou_archive_by_game_id(user_id: int, game_id: str) -> Optional[Any]:
    """按 game_id 读取单局归档。"""
    client = _s3_client()
    if not client:
        return None
    safe_gid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (game_id or ""))[:80]
    if not safe_gid:
        return None
    key = f"wenyou/archive/{int(user_id)}/{safe_gid}.json"
    return _read_json(client, key)


# ---------- 表情包 stickers/（映射表 + 按标签目录存图） ----------


def get_object_bytes(key: str) -> tuple[Optional[bytes], str]:
    """读取任意对象字节，用于 Telegram sendPhoto 无公网 URL 时回退。"""
    k = (key or "").strip()
    if not k:
        return None, ""
    client = _s3_client()
    if not client:
        return None, ""
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=k)
        body = resp["Body"].read()
        ctype = (resp.get("ContentType") or "application/octet-stream").strip()
        return body, ctype
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None, ""
        logger.error("get_object_bytes 失败 key=%s error=%s", k, e, exc_info=True)
        return None, ""
    except Exception as e:
        logger.error("get_object_bytes 失败 key=%s error=%s", k, e, exc_info=True)
        return None, ""


def _sticker_reserved_keys() -> frozenset:
    return frozenset({R2_KEY_STICKERS_MAPPING, R2_KEY_STICKERS_META, "stickers/mapping.json", "stickers/meta.json"})


def _merge_default_sticker_meta(raw: dict) -> dict:
    """默认 8 类 + 用户新增；网关仅英文代号；同名以存储中的 label 为准。"""
    from services.sticker_tags import DEFAULT_STICKER_TAG_ROWS, validate_sticker_tag_key

    by_key: dict[str, dict] = {r["key"]: dict(r) for r in DEFAULT_STICKER_TAG_ROWS}
    incoming = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    for it in incoming:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "").strip().lower()
        if not k or not validate_sticker_tag_key(k):
            continue
        label = str(it.get("label_zh") or it.get("label") or "").strip() or k
        if k in by_key:
            by_key[k]["label_zh"] = label
        else:
            by_key[k] = {"key": k, "label_zh": label}
    order = [r["key"] for r in DEFAULT_STICKER_TAG_ROWS]
    default_set = set(order)
    extras = sorted(k for k in by_key if k not in default_set)
    rows = [by_key[k] for k in order if k in by_key]
    rows.extend(by_key[k] for k in extras)
    return {"tags": rows, "updated_at": str(raw.get("updated_at") or "")}


def get_stickers_meta() -> dict:
    """读取 stickers/meta.json；不存在则写入默认（含中文名）。"""
    from services.sticker_tags import DEFAULT_STICKER_TAG_ROWS

    client = _s3_client()
    if not client:
        return {"tags": list(DEFAULT_STICKER_TAG_ROWS), "updated_at": ""}
    data = _read_json(client, R2_KEY_STICKERS_META)
    if not isinstance(data, dict) or not isinstance(data.get("tags"), list):
        payload = {"tags": list(DEFAULT_STICKER_TAG_ROWS), "updated_at": now_beijing_iso()}
        with _global_write_lock:
            try:
                _write_json(client, R2_KEY_STICKERS_META, payload)
            except Exception:
                pass
        return payload
    return _merge_default_sticker_meta(data)


def save_stickers_meta(payload: dict) -> bool:
    """保存 MiniApp 编辑后的分类元数据。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(payload, dict):
        return False
    p = dict(payload)
    p["updated_at"] = now_beijing_iso()
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_STICKERS_META, p)
            return True
        except Exception as e:
            logger.error("save_stickers_meta 失败 error=%s", e, exc_info=True)
            return False


def get_sticker_tag_keys() -> set[str]:
    """所有合法英文代号（小写，meta ∪ 映射表；非法键名忽略）。"""
    from services.sticker_tags import validate_sticker_tag_key

    keys: set[str] = set()
    meta = get_stickers_meta()
    for it in meta.get("tags") or []:
        if isinstance(it, dict) and it.get("key"):
            k = str(it["key"]).strip().lower()
            if validate_sticker_tag_key(k):
                keys.add(k)
    client = _s3_client()
    if client:
        m = _read_json(client, R2_KEY_STICKERS_MAPPING)
        if isinstance(m, dict):
            for k in m:
                if k != "updated_at" and isinstance(k, str) and k.strip():
                    kk = k.strip().lower()
                    if validate_sticker_tag_key(kk):
                        keys.add(kk)
    return keys


def add_sticker_category(key: str, label_zh: str = "") -> tuple[bool, str]:
    """新增分类：英文代号必填；label_zh 为 MiniApp 展示名（可选，默认同代号）。"""
    from services.sticker_tags import validate_sticker_tag_key

    key = (key or "").strip().lower()
    if not key:
        return False, "英文代号不能为空"
    if not validate_sticker_tag_key(key):
        return False, "代号须为小写英文：字母开头，仅 a-z、0-9、下划线"
    label = (label_zh or "").strip() or key
    meta = get_stickers_meta()
    tags = [t for t in (meta.get("tags") or []) if isinstance(t, dict)]
    for t in tags:
        if str(t.get("key") or "").strip().lower() == key:
            return False, "该代号已存在"
    tags.append({"key": key, "label_zh": label})
    meta["tags"] = tags
    ok = save_stickers_meta(meta)
    return (True, "") if ok else (False, "保存失败")


def rebuild_stickers_mapping_from_r2() -> dict[str, list[str]]:
    """扫描 stickers/ 下各标签目录，生成 { 代号: [对象key,...] }。"""

    client = _s3_client()
    out: dict[str, list[str]] = {}
    if not client:
        return out
    reserved = _sticker_reserved_keys()
    token = None
    try:
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": "stickers/", "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents") or []:
                key = str(obj.get("Key") or "")
                if not key or key.endswith("/"):
                    continue
                if key in reserved or key.endswith("mapping.json") or key.endswith("meta.json"):
                    continue
                parts = key.split("/")
                if len(parts) < 3:
                    continue
                tag = parts[1].strip().lower()
                if not tag:
                    continue
                out.setdefault(tag, []).append(key)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
    except Exception as e:
        logger.warning("rebuild_stickers_mapping_from_r2 列对象失败 error=%s", e)
    for t in list(out.keys()):
        out[t] = sorted(set(out[t]))
    return out


def save_stickers_mapping(mapping: dict[str, list[str]]) -> bool:
    """写入 stickers/mapping.json；mapping 为 代号 -> 对象 key 列表（任意数量键）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(mapping, dict):
        return False
    payload: dict[str, Any] = {"updated_at": now_beijing_iso()}
    for t, arr in mapping.items():
        if t == "updated_at":
            continue
        if isinstance(arr, list):
            payload[str(t)] = [str(x).strip() for x in arr if str(x).strip()]
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_STICKERS_MAPPING, payload)
            return True
        except Exception as e:
            logger.error("save_stickers_mapping 失败 error=%s", e, exc_info=True)
            return False


def get_stickers_mapping() -> dict[str, Any]:
    """读取映射表；不存在或损坏时尝试重建。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_STICKERS_MAPPING)
    if not isinstance(data, dict):
        m = rebuild_stickers_mapping_from_r2()
        save_stickers_mapping(m)
        data = _read_json(client, R2_KEY_STICKERS_MAPPING)
    return data if isinstance(data, dict) else {}


def upload_sticker_file(tag: str, filename: str, content: bytes, content_type: str) -> Optional[str]:
    """上传一张表情包到 stickers/{代号}/，并重建映射。"""
    from services.sticker_tags import validate_sticker_tag_key

    t = (tag or "").strip().lower()
    if not t or not validate_sticker_tag_key(t):
        return None
    allowed = get_sticker_tag_keys()
    if t not in allowed:
        return None
    if not content:
        return None
    ext = Path(filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    ctype = (content_type or "").strip().lower() or "image/jpeg"
    if "jpeg" in ctype or "jpg" in ctype:
        ctype = "image/jpeg"
    elif "png" in ctype:
        ctype = "image/png"
    elif "webp" in ctype:
        ctype = "image/webp"
    elif "gif" in ctype:
        ctype = "image/gif"
    else:
        ctype = "image/jpeg"
    safe = f"{uuid4().hex}{ext}"
    key = f"stickers/{t}/{safe}"
    client = _s3_client()
    if not client:
        return None
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=ctype,
        )
        m = rebuild_stickers_mapping_from_r2()
        save_stickers_mapping(m)
        logger.info("sticker 已上传 key=%s", key)
        return key
    except Exception as e:
        logger.error("upload_sticker_file 失败 error=%s", e, exc_info=True)
        return None


def save_device_screenshot(content: bytes, content_type: str, meta: dict | None = None) -> Optional[dict]:
    """保存一次经用户同意的手机截图，并为临时读取生成 token。"""
    if not content:
        return None
    src = meta if isinstance(meta, dict) else {}
    ctype = (content_type or "").strip().lower() or "image/jpeg"
    if "png" in ctype:
        ctype = "image/png"
        ext = ".png"
    else:
        ctype = "image/jpeg"
        ext = ".jpg"
    token = uuid4().hex
    device_id = str(src.get("deviceId") or "").strip()
    safe_device = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in device_id)[:80] or "default"
    key = f"device_screenshots/latest/{safe_device}{ext}"
    meta_key = f"{key}.json"
    meta_payload = {
        "key": key,
        "contentType": ctype,
        "accessToken": token,
        "createdAt": now_beijing_iso(),
        "deviceId": device_id,
        "requestId": str(src.get("requestId") or "").strip(),
        "capturedAt": str(src.get("capturedAt") or "").strip(),
        "width": int(src.get("width") or 0),
        "height": int(src.get("height") or 0),
    }
    client = _s3_client()
    if not client:
        return None
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=ctype,
        )
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=meta_key,
            Body=json.dumps(meta_payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
        return {**meta_payload, "metaKey": meta_key}
    except Exception as e:
        logger.error("save_device_screenshot 失败 error=%s", e, exc_info=True)
        return None


def get_device_screenshot(key: str, token: str) -> tuple[Optional[bytes], str]:
    k = str(key or "").strip()
    tok = str(token or "").strip()
    if not k.startswith("device_screenshots/") or ".." in k or not tok:
        return None, ""
    client = _s3_client()
    if not client:
        return None, ""
    try:
        meta = _read_json(client, f"{k}.json")
        if not isinstance(meta, dict) or str(meta.get("accessToken") or "") != tok:
            return None, ""
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=k)
        data = resp["Body"].read()
        ctype = (resp.get("ContentType") or meta.get("contentType") or "image/jpeg").strip()
        return data, ctype
    except Exception as e:
        logger.error("get_device_screenshot 失败 key=%s error=%s", k, e, exc_info=True)
        return None, ""


def delete_sticker_object(key: str) -> bool:
    """删除指定 sticker 对象并重建映射。"""
    k = (key or "").strip()
    if not k.startswith("stickers/") or ".." in k or k in _sticker_reserved_keys():
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        client.delete_object(Bucket=R2_BUCKET_NAME, Key=k)
        m = rebuild_stickers_mapping_from_r2()
        save_stickers_mapping(m)
        logger.info("sticker 已删除 key=%s", k)
        return True
    except Exception as e:
        logger.error("delete_sticker_object 失败 key=%s error=%s", k, e, exc_info=True)
        return False


# 网关在 R2 里使用的所有前缀，清空时只删这些，不动桶里其他 key
_R2_WIPE_PREFIXES = (
    "windows/",
    "conversations/",
    "global/",
    "dynamic_memory/",
    "core_cache/",
    "notebook/",
    "docs/",
    "wenyou/",
    "sense/",
    "stickers/",
    "device_screenshots/",
)


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
