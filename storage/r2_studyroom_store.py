"""StudyRoom normalization and R2 persistence."""

from __future__ import annotations

import threading
from typing import Any, Optional
from uuid import uuid4

from config import R2_BUCKET_NAME
from storage.r2_client import _read_json, _s3_client, _write_json
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

R2_KEY_STUDYROOM = "global/studyroom.json"
_global_write_lock = threading.Lock()

_STUDYROOM_MODULES = [
    {"id": "inbox", "label": "待整理"},
    {"id": "current_affairs", "label": "时政"},
    {"id": "party", "label": "党建"},
    {"id": "rural", "label": "乡村振兴"},
    {"id": "governance", "label": "基层治理"},
    {"id": "village_affairs", "label": "村务管理"},
    {"id": "law", "label": "法律法规"},
    {"id": "philosophy", "label": "哲学"},
    {"id": "economy", "label": "经济"},
    {"id": "writing", "label": "公文写作"},
    {"id": "computer", "label": "计算机"},
    {"id": "local", "label": "安徽/铜陵/枞阳"},
    {"id": "wrong_questions", "label": "错题"},
]
_STUDYROOM_SOURCE_TYPES = {"bilibili", "web", "pdf", "question_bank", "word", "text", "screenshot", "fenbi", "note", "wrong_question"}
_STUDYROOM_STATUSES = {"todo", "sorting", "done"}
_STUDYROOM_MODULE_IDS = {m["id"] for m in _STUDYROOM_MODULES}
_STUDYROOM_MODULE_KEYWORDS = [
    ("wrong_questions", ("错题", "错因", "错选", "答案解析", "正确答案", "题干", "选项", "真题", "模拟题", "刷题", "本题")),
    ("local", ("安徽", "铜陵", "枞阳", "枞阳县", "铜陵市", "安庆", "池州", "长江经济带")),
    ("writing", ("公文", "通知", "请示", "报告", "函", "纪要", "简报", "材料写作", "应用文", "标题", "主送机关", "落款")),
    ("philosophy", ("哲学", "马克思主义哲学", "唯物主义", "唯心主义", "辩证法", "认识论", "历史观", "矛盾", "实践", "意识")),
    ("economy", ("经济", "市场经济", "宏观调控", "微观经济", "财政", "货币", "供给", "需求", "价格", "通货膨胀")),
    ("computer", ("计算机", "office", "word", "excel", "wps", "信息技术", "网络安全", "文件管理", "快捷键", "数据库")),
    ("law", ("法律", "法规", "宪法", "民法典", "行政法", "村民委员会组织法", "条例", "法治", "依法", "权利义务")),
    ("party", ("党建", "党员", "党支部", "党组织", "党章", "党纪", "党课", "三会一课", "组织生活", "主题党日")),
    ("rural", ("乡村振兴", "三农", "农业", "农村", "农民", "产业振兴", "耕地", "宅基地", "集体经济", "人居环境")),
    ("governance", ("基层治理", "网格", "矛盾纠纷", "调解", "信访", "综治", "公共服务", "群众工作", "应急管理")),
    ("village_affairs", ("村务", "村委会", "村干部", "村民代表", "村民会议", "民主决策", "财务公开", "四议两公开")),
    ("current_affairs", ("时政", "中央", "国务院", "政府工作报告", "两会", "二十大", "全会", "政策", "会议精神", "热点")),
]


def _trim_study_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def guess_studyroom_module_id(title: Any = "", content: Any = "", url: Any = "", source_type: Any = "") -> str:
    """根据资料文本做轻量关键词归类；不确定时保持 inbox。"""
    source = _trim_study_text(source_type, 32)
    if source in {"fenbi", "wrong_question"}:
        return "wrong_questions"
    text = "\n".join(
        [
            _trim_study_text(title, 300),
            _trim_study_text(content, 5000),
            _trim_study_text(url, 500),
            source,
        ]
    ).lower()
    if not text.strip():
        return "inbox"
    best_module = "inbox"
    best_score = 0
    for module_id, keywords in _STUDYROOM_MODULE_KEYWORDS:
        score = 0
        for keyword in keywords:
            if keyword.lower() in text:
                score += 2 if len(keyword) >= 3 else 1
        if score > best_score:
            best_module = module_id
            best_score = score
    return best_module if best_score >= 2 else "inbox"


def _normalize_studyroom_item(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    title = _trim_study_text(raw.get("title"), 120)
    content = _trim_study_text(raw.get("content"), 20000)
    url = _trim_study_text(raw.get("url"), 1000)
    if not title and not content and not url:
        return None
    module_id = _trim_study_text(raw.get("module_id"), 64) or "inbox"
    if module_id not in _STUDYROOM_MODULE_IDS:
        module_id = "inbox"
    source_type = _trim_study_text(raw.get("source_type"), 32) or "note"
    if source_type not in _STUDYROOM_SOURCE_TYPES:
        source_type = "note"
    status = _trim_study_text(raw.get("status"), 32) or "todo"
    if status not in _STUDYROOM_STATUSES:
        status = "todo"
    now = now_beijing_iso()
    created_at = _trim_study_text(raw.get("created_at"), 64) or now
    updated_at = _trim_study_text(raw.get("updated_at"), 64) or created_at
    return {
        "id": _trim_study_text(raw.get("id"), 80) or str(uuid4()),
        "title": title or "未命名资料",
        "content": content,
        "url": url,
        "module_id": module_id,
        "source_type": source_type,
        "status": status,
        "note": _trim_study_text(raw.get("note"), 16000),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _normalize_studyroom_log(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    content = _trim_study_text(raw.get("content"), 8000)
    if not content:
        return None
    now = now_beijing_iso()
    created_at = _trim_study_text(raw.get("created_at"), 64) or now
    return {
        "id": _trim_study_text(raw.get("id"), 80) or str(uuid4()),
        "content": content,
        "created_at": created_at,
    }


def normalize_studyroom_data(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    items = [_normalize_studyroom_item(x) for x in data.get("items", []) if isinstance(x, dict)]
    logs = [_normalize_studyroom_log(x) for x in data.get("study_logs", []) if isinstance(x, dict)]
    now = now_beijing_iso()
    return {
        "profile": {
            "target_name": _trim_study_text(profile.get("target_name") or profile.get("exam_name"), 120)
            or "安徽省铜陵市枞阳县村级后备干部考试",
            "expected_month": _trim_study_text(profile.get("expected_month"), 40) or "2026年7月左右",
            "goal": _trim_study_text(profile.get("goal"), 200) or "先把资料收齐，按模块整理成能理解、能背、能练、能复盘的学习库。",
        },
        "modules": list(_STUDYROOM_MODULES),
        "items": sorted([x for x in items if x], key=lambda x: str(x.get("updated_at") or ""), reverse=True)[:300],
        "study_logs": sorted([x for x in logs if x], key=lambda x: str(x.get("created_at") or ""), reverse=True)[:120],
        "updated_at": _trim_study_text(data.get("updated_at"), 64) or now,
    }


def get_studyroom_data() -> dict:
    """读取 StudyRoom 数据。"""
    client = _s3_client()
    if not client:
        return normalize_studyroom_data({})
    data = _read_json(client, R2_KEY_STUDYROOM)
    return normalize_studyroom_data(data)


def save_studyroom_data(data: dict) -> bool:
    """覆盖保存 StudyRoom 数据。"""
    client = _s3_client()
    if not client:
        return False
    payload = normalize_studyroom_data(data)
    payload["updated_at"] = now_beijing_iso()
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_STUDYROOM, payload)
            return True
        except Exception as e:
            logger.error("save_studyroom_data 失败 error=%s", e, exc_info=True)
            return False


def add_studyroom_item(item: dict) -> Optional[dict]:
    data = get_studyroom_data()
    now = now_beijing_iso()
    normalized = _normalize_studyroom_item({**(item or {}), "created_at": now, "updated_at": now})
    if not normalized:
        return None
    data["items"] = [normalized, *(data.get("items") or [])]
    return normalized if save_studyroom_data(data) else None


def update_studyroom_item(item_id: str, patch: dict) -> Optional[dict]:
    eid = _trim_study_text(item_id, 80)
    if not eid:
        return None
    data = get_studyroom_data()
    now = now_beijing_iso()
    updated = None
    next_items = []
    for item in data.get("items") or []:
        if str(item.get("id") or "") == eid:
            merged = {**item, **(patch or {}), "id": eid, "created_at": item.get("created_at"), "updated_at": now}
            normalized = _normalize_studyroom_item(merged)
            if not normalized:
                return None
            updated = normalized
            next_items.append(normalized)
        else:
            next_items.append(item)
    if not updated:
        return None
    data["items"] = next_items
    return updated if save_studyroom_data(data) else None


def delete_studyroom_item(item_id: str) -> bool:
    eid = _trim_study_text(item_id, 80)
    if not eid:
        return False
    data = get_studyroom_data()
    items = data.get("items") or []
    next_items = [x for x in items if str(x.get("id") or "") != eid]
    if len(next_items) == len(items):
        return False
    data["items"] = next_items
    return save_studyroom_data(data)


def add_studyroom_log(content: str) -> Optional[dict]:
    text = _trim_study_text(content, 8000)
    if not text:
        return None
    data = get_studyroom_data()
    entry = {"id": str(uuid4()), "content": text, "created_at": now_beijing_iso()}
    data["study_logs"] = [entry, *(data.get("study_logs") or [])]
    return entry if save_studyroom_data(data) else None
