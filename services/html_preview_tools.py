# 渡可调：把 HTML 发布为临时预览链接（与 POST /html-preview/ 共用存储）
from typing import List

from services.html_preview_store import create_preview


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
                    "成功后把返回的 url 用简短话术发给老婆（例如：预览链接：…）。"
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
