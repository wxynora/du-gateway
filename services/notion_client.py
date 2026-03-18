# Notion API：通过网关对 Notion 的读写删改（CRUD）
import logging
import os
import time
from typing import Any, Optional

import requests

from config import NOTION_API_KEY, NOTION_VERSION

logger = logging.getLogger(__name__)

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# 网络/连接类错误时重试（如 10054 远程关闭连接）
_NOTION_RETRY_EXCEPTIONS = (ConnectionError, ConnectionResetError, TimeoutError, requests.exceptions.Timeout, requests.exceptions.ConnectionError)
_NOTION_RETRY_TIMES = 3
_NOTION_RETRY_SLEEP = 1.5


def _req(method: str, path: str, json_data: Optional[dict] = None, params: Optional[dict] = None):
    if not NOTION_API_KEY:
        return None, {"error": "NOTION_API_KEY not configured"}
    url = f"{BASE}{path}"
    last_err = None
    for attempt in range(_NOTION_RETRY_TIMES):
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
                logger.warning("Notion API 错误 method=%s path=%s status=%s body=%s", method, path, r.status_code, (r.text or "")[:1000])
                return None, {"error": r.text, "status": r.status_code}
            return (r.json() if r.content else None), None
        except _NOTION_RETRY_EXCEPTIONS as e:
            last_err = e
            if attempt < _NOTION_RETRY_TIMES - 1:
                time.sleep(_NOTION_RETRY_SLEEP)
        except Exception as e:
            return None, {"error": str(e)}
    return None, {"error": str(last_err)}


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


def get_database_schema(database_id: str) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
    """返回 (name_to_id, name_to_type, err)。name_to_type 为属性名 -> Notion 类型。"""
    data, err = read_database(database_id)
    if err or not data:
        return None, None, (err or {"error": "read_database 为空"})
    name_to_id = {}
    name_to_type = {}
    for pid, prop in (data.get("properties") or {}).items():
        name = (prop.get("name") or "").strip()
        if name:
            name_to_id[name] = pid
            name_to_type[name] = (prop.get("type") or "rich_text").strip()
    return name_to_id, name_to_type, None


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


def _block_to_plain_text(block: dict) -> str:
    """从单个 block 提取纯文本（paragraph/heading/list 等）。"""
    t = (block.get("type") or "").strip()
    inner = block.get(t)
    if not inner or not isinstance(inner, dict):
        return ""
    rich = inner.get("rich_text") or []
    return " ".join(
        (r.get("plain_text") or "") for r in rich if isinstance(r, dict)
    ).strip()


def get_page_content_as_text(page_id: str) -> tuple[Optional[str], Optional[str], Optional[dict]]:
    """
    读取页面：标题（从 properties 第一个 title 列）+ 正文（块内容拼接）。
    返回 (title, body_text, err)。body_text 含所有子块文本，递归获取子块并分页。
    """
    page, err = read_page(page_id)
    if err or not page:
        return None, None, (err or {"error": "read_page 为空"})
    props = page.get("properties") or {}
    title_parts = []
    for pid, prop in props.items():
        if isinstance(prop, dict) and (prop.get("type") == "title"):
            arr = (prop.get("title") or [])
            title_parts.append(" ".join(
                (t.get("plain_text") or "") for t in arr if isinstance(t, dict)
            ))
            break
    title = " ".join(title_parts).strip() or "(无标题)"

    parts = []
    cursor = None
    while True:
        data, err = _req("GET", f"/blocks/{page_id}/children", params={
            "page_size": 100,
            **({"start_cursor": cursor} if cursor else {}),
        })
        if err or not data:
            break
        for block in (data.get("results") or []):
            text = _block_to_plain_text(block)
            if text:
                parts.append(text)
            if block.get("has_children"):
                child_text = _blocks_children_to_text(block.get("id"))
                if child_text:
                    parts.append(child_text)
        cursor = (data or {}).get("next_cursor")
        if not cursor or not (data or {}).get("has_more"):
            break
    body = "\n".join(parts)
    return title, body, None


def _blocks_children_to_text(block_id: str) -> str:
    """递归取块下所有子块文本。"""
    parts = []
    cursor = None
    while True:
        data, err = _req("GET", f"/blocks/{block_id}/children", params={
            "page_size": 100,
            **({"start_cursor": cursor} if cursor else {}),
        })
        if err or not data:
            break
        for block in (data.get("results") or []):
            text = _block_to_plain_text(block)
            if text:
                parts.append(text)
            if block.get("has_children"):
                parts.append(_blocks_children_to_text(block.get("id")))
        cursor = (data or {}).get("next_cursor")
        if not cursor or not (data or {}).get("has_more"):
            break
    return "\n".join(parts)
