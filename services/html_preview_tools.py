# 渡可调：把 HTML 发布为临时预览链接（与 POST /html-preview/ 共用存储）
import re
from typing import List

from services.html_preview_store import create_preview

# 从 tool 结果里抽取预览 URL（与路由 path 一致）
HTML_PREVIEW_URL_RE = re.compile(
    r"https?://[^\s<>\"']+/html-preview/v/\S+",
    re.IGNORECASE,
)


def get_html_preview_tools_for_inject() -> List[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "publish_html_preview",
                "description": (
                    "把完整 HTML 页面发布为临时可访问链接，老婆可在浏览器打开查看渲染效果（类似网页预览）。"
                    "当老婆需要「看一眼页面效果」、图表页、小游戏、排版预览时使用；不要用于纯聊天文字。"
                    "传入完整 html 字符串（可含内联 style/script）。"
                    "若正文中还没写链接，网关也会把预览链接自动附在回复里发给老婆。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "html": {
                            "type": "string",
                            "description": "完整 HTML 文档源码",
                        },
                    },
                    "required": ["html"],
                },
            },
        },
    ]


def execute_publish_html_preview(arguments: dict) -> str:
    if not isinstance(arguments, dict):
        return "参数无效"
    html = arguments.get("html")
    if html is None or (isinstance(html, str) and not html.strip()):
        return "html 不能为空"
    if not isinstance(html, str):
        return "html 须为字符串"

    ok, payload = create_preview(html)
    if not ok:
        return str(payload)

    assert isinstance(payload, dict)
    url = str(payload.get("url", ""))
    exp = int(payload.get("expires_in") or 0)
    return f"预览已生成（约 {exp // 60} 分钟内有效，过期需重新发布）：\n{url}"


def extract_html_preview_urls_from_messages(messages: list) -> List[str]:
    """从含 /html-preview/v/ 的 tool 结果里取出 URL（保序去重）。"""
    seen: set[str] = set()
    out: list[str] = []
    for m in messages or []:
        if str(m.get("role") or "").lower() != "tool":
            continue
        c = m.get("content")
        if not isinstance(c, str) or "/html-preview/v/" not in c:
            continue
        for u in HTML_PREVIEW_URL_RE.findall(c):
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def missing_html_preview_url_suffix(assistant_text: str, messages: list) -> str:
    """
    若消息链里已有预览 URL 但助手正文未包含，返回应追加的片段（含前置换行）；否则空串。
    """
    urls = extract_html_preview_urls_from_messages(messages)
    if not urls:
        return ""
    text = assistant_text or ""
    missing = [u for u in urls if u not in text]
    if not missing:
        return ""
    prefix = "\n\n" if text.strip() else ""
    return prefix + "预览链接：\n" + "\n".join(missing)


def merge_html_preview_urls_into_assistant_text(assistant_text: str, messages: list) -> str:
    suf = missing_html_preview_url_suffix(assistant_text, messages)
    if not suf:
        return assistant_text or ""
    return (assistant_text or "") + suf
