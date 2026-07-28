from __future__ import annotations

from typing import Optional

from storage import du_state_store
from utils.log import get_logger

logger = get_logger(__name__)


def get_latest_longterm_memory() -> Optional[dict]:
    data = du_state_store.get_du_longterm_memory()
    return data if isinstance(data, dict) else None


def format_inject_block(latest: Optional[dict] = None) -> str:
    item = latest or get_latest_longterm_memory()
    if not isinstance(item, dict):
        return ""
    content = str(item.get("content") or "").strip()
    if not content:
        return ""
    covered_through = str(item.get("covered_through") or "").strip()
    title = "长期记忆"
    if covered_through:
        title = f"长期记忆（截至 {covered_through}）"
    return f"【{title}】\n{content}\n【以上为长期记忆】"


def inject_into_static_system(body: dict) -> dict:
    try:
        block = format_inject_block()
        if not block.strip():
            return body
        from pipeline.pipeline import _append_to_static_system

        return _append_to_static_system(body, "\n\n" + block.strip())
    except Exception as e:
        logger.debug("du_longterm 注入跳过 error=%s", e)
        return body
