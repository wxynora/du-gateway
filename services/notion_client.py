# Notion API：通过网关对 Notion 的读写删改（CRUD）
import os
from typing import Any, Optional

import requests

from config import NOTION_API_KEY, NOTION_VERSION

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}


def _req(method: str, path: str, json_data: Optional[dict] = None, params: Optional[dict] = None):
    if not NOTION_API_KEY:
        return None, {"error": "NOTION_API_KEY not configured"}
    url = f"{BASE}{path}"
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        elif method.upper() == "POST":
            r = requests.post(url, headers=HEADERS, json=json_data or {}, timeout=30)
        elif method.upper() == "PATCH":
            r = requests.patch(url, headers=HEADERS, json=json_data or {}, timeout=30)
        elif method.upper() == "DELETE":
            r = requests.delete(url, headers=HEADERS, timeout=30)
        else:
            return None, {"error": f"Unsupported method: {method}"}
        if r.status_code >= 400:
            return None, {"error": r.text, "status": r.status_code}
        return (r.json() if r.content else None), None
    except Exception as e:
        return None, {"error": str(e)}


def search(query: Optional[str] = None) -> tuple[Optional[Any], Optional[dict]]:
    """Notion 搜索（关键词检索）。"""
    body = {}
    if query:
        body["query"] = query
    return _req("POST", "/search", json_data=body if body else None)


def read_page(page_id: str) -> tuple[Optional[Any], Optional[dict]]:
    """读取单个页面/块。"""
    return _req("GET", f"/pages/{page_id}")


def read_block_children(block_id: str) -> tuple[Optional[Any], Optional[dict]]:
    """读取块下的子块。"""
    return _req("GET", f"/blocks/{block_id}/children")


def create_page(parent: dict, properties: dict, children: Optional[list] = None) -> tuple[Optional[Any], Optional[dict]]:
    """
    创建新页面。
    parent: {"database_id": "xxx"} 或 {"page_id": "xxx"}
    properties: Notion 格式的 properties
    """
    body = {"parent": parent, "properties": properties}
    if children:
        body["children"] = children
    return _req("POST", "/pages", json_data=body)


def update_page(page_id: str, properties: dict) -> tuple[Optional[Any], Optional[dict]]:
    """更新页面属性。"""
    return _req("PATCH", f"/pages/{page_id}", json_data={"properties": properties})


def update_block(block_id: str, payload: dict) -> tuple[Optional[Any], Optional[dict]]:
    """更新块内容。"""
    return _req("PATCH", f"/blocks/{block_id}", json_data=payload)


def delete_block(block_id: str) -> tuple[Optional[Any], Optional[dict]]:
    """删除块（归档）。"""
    return _req("DELETE", f"/blocks/{block_id}")


def append_block_children(block_id: str, children: list) -> tuple[Optional[Any], Optional[dict]]:
    """
    在块（如页面）下追加子块。
    children: Notion 块列表，如 [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "..."}}]}}]
    """
    if not block_id or not children:
        return None, {"error": "block_id and children required"}
    return _req("POST", f"/blocks/{block_id}/children", json_data={"children": children})


def read_database(database_id: str) -> tuple[Optional[Any], Optional[dict]]:
    """读取 database 元信息（含 properties schema）。"""
    return _req("GET", f"/databases/{database_id}")


def query_database(
    database_id: str,
    filter_obj: Optional[dict] = None,
    sorts: Optional[list] = None,
    start_cursor: Optional[str] = None,
    page_size: int = 100,
) -> tuple[Optional[Any], Optional[dict]]:
    """
    查询 database 下的页面（分页）。
    返回 (data, err)，data 含 results, next_cursor, has_more。
    """
    body = {"page_size": page_size}
    if filter_obj:
        body["filter"] = filter_obj
    if sorts:
        body["sorts"] = sorts
    if start_cursor:
        body["start_cursor"] = start_cursor
    return _req("POST", f"/databases/{database_id}/query", json_data=body)
