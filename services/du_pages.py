from __future__ import annotations

import json
from typing import Any, List

from storage import du_pages_store
from utils.log import get_logger


logger = get_logger(__name__)

DU_PAGE_TOOL_NAME = "du_page"


def get_du_page_tools_for_inject() -> List[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": DU_PAGE_TOOL_NAME,
                "description": (
                    "保存和管理「渡的页笺」。"
                    "写 HTML 页面、情书、小网页、小游戏和排版作品时，必须用 action=save 保存完整 html。"
                    "保存成功后把返回的长期 url 发给她，不要只贴源码。"
                    "action=list/get/update/delete/restore/stats 用于查看和整理。"
                    "如果只是临时试效果，也先保存到这里，后续可以删除。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["save", "list", "get", "update", "delete", "restore", "stats"],
                            "description": "save 存页笺；list 列表；get 读取；update 修改；delete 软删除；restore 恢复；stats 查看概况。",
                        },
                        "id": {"type": "string", "description": "页笺 id；get/update/delete/restore 时需要。"},
                        "html": {"type": "string", "description": "完整 HTML 文档源码；action=save 必须传，update 时可传。"},
                        "title": {"type": "string", "description": "页笺标题；不传时从 <title> 或正文里自动取。"},
                        "emoji": {"type": "string", "description": "可选，一个小标记。"},
                        "description": {"type": "string", "description": "可选，简短说明这页是什么。"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选标签，如 情书、小游戏、纪念。",
                        },
                        "query": {"type": "string", "description": "list 时按标题、说明或 HTML 内容搜索。"},
                        "tag": {"type": "string", "description": "list 时按单个标签过滤。"},
                        "limit": {"type": "integer", "description": "list 返回数量，默认 10，最多 100。"},
                        "include_deleted": {"type": "boolean", "description": "list/get 时是否包含已删除项，默认 false。"},
                    },
                    "required": ["action"],
                },
            },
        }
    ]


def _tool_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _safe_limit(value: Any, default: int = 10, *, max_value: int = 100) -> int:
    try:
        n = int(float(str(value or default).strip()))
    except Exception:
        n = default
    return max(1, min(max_value, n))


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def execute_du_page_tool(name: str, arguments: dict) -> str:
    if name != DU_PAGE_TOOL_NAME:
        return _tool_json({"ok": False, "error": "UNKNOWN_TOOL"})
    args = arguments if isinstance(arguments, dict) else {}
    action = str(args.get("action") or "").strip().lower()
    try:
        if action == "save":
            item = du_pages_store.save_page(args)
            return _tool_json({"ok": True, "action": action, "item": item, "url": item.get("url")})
        if action == "list":
            pages = du_pages_store.list_pages(
                include_deleted=_bool_value(args.get("include_deleted")),
                query=str(args.get("query") or ""),
                tag=str(args.get("tag") or ""),
                limit=_safe_limit(args.get("limit")),
            )
            return _tool_json({"ok": True, "action": action, "pages": pages, "count": len(pages)})
        if action == "get":
            item = du_pages_store.get_page(
                str(args.get("id") or ""),
                include_html=True,
                include_deleted=_bool_value(args.get("include_deleted")),
            )
            if not item:
                return _tool_json({"ok": False, "action": action, "error": "NOT_FOUND"})
            return _tool_json({"ok": True, "action": action, "item": item})
        if action == "update":
            item = du_pages_store.update_page(str(args.get("id") or ""), args)
            if not item:
                return _tool_json({"ok": False, "action": action, "error": "NOT_FOUND_OR_UPDATE_FAILED"})
            return _tool_json({"ok": True, "action": action, "item": item, "url": item.get("url")})
        if action == "delete":
            item = du_pages_store.soft_delete_page(str(args.get("id") or ""))
            if not item:
                return _tool_json({"ok": False, "action": action, "error": "NOT_FOUND_OR_DELETE_FAILED"})
            return _tool_json({"ok": True, "action": action, "item": item})
        if action == "restore":
            item = du_pages_store.restore_page(str(args.get("id") or ""))
            if not item:
                return _tool_json({"ok": False, "action": action, "error": "NOT_FOUND_OR_RESTORE_FAILED"})
            return _tool_json({"ok": True, "action": action, "item": item, "url": item.get("url")})
        if action == "stats":
            return _tool_json({"ok": True, "action": action, "stats": du_pages_store.stats()})
        return _tool_json({"ok": False, "error": "INVALID_ACTION", "message": "action 必须是 save/list/get/update/delete/restore/stats"})
    except Exception as exc:
        logger.exception("du_page tool failed action=%s", action)
        return _tool_json({"ok": False, "action": action, "error": "EXECUTION_FAILED", "message": str(exc)})
