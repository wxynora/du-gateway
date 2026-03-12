# 核心缓存与 Notion 剪切/粘贴：sync_to 清空 R2 并推到 Notion，sync_from 从 Notion 读回并追加到 R2
# Notion 里列名与下面一致即可直接匹配；可只建部分列，只同步存在的字段。
from typing import Any, Optional

from config import NOTION_CORE_CACHE_DATABASE_ID
from storage import r2_store
from services import notion_client
from utils.log import get_logger

logger = get_logger(__name__)

# 核心缓存 pending 一条的字段（与 R2 / Notion 列名一致即可匹配）
# 列名           Notion 属性类型   说明
# id             Title            唯一标识（imp_xxx_1 或记忆 id）
# content        Text (Rich text) 内容（当轮原文或融合版）
# promoted_by    Select           "importance" | "mention_count"
# importance     Number           1–4
# mention_count  Number
# promoted_at    Date             北京时间 ISO
# tag            Select           卧室 | 客厅 | 书房 | 图书馆
CORE_CACHE_FIELD_NAMES = ("id", "content", "promoted_by", "importance", "mention_count", "promoted_at", "tag")

def _get_property_ids() -> tuple[Optional[dict], Optional[str]]:
    """返回 name -> property_id 映射，失败返回 (None, error)。"""
    data, err = notion_client.read_database(NOTION_CORE_CACHE_DATABASE_ID)
    if err or not data:
        return None, (err or "read_database 为空")
    name_to_id = {}
    for pid, prop in (data.get("properties") or {}).items():
        name = (prop.get("name") or "").strip()
        if name:
            name_to_id[name] = pid
    return name_to_id, None


def _prop_title(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": (value or "")[:2000]}}]}


def _prop_rich_text(value: str) -> dict:
    if not value:
        return {"rich_text": []}
    # Notion 单段约 2000 字，长文拆多段
    chunks = []
    while value:
        chunks.append({"type": "text", "text": {"content": value[:2000]}})
        value = value[2000:]
    return {"rich_text": chunks}


def _prop_select(value: str) -> dict:
    return {"select": {"name": (value or "").strip() or "importance"}}


def _prop_number(value: Optional[int]) -> dict:
    return {"number": value if value is not None else 0}


def _prop_date(iso_str: Optional[str]) -> dict:
    if not iso_str:
        return {"date": None}
    return {"date": {"start": iso_str}}


def _page_properties_for_pending(item: dict, name_to_id: dict) -> dict:
    """只对 Notion schema 里存在的列写入，列名一致即匹配。"""
    out = {}
    if "id" in name_to_id:
        out[name_to_id["id"]] = _prop_title(item.get("id") or "")
    if "content" in name_to_id:
        out[name_to_id["content"]] = _prop_rich_text(item.get("content") or "")
    if "promoted_by" in name_to_id:
        out[name_to_id["promoted_by"]] = _prop_select(item.get("promoted_by") or "importance")
    if "importance" in name_to_id:
        out[name_to_id["importance"]] = _prop_number(item.get("importance"))
    if "mention_count" in name_to_id:
        out[name_to_id["mention_count"]] = _prop_number(item.get("mention_count"))
    if "promoted_at" in name_to_id:
        out[name_to_id["promoted_at"]] = _prop_date(item.get("promoted_at"))
    if "tag" in name_to_id:
        out[name_to_id["tag"]] = _prop_select(item.get("tag") or "")
    return out


def _extract_prop(page: dict, prop_id: str, kind: str) -> Any:
    """从 Notion 页面 properties 里按 property id 取出值。"""
    props = page.get("properties") or {}
    p = props.get(prop_id)
    if not p:
        return None
    if kind == "title":
        arr = p.get("title") or []
        return " ".join(t.get("plain_text", "") for t in arr).strip()
    if kind == "rich_text":
        arr = p.get("rich_text") or []
        return " ".join(t.get("plain_text", "") for t in arr).strip()
    if kind == "select":
        s = p.get("select")
        return s.get("name") if s else None
    if kind == "number":
        return p.get("number")
    if kind == "date":
        d = p.get("date")
        return d.get("start") if d else None
    return None


def sync_to_notion() -> tuple[bool, str]:
    """
    剪切：把当前 R2 pending 全量推到 Notion，然后清空 R2 pending。
    已存在同 id（标题）的页面则更新，否则创建；完成后 R2 pending 必为空。
    返回 (成功与否, 错误信息)。
    """
    if not NOTION_CORE_CACHE_DATABASE_ID:
        return False, "NOTION_CORE_CACHE_DATABASE_ID 未配置"
    name_to_id, err = _get_property_ids()
    if err or not name_to_id:
        return False, f"读取 Notion 数据库 schema 失败: {err or '无 properties'}"

    pending = r2_store.get_core_cache_pending()
    if not pending:
        r2_store.save_core_cache_pending([])  # 确保清空
        logger.info("sync_to_notion: pending 已空，仅清空 R2")
        return True, ""

    pid_title = name_to_id.get("id")  # 用于匹配「已存在」的页面，没有 id 列则全部当新建
    # 拉取已存在页面：分页查全库，建立 id(title) -> page_id
    existing = {}
    cursor = None
    while True:
        data, err = notion_client.query_database(NOTION_CORE_CACHE_DATABASE_ID, start_cursor=cursor)
        if err:
            return False, f"查询 Notion 失败: {err}"
        for page in (data or {}).get("results") or []:
            page_id = page.get("id")
            title = _extract_prop(page, pid_title, "title") if pid_title else None
            if title:
                existing[title] = page_id
        cursor = (data or {}).get("next_cursor")
        if not cursor or not (data or {}).get("has_more"):
            break

    parent = {"database_id": NOTION_CORE_CACHE_DATABASE_ID}
    for item in pending:
        entry_id = (item.get("id") or "").strip()
        if not entry_id:
            continue
        props = _page_properties_for_pending(item, name_to_id)
        if entry_id in existing:
            page_id = existing[entry_id]
            _, err = notion_client.update_page(page_id, props)
            if err:
                logger.warning("sync_to_notion 更新页面失败 id=%s err=%s", entry_id, err)
        else:
            _, err = notion_client.create_page(parent, props)
            if err:
                logger.warning("sync_to_notion 创建页面失败 id=%s err=%s", entry_id, err)
            else:
                existing[entry_id] = None

    r2_store.save_core_cache_pending([])  # 剪切：推完即清空 R2
    logger.info("sync_to_notion 完成 已推条数=%s，R2 pending 已清空", len(pending))
    return True, ""


def sync_from_notion() -> tuple[bool, str]:
    """
    粘贴：从 Notion 读回当前所有条目，追加到 R2 pending（不覆盖）。
    返回 (成功与否, 错误信息)。
    """
    if not NOTION_CORE_CACHE_DATABASE_ID:
        return False, "NOTION_CORE_CACHE_DATABASE_ID 未配置"
    name_to_id, err = _get_property_ids()
    if err or not name_to_id:
        return False, f"读取 Notion 数据库 schema 失败: {err or '无 properties'}"

    # 只读 Notion 里存在的列，列名一致即匹配；缺列用默认值
    kid = name_to_id.get("id")
    kcontent = name_to_id.get("content")
    kpromoted_by = name_to_id.get("promoted_by")
    kimportance = name_to_id.get("importance")
    kmention_count = name_to_id.get("mention_count")
    kpromoted_at = name_to_id.get("promoted_at")
    ktag = name_to_id.get("tag")

    pending = []
    cursor = None
    while True:
        data, err = notion_client.query_database(NOTION_CORE_CACHE_DATABASE_ID, start_cursor=cursor)
        if err:
            return False, f"查询 Notion 失败: {err}"
        for page in (data or {}).get("results") or []:
            entry_id = _extract_prop(page, kid, "title") if kid else None
            if not entry_id:
                continue
            content = _extract_prop(page, kcontent, "rich_text") if kcontent else ""
            promoted_by = _extract_prop(page, kpromoted_by, "select") if kpromoted_by else "importance"
            importance = _extract_prop(page, kimportance, "number") if kimportance else 0
            mention_count = _extract_prop(page, kmention_count, "number") if kmention_count else 0
            promoted_at = _extract_prop(page, kpromoted_at, "date") if kpromoted_at else ""
            tag = _extract_prop(page, ktag, "select") if ktag else ""
            pending.append({
                "id": entry_id,
                "content": content or "",
                "promoted_by": promoted_by or "importance",
                "importance": importance if importance is not None else 0,
                "mention_count": mention_count if mention_count is not None else 0,
                "promoted_at": promoted_at or "",
                "tag": tag or "",
            })
        cursor = (data or {}).get("next_cursor")
        if not cursor or not (data or {}).get("has_more"):
            break

    current = r2_store.get_core_cache_pending()
    new_pending = current + pending
    if not r2_store.save_core_cache_pending(new_pending):
        return False, "写回 R2 pending 失败"
    logger.info("sync_from_notion 完成 从 Notion 读回条数=%s，追加后 R2 总条数=%s", len(pending), len(new_pending))
    return True, ""
