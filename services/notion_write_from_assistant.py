# 渡写入 Notion：已改为通过工具调用，见 NOTION_TOOLS_ENABLED 与 services/chat_tools.py
# 本模块保留空壳以兼容调用方；实际写入由渡调用 notion_append_to_page / notion_append_to_notebook 完成。


def process_assistant_content_for_notion_write(assistant_content: str) -> None:
    """已改为工具调用，本函数保留为空操作以兼容流式路径的调用。"""
    pass
