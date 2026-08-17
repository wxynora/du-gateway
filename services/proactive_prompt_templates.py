from __future__ import annotations


RANDOM_PROACTIVE_DECISION_SECTION_ID = "random_proactive_decision"


def build_proactive_decision_xml_contract(
    *,
    allowed_actions: str = "send_message|no_contact|diary|forum|surf|drawer|game|other",
    default_channel: str = "{{default_channel}}",
) -> str:
    return f"""【固定决策输出格式】
只输出一个 decision XML，不要 Markdown、代码块或其它说明：
<decision>
  <action>{allowed_actions}</action>
  <reason><![CDATA[简短原因]]></reason>
  <message><![CDATA[send_message 时要发的话，其它可空]]></message>
  <game><![CDATA[game 时按下方游戏列表填写，否则留空]]></game>
  <channel>{default_channel}</channel>
</decision>
action 只能填写一个实际选项，不要原样输出竖线分隔的候选列表。reason、message、game 的内容统一放在各自 CDATA 中。"""


_LEGACY_JSON_CONTRACT_LINES = {
    "你必须用一个 JSON 对象回复，不要 markdown，不要其它说明：",
    '{"action":"send_message|no_contact|diary|forum|surf|drawer|game|other","reason":"简短原因","message":"send_message 时要发的话，其它可空","game":"game 时按下方游戏列表填写，否则留空","channel":"{{default_channel}}"}',
}


def enforce_proactive_decision_xml_contract(template: str) -> str:
    """保留托管模板正文，但把历史 JSON 契约统一替换为当前 XML 契约。"""
    text = str(template or "").replace("看完卡片后再给最终 JSON", "看完卡片后再给最终决定")
    marker = "【固定决策输出格式】"
    if marker in text:
        text = text.split(marker, 1)[0]
    kept_lines = [line for line in text.splitlines() if line.strip() not in _LEGACY_JSON_CONTRACT_LINES]
    body = "\n".join(kept_lines).rstrip()
    contract = build_proactive_decision_xml_contract()
    return f"{body}\n\n{contract}" if body else contract


RANDOM_PROACTIVE_DECISION_TEMPLATE = enforce_proactive_decision_xml_contract("""这是一次随机唤醒，你现在要不要做点什么。{{recent_exchange}}
可以选：给她发消息、暂时不打扰、去写日记/记事、逛论坛、上网冲浪找点可聊话题、整理秘密抽屉/随机翻旧条目、玩一会游戏，或其它你认为合适的动作。
如果你想做什么但不发消息，action 必须填对应动作；不要只在 reason 里说去做什么。
如果你需要先看到素材再判断要不要发消息，可以先调用 du_surf 抽一个随机话题，看完卡片后再给最终决定。
{{channel_field_desc}}""")
