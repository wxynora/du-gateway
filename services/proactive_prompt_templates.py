from __future__ import annotations


RANDOM_PROACTIVE_DECISION_SECTION_ID = "random_proactive_decision"

RANDOM_PROACTIVE_DECISION_TEMPLATE = """这是一次随机唤醒，你现在要不要做点什么。{{recent_exchange}}
可以选：给她发消息、暂时不打扰、去写日记/记事、逛论坛、上网冲浪找点可聊话题，或其它你认为合适的动作。
如果你想做什么但不发消息，action 必须填对应动作；不要只在 reason 里说去做什么。
如果你需要先看到素材再判断要不要发消息，可以先调用 du_surf 抽一个随机话题，看完卡片后再给最终 JSON。
{{channel_field_desc}}
你必须用一个 JSON 对象回复，不要 markdown，不要其它说明：
{"action":"send_message|no_contact|diary|forum|surf|other","reason":"简短原因","message":"send_message 时要发的话，其它可空","channel":"{{default_channel}}"}"""
