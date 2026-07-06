from services.device_action_tools import (
    dedupe_sumitalk_cards_in_text,
    merge_sumitalk_cards_into_assistant_text,
)


def merge_sumitalk_card_into_nonstream_response(resp_json: dict, messages: list) -> dict:
    """非流式 Sumitalk：若调用了 app 原生动作工具，补入可渲染的卡片 marker。"""
    if not resp_json or not isinstance(resp_json, dict):
        return resp_json
    choices = resp_json.get("choices") or []
    if not choices:
        return resp_json
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        return resp_json
    ct = msg.get("content")
    if not isinstance(ct, str):
        return resp_json
    merged = merge_sumitalk_cards_into_assistant_text(ct, messages)
    if merged != ct:
        msg["content"] = merged
    return resp_json


def dedupe_stream_sumitalk_cards(assistant_text: str) -> str:
    return dedupe_sumitalk_cards_in_text(assistant_text)


def sumitalk_card_suffix_for_stream(assistant_text: str, messages: list) -> str:
    merged = merge_sumitalk_cards_into_assistant_text(assistant_text, messages)
    if merged == assistant_text:
        return ""
    return merged[len(assistant_text):] if merged.startswith(assistant_text) else ("\n" + merged)
