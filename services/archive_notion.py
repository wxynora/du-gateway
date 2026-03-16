# 归档写入 Notion：支持「一个数据库多分类」或「四张表」；字段与动态层一致（id, content, importance, mention_count, promoted_at；分类用 分类 或 tag）
# 时间写入为人可读格式（如 2026年03月07日 14:41），对应列需为「文本」类型
from typing import Optional

from config import (
    NOTION_ARCHIVE_DATABASE_ID,
    NOTION_ARCHIVE_DATABASE_ID_书房,
    NOTION_ARCHIVE_DATABASE_ID_客厅,
    NOTION_ARCHIVE_DATABASE_ID_图书馆,
    NOTION_ARCHIVE_DATABASE_ID_卧室,
)
from services import notion_client
from utils.log import get_logger
from utils.time_aware import iso_to_display_time

logger = get_logger(__name__)

_ARCHIVE_DB_BY_TAG = {
    "书房": NOTION_ARCHIVE_DATABASE_ID_书房,
    "客厅": NOTION_ARCHIVE_DATABASE_ID_客厅,
    "图书馆": NOTION_ARCHIVE_DATABASE_ID_图书馆,
    "卧室": NOTION_ARCHIVE_DATABASE_ID_卧室,
}

# 单库多分类时用「分类」列；四表时用「tag」列
_CATEGORY_PROP_SINGLE_DB = "分类"
_CATEGORY_PROP_FOUR_DB = "tag"


def _get_property_ids(database_id: str) -> Optional[dict]:
    """返回列名 -> property_id 映射。"""
    data, err = notion_client.read_database(database_id)
    if err or not data:
        return None
    name_to_id = {}
    for pid, prop in (data.get("properties") or {}).items():
        name = (prop.get("name") or "").strip()
        if name:
            name_to_id[name] = pid
    return name_to_id


def _prop_title(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": (value or "")[:2000]}}]}


def _prop_rich_text(value: str) -> dict:
    if not value:
        return {"rich_text": []}
    chunks = []
    rest = (value or "")[:2000 * 10]
    while rest:
        chunks.append({"type": "text", "text": {"content": rest[:2000]}})
        rest = rest[2000:]
    return {"rich_text": chunks}


def _prop_number(value: Optional[int]) -> dict:
    return {"number": value if value is not None else 0}


def _prop_date(iso_str: Optional[str]) -> dict:
    if not iso_str:
        return {"date": None}
    return {"date": {"start": iso_str}}


def _prop_select(value: str) -> dict:
    return {"select": {"name": (value or "").strip() or "—"}}


def write_archive_entry(
    tag: str,
    entry_id: str,
    content: str,
    importance: int = 0,
    mention_count: int = 0,
    promoted_at: Optional[str] = None,
) -> bool:
    """
    按 tag 写入归档一行。单库多分类时用 NOTION_ARCHIVE_DATABASE_ID +「分类」列；否则用四表 +「tag」列。
    tag 为 书房/客厅/图书馆/卧室 之一；留空则不写。
    """
    tag = (tag or "").strip()
    if tag not in _ARCHIVE_DB_BY_TAG:
        return False
    if NOTION_ARCHIVE_DATABASE_ID:
        database_id = NOTION_ARCHIVE_DATABASE_ID
        category_prop = _CATEGORY_PROP_SINGLE_DB
    else:
        database_id = _ARCHIVE_DB_BY_TAG.get(tag)
        category_prop = _CATEGORY_PROP_FOUR_DB
    if not database_id:
        return False
    name_to_id = _get_property_ids(database_id)
    if not name_to_id:
        logger.warning("归档 Notion 读 schema 失败 database_id=%s", database_id[:16])
        return False
    props_by_id = {}
    if "id" in name_to_id:
        props_by_id[name_to_id["id"]] = _prop_title(entry_id)
    if "content" in name_to_id:
        props_by_id[name_to_id["content"]] = _prop_rich_text(content)
    # importance、mention_count 不写入 Notion（若表里有这两列也会留空）
    # promoted_at 存给人看版本（如 2026年03月07日 14:41），列类型需为文本
    if "promoted_at" in name_to_id:
        display_promoted = iso_to_display_time(promoted_at) if promoted_at else ""
        props_by_id[name_to_id["promoted_at"]] = _prop_rich_text(display_promoted)
    if category_prop in name_to_id:
        props_by_id[name_to_id[category_prop]] = _prop_select(tag)

    # 同 id 则更新，避免重跑产生重复行
    id_prop_id = name_to_id.get("id")
    if id_prop_id:
        data, err = notion_client.query_database(
            database_id,
            filter_obj={"property": id_prop_id, "title": {"equals": entry_id}},
            page_size=1,
        )
        if not err and data and (data.get("results") or []):
            page_id = data["results"][0]["id"]
            _, err = notion_client.update_page(page_id, props_by_id)
            if not err:
                logger.debug("归档已更新 Notion tag=%s id=%s", tag, entry_id[:32])
                return True
            logger.warning("归档 Notion 更新失败 tag=%s page_id=%s err=%s", tag, page_id[:16], err)

    _, err = notion_client.create_page(
        parent={"database_id": database_id},
        properties=props_by_id,
    )
    if err:
        logger.error("归档 Notion 写入失败 tag=%s database_id=%s err=%s", tag, database_id[:16], err)
        return False
    logger.debug("归档已写入 Notion tag=%s id=%s", tag, entry_id[:32])
    return True
