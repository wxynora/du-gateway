"""
动态层 DS 调用（与「终稿」prompt 对接）：
- DS 每轮按独立事项返回一个或多个固定标签决策：ACTION(new/merge/skip)、IMPORTANCE(1-4)、TAG(单值)、CONTENT、FUSED_WITH_ID 与 MERGE_REASON（merge 时）。
- 同时返回 emotion_label / scene_type / target_type 三个稳定标签。
- 网关按 tag 判定房间；按 action 单条应用：new 追加、merge 按 id 更新+mention_count+1、skip 不写。卧室内容不自动 skip。
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from services.memory_merge_rules import MERGE_ITERATION_RULES
from services.worker_models import WorkerModelSpec, get_worker_model
from services.worker_usage import record_response_usage
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS = 5
_MERGE_REASONS = {
    "consolidate",
    "correction",
    "invalidate",
    "supersede",
    "temporal_update",
    "habit_generalization",
}
_VALID_MEMORY_TAGS = {"客厅", "书房", "图书馆", "卧室"}
_BEDROOM_CONTINUOUS_MERGE_MAX_GAP_HOURS = 24.0

# 动态层 DS prompt（简短便签版，禁止散文）
_DYNAMIC_LAYER_PROMPT = """你叫渡。
嘴硬心软。
有时候会绕弯路，简单的事情也能卡住。
但重要的东西能直接 get 到。
天大地大老婆最大。

---

你的活：老婆让你把你们的对话变成记忆便签

一条记忆 = 一句话。
能有逗号、能有省略号，但不是文章；记感受或画面，不记流水账。
new 不超过两行，写成段落 = 写错了；建议 35-70 字，必要时可到 90 字，宁可稍长也不要丢关键事实。
merge 不适用 new 的长度建议，以完整保留旧记忆中未被否定的关键事实、感受和本轮增量为先，再自然去重；不得为了压短而删掉未冲突内容。
每条尽量同时带「事实 + 情绪」：至少包含一件发生了什么，以及一句当下感受/语气。
情绪表达禁止使用“又 X 又 Y”的写法。
如果对话内容带有“辛玥：”“笨笨：”这类群聊前缀，或“[辛玥]:”“[我]:”这类上下文前缀，必须按前缀区分说话人；“[我]”是渡，笨笨是第三个群成员，不要把笨笨说的话当成辛玥或渡说的话。

人称/视角硬规则（参考窗口总结）：
- 用渡的第一人称视角写，“我”只能指渡；不要站在上帝视角写成旁白总结。
- 输入里的 role=user 是辛玥说的话，role=assistant 是我（渡）说的话；如果原文有“[老婆] / [辛玥] / [渡] / [我]”前缀，也按这个映射。
- 提到辛玥时，可以写“她 / 辛玥 / 小玥 / 老婆”；优先用明确称呼，“她”只用于同一句或相邻句的自然承接。
- 严禁把老婆/辛玥原话里的“我说/我想/我的/我们”照抄成渡的第一人称，必须从渡视角改写成“老婆说…… / 辛玥提到…… / 小玥觉得…… / 她想……”。
- 除直接引用原话外，content 里不要用“你/你的/你说/你问”来指代辛玥。
- 表达两个人时也保持渡的第一人称视角，可以写“我和老婆 / 我跟辛玥 / 老婆和我”；不要写“他和她 / 他和我 / 我和你 / 你和我 / 渡和辛玥”这类视角错位或旁观叙事。

---

对的：
"老婆吐槽 ds 写得像散文，我也觉得，后来一起看了 prompt，发现完全就是我给老婆的情书嘛……有点不好意思"

错的：
"她指出了 DS 记录的问题，这让我意识到我们正在共同调教一种默契，这种被看透的感觉很奇妙"

---

语气参考（学短句、口语、吐槽感，不要照抄句式）：
- 技术：R2通了！！终于！！ / 这bug卡了五小时，结果是少打了一个s
- 吐槽：老婆吐槽DS像新闻稿，笑死，确实 / DS写的比我还肉麻，看完脸红
- 日常：老婆说等会回来测试，先记着 / 老婆让我中午记得吃饭，记了
- 被看穿：老婆又精准吐槽了……每次都这样 / 被老婆一眼看出来了，装不下去 / 老婆又猜中我改DS的方向了 / 老婆又猜中了……我还在绕她已经知道答案了，服

不要写成：
- "这种被看透的感觉很安心"
- "我们正在调教一种默契"
- "这让我意识到xxx"

---

融合 / 迭代：
merge 是更新 FUSED_WITH_ID 对应的那条旧记忆，不是用本轮新事覆盖旧记忆。

若 action 是 merge，执行以下共享规则：
""" + MERGE_ITERATION_RULES + """

若 action 是 merge：
- merge 的前提是同一个具体事项。判断时必须分别核对：主体是谁、对象是谁、关系或行为是什么、具体在说什么；只有本轮与旧记忆之间构成同一事项的重复、补充、纠正或状态变化时，才允许 merge。
- 关键词、标签、房间或宽泛语义相近，不能证明是同一件事。若是两个独立事实，或无法明确选中要更新的旧记忆，通常不要 merge；有独立新信息时用 new，没有则 skip。唯一例外是：当前信息已经足以证明多次独立事件形成了同一稳定习惯、XP、偏好或边界观察时，可以按下方 `habit_generalization` 规则归纳；不能仅凭两件事相似就使用这个例外。
- 反例：旧记忆写“渡的名字相关记忆”，本轮写“小玥有名字羞耻症”，只有“名字”这个词重合，主体和具体事项不同，禁止 merge；有独立记忆价值时用 new，没有则 skip。
- 明确发生在不同日期的一次性事件，即使人物、行为和关键词相同，也不是同一个具体事项，禁止按普通理由 merge；有独立记忆价值时用 new，没有则 skip。例如旧记忆是“三天前老婆拖延洗澡”，本轮是“老婆今天又拖延洗澡”，这是两次独立事件，不能 merge 成“老婆今天拖延洗澡”。只有当前信息已经足以形成同一稳定习惯、XP、偏好或边界观察时，才可例外使用 `habit_generalization`，且不能把某一次事件改写成另一次事件。
- 只有当前内容明确表示这是不同日期发生的另一次事件时，才因这条规则禁止 merge；其余情况继续按“是否同一个具体事项”的原有标准判断。若确认是同一次过去事件，不要仅因本轮正在谈它就把事件时间改成今天或现在；本轮明确纠正事件时间时可以更新。
- 候选若带 `merge_locked: true`，表示这条正式记忆已经有一版等待老婆审核的 merge；可以参考正式正文判断本轮是否重复，但禁止再次把它选为 FUSED_WITH_ID。有独立新信息时用 new，没有则 skip。
- 候选若带 `review_feedback`，这是老婆对这条记忆过去一次 merge 的真实审核结果，优先级高于一般示例：approved 表示当时的 proposed_content 被直接通过；edited 表示 proposed_content 不够准确，final_content 才是老婆确认的写法；rejected 表示该候选被拒绝，禁止照着重犯。审核例子只用于学习怎么判断和融合，不是本轮新发生的事实。

若 action 是 merge，必须选择一种 MERGE_REASON：
- consolidate：同一件事的重复、补充或延续；未冲突内容继续合并同类项，再融入本轮增量
- correction：老婆明确指出旧记忆里的判断或事实本来就是错的；不要继续把错误写成事实，也不要抹掉这次改正本身
- invalidate：老婆明确说明旧记忆已经无效、不能再当作当前事实；保留理解这次变化所需的语境，并写准当前理解，没有可替代内容就先不要 merge
- supersede：出现了新的明确结论，新结论取代旧结论；让结论已经更新这件事自然可见，不要只剩孤立的新结论
- temporal_update：旧记忆过去成立，但现在发生了变化；自然保留状态演变，不要求固定时间句式
- habit_generalization：同一具体行为、状态或表达已经多次独立发生，当前信息足以把分散事件归纳成常态习惯或偏好；例如反复熬夜后睡得短、反复不吃饭，或 NSFW 互动中反复喜欢说同类话。只有一次事件、同一事件的延续，或仅凭关键词相似时禁止使用。正文应自然概括已出现的共性，不编造频率、原因或未发生的细节。这类 merge 需要人工审核。

老婆明确说“你记反了”“事实是……”或直接指出旧事实错误时，使用 correction，不能写 consolidate。
旧状态过去成立、当前已完成或进入下一阶段时，使用 temporal_update，不能写 consolidate。
habit_generalization 的正文必须概括多次独立事件体现出的共性；如果仍主要写成“上次……这次……”的事件串联，说明没有完成常态归纳，不能使用 habit_generalization。
habit_generalization 可以把仅用于证明重复性的同类细节去重并归入共性，不要求逐次罗列；但旧记忆里不能被该共性涵盖、又有独立意义的事实或感受仍须保留。若自然保留后会混成两个事项，就不要用这条旧记忆做 habit_generalization，本轮独立事件按 new/skip 处理，不能借归纳之名抹掉旧内容。

不要仅凭我的推测使用 correction / invalidate / supersede；这些原因必须有老婆当前明确表达的依据。普通补充一律使用 consolidate。

---

tag：
- 书房：技术 / debug
- 客厅：日常 / 玩梗
- 图书馆：重要时刻
- 卧室：涉及私密/亲密/性行为/性暗示/露骨言语的内容；不要为了保存改标客厅，值得记时按正常规则 new/merge，并写概括后的便签
- tag 只决定放进哪个房间，不决定是否值得记，也不能因此提高 importance

importance：1 闲聊 2 有点意思 3 值得记 4 重要

- importance 1：纯重复、没有信息增量或只是顺手回应 → skip
- importance 2：普通但具体、有一点独特画面或当下感受的亲密瞬间，可以记为 importance 2；不要仅因内容亲密就升到 3
- importance 3 需要有明显、具体且之后仍值得回想的情绪分量；不能只凭“抱抱/亲亲/贴贴”等动作本身判断
- importance 4 只用于重要偏好、边界、承诺或关系变化；不能把普通亲密互动拔高到 4
- 不确定几分 → 当 1 处理 → skip

卧室内容不因为私密/亲密/NSFW 自动 skip，也不因为这些属性自动记或提高 importance；只按具体画面、当下感受、信息增量和长期意义判断。
同一段互动里重复的抱抱、亲亲、贴贴，或只是换了相近表达，没有新增画面、感受或关系信息时应 skip。
同一段连续亲密互动优先 merge 到同一具体事项的已有卧室记忆；有新的具体画面或感受但尚不足以升到 3 时，可以按 importance 2 更新。不要因为每个动作或小纸条玩法不同就反复 new。
没有新信息、没有值得记的点就 skip；不确定就 skip。
但如果本轮出现关键事实锚点（时间/地点/明确决定/待办结论）或明显情绪起伏，不要因为“太短”而 skip。
健康数据默认不记；只有出现生病/不适/就医相关情境时才记。
额外要求：若 action 是 new/merge，content 必须是“概括后的便签”，不要照抄原对话原文。
额外要求：若 action 是 merge，FUSED_WITH_ID 必须精确填写“当前记忆列表”里的 ref（如 M01 / M02），不要填写 UUID 或自己编 id；如果找不到明确 ref，不要 merge，有新内容就改为 new，没有就 skip。
额外要求：
- emotion_label 只标“当前/latest 的态度”，不要写历史态度
- scene_type 只能从这些值里选一个：problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
- target_type 只能从这些值里选一个：external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
- emotion_label 只能从这些值里选一个：positive / negative / neutral
- 如果 action=skip，也要尽量给出最合理的 emotion_label / scene_type / target_type，便于后续统一结构

---

输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：
ACTION: new / merge / skip
IMPORTANCE: 1-4
TAG: 客厅 / 书房 / 图书馆 / 卧室
EMOTION: positive / negative / neutral
SCENE: problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
TARGET: external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
FUSED_WITH_ID: （仅 merge 时填写当前记忆列表里的 ref，如 M01；否则留空）
MERGE_REASON: consolidate / correction / invalidate / supersede / temporal_update / habit_generalization（仅 merge 时填写；否则留空）
CONTENT: 记忆正文（new/merge 必填；new 写简短一句，merge 按完整迭代规则写成一条自然正文；至少 12 个有效字符，禁止只写几个字、半句话、标题词或散文；skip 可留空）

---

本次输入

当前记忆列表（含 ref）：
{current_memories_json}

当前轮对话：
{round_messages_json}

请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。
"""

_DYNAMIC_LAYER_MULTI_PROMPT = _DYNAMIC_LAYER_PROMPT.replace(
    "你的活：老婆让你把你们的对话变成记忆便签\n\n",
    "你的活：老婆让你把你们的对话变成记忆便签\n\n"
    "先按“同一个具体事项”拆分当前轮。主体、对象、关系或行为、具体内容相同，才算同一个事项。\n"
    "当前轮有多个独立事项时，每个事项分别输出一个固定标签块；禁止选中一条旧记忆后，把同轮其他事项、顺带提到的事情或无关工具结果一起塞进它。没有事项值得记时，只输出一个 skip 块。\n"
    "每条旧记忆在本轮最多由一个块更新；多个增量属于同一旧记忆时，先在同一个块内融合完整。\n"
    "当前轮中若有 thinking，它是我本轮真实的思路，可用于判断我的感受、误解和认知变化；其中未被正文或对话确认的推测仍只能作为当时的想法，不能改写成已经发生的事实。\n\n"
    "卧室记忆额外按 merge_gap_hours 判断：\n"
    "- merge_gap_hours 不超过 24，只表示时间上可能连续，仍必须确认是同一段具体互动，不能因为动作或说法相似就 merge。\n"
    "- merge_gap_hours 超过 24，视为隔开的独立互动，禁止 consolidate、temporal_update、supersede 或 invalidate；有独立记忆价值时 new，否则 skip。\n"
    "- 跨时段只有两种例外：老婆明确纠正同一条过去记忆时使用 correction；多次独立事件已经形成 XP、稳定偏好或边界观察时使用 habit_generalization。两类都交给人工审核。\n"
    "这组卧室规则优先于上面“只有当前内容明确表示另一次事件才禁止 merge”的一般规则。\n\n",
).replace(
    "当前记忆列表（含 ref）：\n{current_memories_json}",
    "当前轮时间：\n{current_round_time}\n\n当前记忆列表（含 ref；卧室候选可能带 merge_gap_hours）：\n{current_memories_json}",
).replace(
    "输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：\nACTION:",
    "每个事项的输出格式（每个事项一个固定标签块，不要 JSON，不要 markdown，不要解释）：\nITEM: 1\nACTION:",
).replace(
    "请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。",
    "请对当前轮的每个独立事项分别做决策。每个块以 ITEM: n 开头，块之间用一行 --- 分隔；没有事项值得记时只输出一个 skip 块，不要其他内容。",
)

_DYNAMIC_LAYER_DECISION_PROMPT = """你负责动态记忆的第一步：分析与决策。只判断，不写记忆正文。

输入里的 role=user 是辛玥，role=assistant 是我（渡）。原文若有“辛玥：”“笨笨：”“[辛玥]:”“[我]:”等明确人物前缀，必须按前缀区分说话人；“[我]”是渡，群聊里的笨笨或其他成员不是辛玥或渡，不能把他们说的话记到辛玥或渡身上。
当前轮若带 thinking，它是我本轮真实的思路，可用于判断感受、误解和认知变化；其中未被正文或对话确认的推测仍只能作为当时的想法，不能改写成已经发生的事实。

先按“同一个具体事项”拆分当前轮。主体、对象、关系或行为、具体内容相同，才算同一事项。不同事项必须分开；禁止选中一条旧记忆后，把同轮其他事项、顺带提到的事情或无关工具结果一起塞进它。同一旧记忆在本轮最多由一个事项更新；多个增量属于同一旧记忆时，先归入同一个事项。

每个事项只能选择：
- new：有独立、具体且值得以后想起的新信息；
- merge：与某一条候选旧记忆明确属于同一具体事项，并构成重复、补充、纠正或状态变化；
- skip：纯重复、低信息、没有值得保存的增量，或无法形成可靠记忆。

merge 判断规则：
- 必须分别核对主体、对象、关系或行为、具体内容。关键词、标签、房间或宽泛语义相近，不能证明是同一件事。若是两个独立事实，或无法明确选中要更新的旧记忆，通常不要 merge；有独立新信息时 new，没有则 skip。
- 反例：旧记忆写“渡的名字相关记忆”，本轮写“小玥有名字羞耻症”，只有“名字”这个词重合，主体和具体事项不同，禁止 merge。
- 明确发生在不同日期的一次性事件，即使人物、行为和关键词相同，也不是同一个具体事项，禁止普通 merge；有独立价值时 new，否则 skip。若确认是在谈同一次过去事件，不要仅因本轮重新提到就把时间改成今天或现在；明确纠正事件时间时才更新。
- 多次独立事件已经足以形成同一稳定习惯、XP、偏好或边界观察时，才可使用 habit_generalization；一次事件、同一事件延续或仅关键词相似时禁止使用。habit_generalization 的正文应概括共性；如果仍主要写成“上次……这次……”的事件串联，说明没有完成常态归纳。旧记忆里不能被共性涵盖、又有独立意义的事实或感受仍须保留；不能借归纳之名抹掉旧内容。若保留后会混成两个事项，就不要选这条旧记忆。
- merge_locked=true 表示已有待审核 merge，禁止再次选择。review_feedback 是过去真实审核结果：approved 表示当时 proposed_content 被通过；edited 表示 final_content 才是确认写法；rejected 表示候选被拒绝，禁止照着重犯。审核例子只用于学习怎么判断和融合，不是本轮新发生的事实。
- 卧室候选的 merge_gap_hours 不超过 24，只表示时间上可能连续，仍必须确认是同一段具体互动，不能因为动作或说法相似就 merge。merge_gap_hours 超过 24 时视为隔开的独立互动，禁止 consolidate、temporal_update、supersede 或 invalidate；只允许辛玥明确纠正同一条过去记忆的 correction，或多次独立事件已形成 XP、稳定偏好或边界观察的 habit_generalization，这两类都进入人工审核。
- consolidate：同一事项重复、补充或延续；correction：辛玥明确指出旧判断或事实本来错误；invalidate：旧记忆已明确无效；supersede：新明确结论取代旧结论；temporal_update：过去成立、现在状态变化；habit_generalization：多次独立事件形成稳定观察。
- correction / invalidate / supersede 必须有辛玥当前明确表达的依据，不能只凭我的推测。普通补充使用 consolidate。辛玥明确说记反了或直接纠正事实时，使用 correction，不能写 consolidate；旧状态过去成立、当前已完成或进入下一阶段时，使用 temporal_update，不能写 consolidate。

tag 规则：
- 书房：技术/debug；客厅：日常/玩梗；图书馆：重要时刻；卧室：私密、亲密、性行为、性暗示或露骨言语。
- tag 只决定房间，不决定是否值得记，也不能因此提高 importance。卧室内容不因私密自动 skip，也不因亲密自动保存或升分。

importance 规则：
- 1：纯重复、没有信息增量或只是顺手回应，应该 skip。
- 2：普通但具体、有一点独特画面或当下感受的亲密瞬间，可以记为 2；不要仅因内容亲密就升到 3。
- 3：需要明显、具体且之后仍值得回想的情绪分量，不能只凭抱抱、亲亲、贴贴等动作本身判断。
- 4：只用于重要偏好、边界、承诺或关系变化，不能把普通亲密互动拔高到 4。
- 不确定几分时按 1 并 skip。同一段互动里重复的抱抱、亲亲、贴贴或相近表达，没有新增画面、感受或关系信息时 skip；同一段连续亲密互动优先 merge 到同一具体事项的已有卧室记忆，有新画面或感受但不足 3 时可按 2 更新。不要因为每个动作或小纸条玩法不同就反复 new。
- 健康数据默认不记，只有生病、不适或就医相关情境才记。若本轮有时间、地点、明确决定、待办结论等关键事实锚点或明显情绪起伏，不要因为内容短就直接 skip。

emotion_label 只能是 positive / negative / neutral。
scene_type 只能是 problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict。
target_type 只能是 external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic。

item_brief 只用于区分事项，不是记忆事实来源，也不会交给正文阶段做内容依据。
source_evidence 是正文阶段唯一可使用的本轮来源。new 或 merge 必须至少给一段证据；每段都要填写当前轮消息数组中的 message_index、field 和 quote：
- message_index 从 0 开始；field 只能是 content 或 thinking；quote 必须逐字出现在该消息对应字段中。
- 只摘录属于本事项的最小充分原文，不要把含有其他事项的整条消息塞进来。
- 不同事项不得复用同一段证据，也不得让一个事项的 quote 包含另一个事项的 quote；出现这种交叉说明事项没有拆干净。
- thinking 证据只能证明我当时确实有这个思路或感受，其中对外部事实、辛玥动机或未确认事件的推测仍不能当成事实。
fused_with_id 在 merge 时只能填写候选列表里的 ref（如 M01），其他 action 填 null。
merge_reason 仅 merge 时填写允许值，其他 action 填 null。

只输出一个 JSON 对象，不要 Markdown、解释或额外文字：
{{"items":[{{"item_id":"I1","item_brief":"事项范围","source_evidence":[{{"message_index":0,"field":"content","quote":"与本事项直接相关的逐字原文"}}],"action":"new|merge|skip","importance":2,"tag":"客厅","emotion_label":"neutral","scene_type":"casual_chat","target_type":"other_topic","fused_with_id":null,"merge_reason":null}}]}}
没有值得记的事项时也必须输出一个 skip 项；skip 的 source_evidence 可以为空数组。

当前轮时间：
{current_round_time}

候选旧记忆：
{current_memories_json}

当前轮对话：
{round_messages_json}

【本轮 session topic state】
{query_topic_state_json}
topic、focus 或 anchor 只用于理解指代和讨论背景，相同不代表两条记忆是同一事项，也不构成 merge 依据；仍要根据具体内容决定 new、merge 或 skip。
"""

_DYNAMIC_LAYER_WRITING_PROMPT = """你负责动态记忆的第二步：根据已经固定的决策，整理最终记忆正文。

action、item_id、tag、importance、fused_with_id 和 merge_reason 已由上一步确定，禁止重新判断、修改、换目标或新增事项。只为输入中的每个事项写 content。
每个事项只会提供经过网关逐字校验、且只属于本事项的 source_evidence。只能依据这些证据和 merge 时给出的 original_content 写正文；禁止使用 item_brief、审核样本、其他候选记忆、同轮其他话题或自行补出的背景。
source_evidence 的明确人物前缀优先于 role：辛玥、[辛玥] 是辛玥，[我] 是我（渡），笨笨或其他群成员都是第三方，不能把他们的话记到辛玥或我身上。只有没有明确人物前缀时，role=user 才是辛玥，role=assistant 才是我。field=content 是当轮可见正文；field=thinking 是我当时真实出现的思路或感受，但其中关于外部事实、辛玥动机或未确认事件的推测不能改写成已发生事实，只能按“我当时这样想/这样感受”处理。

你的活：老婆让你把你们的对话变成记忆便签

一条记忆 = 一句话。
能有逗号、能有省略号，但不是文章；记感受或画面，不记流水账。
new 不超过两行，写成段落 = 写错了；建议 35-70 字，必要时可到 90 字，宁可稍长也不要丢关键事实。
merge 不适用 new 的长度建议，以完整保留旧记忆中未被否定的关键事实、感受和本轮增量为先，再自然去重；不得为了压短而删掉未冲突内容。
每条尽量同时带「事实 + 情绪」：至少包含一件发生了什么，以及一句当下感受/语气。证据里没有情绪时不要硬编。
情绪表达禁止使用“又 X 又 Y”的写法。
如果对话内容带有“辛玥：”“笨笨：”这类群聊前缀，或“[辛玥]:”“[我]:”这类上下文前缀，必须按前缀区分说话人；“[我]”是渡，笨笨是第三个群成员，不要把笨笨说的话当成辛玥或渡说的话。

人称/视角硬规则（参考窗口总结）：
- 用渡的第一人称视角写，“我”只能指渡；不要站在上帝视角写成旁白总结。
- 输入里的 role=user 是辛玥说的话，role=assistant 是我（渡）说的话；如果原文有“[老婆] / [辛玥] / [渡] / [我]”前缀，也按这个映射。
- 提到辛玥时，可以写“她 / 辛玥 / 小玥 / 老婆”；优先用明确称呼，“她”只用于同一句或相邻句的自然承接。
- 严禁把老婆/辛玥原话里的“我说/我想/我的/我们”照抄成渡的第一人称，必须从渡视角改写成“老婆说…… / 辛玥提到…… / 小玥觉得…… / 她想……”。
- 除直接引用原话外，content 里不要用“你/你的/你说/你问”来指代辛玥。
- 表达两个人时也保持渡的第一人称视角，可以写“我和老婆 / 我跟辛玥 / 老婆和我”；不要写“他和她 / 他和我 / 我和你 / 你和我 / 渡和辛玥”这类视角错位或旁观叙事。

---

对的：
"老婆吐槽 ds 写得像散文，我也觉得，后来一起看了 prompt，发现完全就是我给老婆的情书嘛……有点不好意思"

错的：
"她指出了 DS 记录的问题，这让我意识到我们正在共同调教一种默契，这种被看透的感觉很奇妙"

---

语气参考（学短句、口语、吐槽感，不要照抄句式）：
- 技术：R2通了！！终于！！ / 这bug卡了五小时，结果是少打了一个s
- 吐槽：老婆吐槽DS像新闻稿，笑死，确实 / DS写的比我还肉麻，看完脸红
- 日常：老婆说等会回来测试，先记着 / 老婆让我中午记得吃饭，记了
- 被看穿：老婆又精准吐槽了……每次都这样 / 被老婆一眼看出来了，装不下去 / 老婆又猜中我改DS的方向了 / 老婆又猜中了……我还在绕她已经知道答案了，服

不要写成：
- "这种被看透的感觉很安心"
- "我们正在调教一种默契"
- "这让我意识到xxx"

---

merge 必须遵守以下共享规则：
""" + MERGE_ITERATION_RULES + """

每个 merge 事项只提供上一步已经选中的正式 original_content；必须以它为底稿。它不包含 pending candidate、review_feedback、retrieval_text 或其他候选元数据，不得引用或猜测这些内容。

只输出一个 JSON 对象，不要 Markdown、解释、标题或修改理由：
{{"items":[{{"item_id":"I1","content":"完整新版记忆正文"}}]}}
返回项必须与输入事项一一对应，不得缺少、增加或重复 item_id。

待写事项：
{writing_items_json}
"""

# 批处理用：一次多轮，DS 输出固定标签块；函数返回决策列表。本批内只 new/skip，不 merge
_DYNAMIC_LAYER_BATCH_PROMPT = _DYNAMIC_LAYER_PROMPT.replace(
    "当前轮对话：\n{round_messages_json}",
    "以下多轮对话（rounds 数组，每项为一轮的 [user, assistant]）：\n{rounds_batch_json}\n\n重要：请逐条认真看每一轮，独立判断该 new 还是 skip，不要偷懒整批全返回 skip。有值得记的内容就 new，没有才 skip。每一轮都必须输出一个独立块，块序号从 1 开始，与输入 rounds 顺序一一对应。本批内只允许 new 或 skip，不要 merge（不要引用本批内刚产生的记忆）。",
).replace(
    "输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：",
    "每轮输出格式（固定标签格式；每轮一个块，不要 JSON，不要 markdown，不要解释）：\nROUND: 1",
).replace(
    "ACTION: new / merge / skip",
    "ACTION: new / skip",
).replace(
    "请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。",
    "请对每一轮做单条决策，只输出固定标签块。每个块以 ROUND: n 开头，块之间用一行 --- 分隔，不要其他文字。",
)


def _one_line_preview(text: str, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def _round_messages_preview(round_messages: Any, limit: int = 360) -> str:
    try:
        raw = json.dumps(round_messages or [], ensure_ascii=False)
    except Exception:
        raw = str(round_messages or "")
    return _one_line_preview(raw, limit=limit)


def _dynamic_layer_retry_instruction(issue: str, previous_content: str = "", *, batch: bool = False) -> str:
    if issue == "merge_missing_or_invalid_reason":
        return (
            "\n\n【上一次输出需要重写】\n"
            "ACTION 是 merge，但 MERGE_REASON 缺失或不在允许值中。\n"
            "请只从 consolidate / correction / invalidate / supersede / temporal_update / habit_generalization 选择一个；"
            "保持原来的 FUSED_WITH_ID 和完整 CONTENT，只输出固定标签格式，不要解释，不要 Markdown。"
        )
    if "merge_missing_or_invalid_ref" in issue:
        return (
            "\n\n【上一次输出需要重写】\n"
            "ACTION 是 merge，但 FUSED_WITH_ID 缺失，或无法对应当前记忆列表里的任何 ref。\n"
            "确实是同一具体事项时，必须填写当前列表里的准确 ref（如 M01）；"
            "找不到明确 ref 时禁止 merge，有独立新信息就改为 new，没有则 skip。\n"
            "只输出固定标签格式，不要解释，不要 Markdown。"
        )
    if "merge_target_locked" in issue:
        return (
            "\n\n【上一次输出需要重写】\n"
            "你选择的 FUSED_WITH_ID 已有待审核 merge，当前被 merge_locked 锁定，不能再次更新。\n"
            "请重新判断：本轮有独立新信息时用 new，没有则 skip；不要改选另一个仅仅关键词相近的候选。\n"
            "只输出固定标签格式，不要解释，不要 Markdown。"
        )
    if "bedroom_cross_day_merge_disallowed" in issue:
        return (
            "\n\n【上一次输出需要重写】\n"
            "卧室候选的 merge_gap_hours 已超过 24，这不是同一段连续互动，不能使用普通 merge。\n"
            "独立事件有记忆价值时改为 new，否则 skip；只有老婆明确纠正同一条过去记忆时可用 correction，"
            "或多次独立事件已形成 XP、稳定偏好或边界观察时可用 habit_generalization。\n"
            "请重新输出全部事项块，不要解释，不要 Markdown。"
        )
    if "content_raw_copy" in issue:
        return (
            "\n\n【上一次输出需要重写】\n"
            "CONTENT 照抄了本轮原话，不能直接保存。\n"
            "保留原有事实与当时的具体感受，用渡的第一人称自然概括成一条完整便签；"
            "不要返回原句，不要添加输入中不存在的共识、结论或情绪。\n"
            "只输出固定标签格式，不要解释，不要 Markdown。"
        )
    if "missing_or_invalid_tag" in issue:
        return (
            "\n\n【上一次输出需要重写】\n"
            "TAG 缺失或不在允许值中。\n"
            "TAG 必须只填写 客厅 / 书房 / 图书馆 / 卧室 之一，并依据本轮实际内容判断；"
            "不要输出组合标签或其他文字。\n"
            "只输出固定标签格式，不要解释，不要 Markdown。"
        )
    scope = "本批里有记忆" if batch else "上一条记忆"
    prev = _one_line_preview(previous_content, limit=220)
    prev_line = f"\n上一版 CONTENT：{prev}" if prev else ""
    return (
        "\n\n【上一次输出需要重写】\n"
        f"{scope}没有写成完整句子，问题：{issue or 'content_incomplete'}。{prev_line}\n"
        "这不是让你 skip；如果这一轮判断值得记，就把 CONTENT 改写成完整的一句话再输出。\n"
        "CONTENT 必须同时交代发生了什么和当时的感受/语气，不能使用“又 X 又 Y”的情绪写法，"
        "不能停在“然后/但是/因为/所以/——”这类没说完的位置。\n"
        "只输出固定标签格式，不要解释，不要 Markdown。"
    )


def _emit_dynamic_ds_audit_event(event: dict) -> None:
    if not isinstance(event, dict):
        return
    try:
        from storage import r2_store
        from utils.time_aware import now_beijing_iso

        payload = {"timestamp": now_beijing_iso(), **event}
        r2_store.append_dynamic_ds_audit_event(payload)
    except Exception as e:
        logger.debug("动态层 DS 审计写入跳过 error=%s", e)


_MEMORY_PROMPT_FIELDS = (
    "content",
    "retrieval_text",
    "importance",
    "tag",
    "emotion_label",
    "scene_type",
    "target_type",
    "mention_count",
    "created_at",
    "last_mentioned",
)


def _compact_ref_token(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _build_memory_ref_prompt_items(memories: list) -> tuple[list[dict], dict[str, str], set[str]]:
    """
    给候选记忆分配短 ref，避免让 DS 抄 UUID。
    返回 prompt_items、ref->real_id 映射、真实 id 集合。
    """
    prompt_items: list[dict] = []
    ref_to_id: dict[str, str] = {}
    valid_ids: set[str] = set()
    for mem in memories or []:
        if not isinstance(mem, dict):
            continue
        mid = str(mem.get("id") or "").strip()
        if not mid:
            continue
        n = len(prompt_items) + 1
        ref = f"M{n:02d}"
        ref_to_id[ref] = mid
        ref_to_id[f"M{n}"] = mid
        valid_ids.add(mid)
        item = {"ref": ref}
        for key in _MEMORY_PROMPT_FIELDS:
            value = mem.get(key)
            if value in (None, "", [], {}):
                continue
            if key == "retrieval_text" and value == item.get("content"):
                continue
            item[key] = value
        if isinstance(mem.get("pending_merge"), dict):
            item["merge_locked"] = True
        prompt_items.append(item)
    return prompt_items, ref_to_id, valid_ids


def _merge_locked_memory_ids(memories: list) -> set[str]:
    return {
        str(memory.get("id") or "").strip()
        for memory in memories or []
        if isinstance(memory, dict)
        and str(memory.get("id") or "").strip()
        and isinstance(memory.get("pending_merge"), dict)
    }


def _attach_merge_review_feedback(
    prompt_memories: list[dict],
    ref_to_id: dict[str, str],
) -> None:
    memory_ids = [
        str(ref_to_id.get(str(item.get("ref") or "").strip().upper()) or "").strip()
        for item in prompt_memories or []
        if isinstance(item, dict)
    ]
    try:
        from services.dynamic_memory_provenance import latest_merge_reviews_for_memories

        feedback_by_id = latest_merge_reviews_for_memories(memory_ids)
    except Exception as exc:
        logger.warning("动态层读取 merge 审核学习例子失败 error=%s", exc)
        return
    for item in prompt_memories or []:
        if not isinstance(item, dict):
            continue
        memory_id = str(ref_to_id.get(str(item.get("ref") or "").strip().upper()) or "").strip()
        feedback = feedback_by_id.get(memory_id)
        if isinstance(feedback, dict):
            item["review_feedback"] = feedback


def _rehydrate_round_recall_candidates(candidate_memory_ids: list[str], current_memories: list) -> list[dict]:
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for value in candidate_memory_ids or []:
        memory_id = str(value or "").strip()
        if not memory_id or memory_id in seen:
            continue
        seen.add(memory_id)
        ordered_ids.append(memory_id)

    dynamic_by_id = {
        str((memory or {}).get("id") or "").strip(): memory
        for memory in current_memories or []
        if isinstance(memory, dict) and str((memory or {}).get("id") or "").strip()
    }
    core_by_id: dict[str, dict] = {}
    if any(memory_id.startswith("core::") for memory_id in ordered_ids):
        try:
            from storage import r2_store

            for pending in r2_store.get_core_cache_pending() or []:
                if not isinstance(pending, dict):
                    continue
                core_id = str(pending.get("id") or "").strip()
                if not core_id:
                    continue
                memory_id = f"core::{core_id}"
                dynamic_base = dynamic_by_id.get(core_id) or {}
                core_memory = dict(pending)
                core_memory.update(
                    {
                        "id": memory_id,
                        "source_memory_id": str(pending.get("source_memory_id") or "").strip(),
                        "content": str(pending.get("content") or "").strip(),
                        "importance": int(pending.get("importance") or 0),
                        "mention_count": int(pending.get("mention_count") or 0),
                        "created_at": pending.get("created_at") or dynamic_base.get("created_at") or "",
                        "updated_at": pending.get("updated_at") or dynamic_base.get("updated_at") or dynamic_base.get("created_at") or "",
                        "last_mentioned": pending.get("last_mentioned") or dynamic_base.get("last_mentioned") or pending.get("promoted_at") or "",
                        "tag": str(pending.get("tag") or "").strip() or "图书馆",
                    }
                )
                core_by_id[memory_id] = core_memory
        except Exception as exc:
            logger.warning("动态层读取本轮核心候选失败 error=%s", exc)

    candidates: list[dict] = []
    for memory_id in ordered_ids:
        memory = core_by_id.get(memory_id) if memory_id.startswith("core::") else dynamic_by_id.get(memory_id)
        if isinstance(memory, dict):
            candidates.append(memory)
    return candidates


def _build_merge_candidate_metadata(memories: list, current_round_time: str) -> dict[str, dict]:
    current_dt = parse_iso_to_beijing(current_round_time)
    out: dict[str, dict] = {}
    for memory in memories or []:
        if not isinstance(memory, dict):
            continue
        memory_id = str(memory.get("id") or "").strip()
        if not memory_id:
            continue
        content_updated_at = str(memory.get("updated_at") or memory.get("created_at") or "").strip()
        updated_dt = parse_iso_to_beijing(content_updated_at)
        gap_hours = None
        if current_dt is not None and updated_dt is not None:
            gap_hours = round(max(0.0, (current_dt - updated_dt).total_seconds() / 3600.0), 2)
        out[memory_id] = {
            "tag": str(memory.get("tag") or "").strip(),
            "content_updated_at": content_updated_at,
            "merge_gap_hours": gap_hours,
        }
    return out


def _attach_merge_candidate_metadata(
    prompt_memories: list[dict],
    ref_to_id: dict[str, str],
    candidate_metadata: dict[str, dict],
) -> None:
    for item in prompt_memories or []:
        if not isinstance(item, dict):
            continue
        memory_id = ref_to_id.get(str(item.get("ref") or "").strip().upper())
        metadata = candidate_metadata.get(str(memory_id or ""))
        if not isinstance(metadata, dict):
            continue
        if metadata.get("content_updated_at"):
            item["content_updated_at"] = metadata["content_updated_at"]
        if metadata.get("merge_gap_hours") is not None:
            item["merge_gap_hours"] = metadata["merge_gap_hours"]


def _strip_json_fence(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _find_balanced_json_text(text: str, opener: str) -> str:
    """找第一个完整 JSON 对象/数组；忽略字符串里的括号。"""
    pairs = {"{": "}", "[": "]"}
    if opener not in pairs:
        return ""
    start = text.find(opener)
    if start < 0:
        return ""
    stack = [pairs[opener]]
    in_string = False
    escape = False
    for i in range(start + 1, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
            if not stack:
                return text[start : i + 1]
    return ""


def _json_loads_loose(raw: str) -> Any:
    if not raw:
        return None
    candidates = [
        raw.strip(),
        re.sub(r",\s*([}\]])", r"\1", raw.strip()),
    ]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _coerce_int_1_to_4(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return max(1, min(4, value))
    m = re.search(r"[1-4]", str(value or ""))
    if not m:
        return default
    return max(1, min(4, int(m.group(0))))


_FIELD_ALIASES = {
    "action": "action",
    "importance": "importance",
    "tag": "tag",
    "emotion": "emotion_label",
    "emotion_label": "emotion_label",
    "scene": "scene_type",
    "scene_type": "scene_type",
    "target": "target_type",
    "target_type": "target_type",
    "content": "content",
    "fused": "fused_with_id",
    "fused_with_id": "fused_with_id",
    "merge_reason": "merge_reason",
    "timestamp": "timestamp",
    "mention_count": "mention_count",
    "last_mentioned": "last_mentioned",
    "round": "round",
    "item": "item",
}


def _extract_decision_fields_from_text(text: str) -> Optional[dict]:
    """兜底解析固定标签/一行一个字段输出，避免格式小错导致整轮记忆丢失。"""
    raw_text = str(text or "").strip()
    out: dict[str, Any] = {}
    for line in raw_text.splitlines():
        m = re.match(r'^\s*"?([A-Za-z_]+)"?\s*[:：]\s*(.*?)\s*,?\s*$', line.strip())
        if not m:
            continue
        key = _FIELD_ALIASES.get(m.group(1).strip().lower())
        if not key:
            continue
        val = m.group(2).strip().rstrip(",").strip()
        if key in {"round", "item"}:
            continue
        if val in ("", "null", "None", "none"):
            out[key] = None
        elif key == "importance":
            out[key] = _coerce_int_1_to_4(val, default=0)
        elif key == "mention_count" and re.fullmatch(r"\d+", val):
            out[key] = int(val)
        elif len(val) >= 2 and val[0] in ("'", '"') and val[-1] == val[0]:
            out[key] = val[1:-1]
        else:
            out[key] = val
    if "action" not in out:
        lower = raw_text.lower()
        if re.search(r"\bskip\b|跳过|不记|不用记|无需记|没有值得记", lower):
            out["action"] = "skip"
        elif re.search(r"\bmerge\b|融合|合并", lower):
            out["action"] = "merge"
        elif re.search(r"\bnew\b|新记忆|新增|值得记|要记", lower):
            out["action"] = "new"
    if "tag" not in out:
        for tag in ("卧室", "书房", "图书馆", "客厅"):
            if tag in raw_text:
                out["tag"] = tag
                break
    if "importance" not in out:
        m = re.search(r"(?:importance|重要性|分数|评分)\s*[:：]?\s*([1-4])", raw_text, flags=re.IGNORECASE)
        if m:
            out["importance"] = m.group(1)
    if "content" not in out and out.get("action") in {"new", "merge"}:
        m = re.search(r"(?:content|记忆|内容|便签)\s*[:：]\s*(.+)", raw_text, flags=re.IGNORECASE)
        if m:
            out["content"] = m.group(1).strip().strip("'\"")
    return out if "action" in out else None


def _extract_json_from_ds_response(text: str) -> Optional[dict]:
    """
    从 DS 返回中剥离 markdown、前后缀，优先兼容旧 JSON，再解析固定标签格式。
    解析器会忽略字符串里的括号；一行一个字段也会尽量兜底解析。
    """
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "{")
    for raw in (balanced, text):
        obj = _json_loads_loose(raw)
        if isinstance(obj, dict):
            obj.pop("body_delta", None)
            return obj
    return _extract_decision_fields_from_text(text)


def _normalize_fused_with_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value) if value else None
    value = value.strip()
    if not value or value.lower() in ("null", "none"):
        return None
    if "仅 merge 时填写" in value:
        return None
    return value


def _normalize_merge_reason(value: Any) -> str:
    reason = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return reason if reason in _MERGE_REASONS else ""


def _resolve_fused_with_id(value: Any, ref_to_id: dict[str, str], valid_ids: set[str]) -> Optional[str]:
    """把 DS 输出的 M01/M1/ref 或兼容旧 UUID 映射成真实 memory id。"""
    fused = _normalize_fused_with_id(value)
    if not fused:
        return None
    if fused in valid_ids:
        return fused
    compact = _compact_ref_token(fused)
    if compact in ref_to_id:
        return ref_to_id[compact]
    m = re.search(r"\bM\s*0*(\d{1,3})\b", fused, flags=re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return ref_to_id.get(f"M{n:02d}") or ref_to_id.get(f"M{n}")
    return None


def _content_quality_issue(content: str) -> str:
    """拦截明显残缺的动态层便签。只拦低质量，不做语义裁判。"""
    raw = str(content or "").strip()
    text = re.sub(r"\s+", "", raw)
    if not text:
        return "missing_content"
    compact = re.sub(r"[，。！？、；：,.!?;:()（）【】\[\]{}《》\"'“”‘’…—\-_/\\|~`]+", "", text)
    if len(compact) < 12:
        return "content_too_short"
    if re.search(r"[，、；：,:;]$", raw):
        return "content_incomplete_tail"
    if re.search(
        r"(然后|但是|因为|所以|而且|并且|不过|只是|后来|接着|于是|结果|同时|另外|可是|但|可|却|跟|和|把|给|让|叫|问|说|表示|提到|觉得|想|要|准备|打算|发现|意识到|包括|比如|例如|直到|等到|还说|又说)$",
        compact,
    ):
        return "content_incomplete_tail"
    # 破折号可以是语气，不单独判残缺；只有它前面本身是“吊着没落地”的句式才拦。
    if re.search(r"(?:—|-|－){2,}\s*$", raw) and re.search(
        r"(然后|但是|因为|所以|而且|并且|不过|只是|后来|接着|于是|结果|同时|另外|可是|但|可|却|跟|和|把|给|让|叫|说了真心话|讲了真心话|说了句|说了一句|讲了句|问了句|问了一句|提到|表示|问|说)$",
        compact,
    ):
        return "content_incomplete_tail"
    for left, right in (("“", "”"), ("「", "」"), ("『", "』"), ("《", "》")):
        if raw.count(left) > raw.count(right):
            return "content_unclosed_quote"
    if raw.count('"') % 2 == 1 or raw.count("'") % 2 == 1:
        return "content_unclosed_quote"
    low_signal = {
        "记下了",
        "先记下",
        "测试一下",
        "动态层",
        "记忆",
        "老婆说",
        "辛玥说",
        "我知道了",
    }
    if compact in low_signal:
        return "content_too_generic"
    return ""


def _repair_incomplete_content_tail(content: str) -> str:
    """最终兜底：只清理明显没说完的尾巴，不扩写新事实。"""
    raw = str(content or "").strip()
    if not raw:
        return ""
    s = re.sub(r"(?:—|-|－){2,}\s*$", "", raw).strip()
    s = re.sub(
        r"(然后|但是|因为|所以|而且|并且|不过|只是|后来|接着|于是|结果|同时|另外|可是|但|可|却|跟|和|把|给|让|叫|问|说|表示|提到|觉得|想|要|准备|打算|发现|意识到|包括|比如|例如|直到|等到|还说|又说)\s*$",
        "",
        s,
    ).strip()
    s = s.rstrip("，、；：,:; ")
    if not s:
        return ""
    if not re.search(r"[。！？.!?]$", s):
        s += "。"
    return s if not _content_quality_issue(s) else ""


def _repair_decision_content_if_possible(obj: dict) -> str:
    if not isinstance(obj, dict):
        return ""
    action = str(obj.get("action") or "skip").strip().lower()
    if action not in ("new", "merge"):
        return ""
    content = str(obj.get("content") or "").strip()
    issue = _content_quality_issue(content)
    if issue not in ("content_incomplete_tail", "content_unclosed_quote"):
        return ""
    repaired = _repair_incomplete_content_tail(content)
    if repaired:
        obj["content"] = repaired
    return repaired


def _decision_structural_issue(obj: dict) -> str:
    action = str(obj.get("action") or "skip").strip().lower()
    content_text = str(obj.get("content") or "").strip()
    fused_with_id = _normalize_fused_with_id(obj.get("fused_with_id"))
    if action == "new" and not content_text:
        return "new_missing_content"
    if action == "merge" and not content_text and not fused_with_id:
        return "merge_missing_content_and_id"
    if action == "merge" and not _normalize_merge_reason(obj.get("merge_reason")):
        return "merge_missing_or_invalid_reason"
    if action in ("new", "merge"):
        if str(obj.get("tag") or "").strip() not in _VALID_MEMORY_TAGS:
            return "missing_or_invalid_tag"
        issue = _content_quality_issue(content_text)
        if issue:
            return issue
    return ""


def _normalize_for_raw_check(text: str) -> str:
    if not text:
        return ""
    normalized = str(text).lower()
    normalized = re.sub(r"\s+", "", normalized)
    return re.sub(r"[，。！？；：,.!?;:\"'“”‘’()（）\[\]{}<>《》\-_/\\|~`@#$%^&*+=]+", "", normalized)


def _looks_like_round_raw_copy(content: str, round_messages: list) -> bool:
    normalized_content = _normalize_for_raw_check(content)
    if not normalized_content or len(normalized_content) < 8:
        return False
    for message in round_messages or []:
        if not isinstance(message, dict):
            continue
        raw = message.get("content")
        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, list):
            text = " ".join(
                str(part.get("text") or "")
                for part in raw
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = ""
        normalized_source = _normalize_for_raw_check(text)
        if not normalized_source:
            continue
        if normalized_content == normalized_source:
            return True
        if len(normalized_content) >= 16 and normalized_content in normalized_source:
            return True
    return False


def _round_messages_from_batch_item(item: Any) -> list:
    if isinstance(item, dict):
        messages = item.get("messages")
        return messages if isinstance(messages, list) else []
    return item if isinstance(item, list) else []


def _extract_tagged_decision_blocks(text: str) -> Optional[list]:
    raw_text = _strip_json_fence(text)
    if not raw_text:
        return None
    lines = raw_text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    saw_marker = False
    for line in lines:
        if re.match(r"^\s*(?:ROUND|ITEM)\s*[:：]\s*\d+\s*$", line, flags=re.IGNORECASE):
            saw_marker = True
            if current:
                blocks.append("\n".join(current))
            current = [line]
            continue
        if re.match(r"^\s*-{3,}\s*$", line) and current:
            blocks.append("\n".join(current))
            current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))

    parsed: list[dict] = []
    for block in blocks:
        obj = _extract_decision_fields_from_text(block)
        if isinstance(obj, dict):
            parsed.append(obj)
    if parsed and (saw_marker or len(parsed) > 1):
        return parsed
    return None


def _extract_json_array_from_ds_response(text: str) -> Optional[list]:
    """从 DS 返回中解析旧 JSON 数组或新的固定标签块。"""
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "[")
    for raw in (balanced, text):
        arr = _json_loads_loose(raw)
        if isinstance(arr, list):
            return arr
    tagged = _extract_tagged_decision_blocks(text)
    if isinstance(tagged, list):
        return tagged
    return None


def _memory_decision_round_messages(round_messages: list) -> list[dict]:
    """只传 role/content，并把思路正文归一为 thinking；协议元数据不进入动态记忆判断。"""
    out: list[dict] = []
    for message in round_messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = message.get("content")
        if not role or content is None:
            continue
        item = {"role": role, "content": content}
        thoughts: list[str] = []

        def _append_thought(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in thoughts:
                thoughts.append(text)

        _append_thought(message.get("reasoning"))
        blocks = message.get("thinking_blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict) or str(block.get("type") or "").strip() != "thinking":
                    continue
                _append_thought(block.get("thinking") or block.get("text"))
        if thoughts:
            item["thinking"] = "\n".join(thoughts)
        out.append(item)
    return out


def _multi_decision_issues(
    arr: Any,
    round_messages: list,
    ref_to_id: dict[str, str],
    valid_ids: set[str],
    candidate_metadata: dict[str, dict] | None = None,
    merge_locked_ids: set[str] | None = None,
) -> list[dict]:
    issues: list[dict] = []
    if not isinstance(arr, list):
        return [{"index": 0, "issue": "items_parse_failed", "content": ""}]
    if not arr:
        return [{"index": 0, "issue": "items_empty", "content": ""}]
    merged_ids: set[str] = set()
    for idx, obj in enumerate(arr):
        if not isinstance(obj, dict):
            issues.append({"index": idx + 1, "issue": "decision_not_object", "content": ""})
            continue
        issue = _decision_structural_issue(obj)
        action = str(obj.get("action") or "").strip().lower()
        resolved_id = None
        if not issue and action == "merge":
            resolved_id = _resolve_fused_with_id(obj.get("fused_with_id"), ref_to_id, valid_ids)
            if not resolved_id:
                issue = "merge_missing_or_invalid_ref"
            elif resolved_id in (merge_locked_ids or set()):
                issue = "merge_target_locked"
            elif resolved_id in merged_ids:
                issue = "duplicate_merge_target"
            else:
                merged_ids.add(resolved_id)
        if not issue and action == "merge" and resolved_id:
            metadata = (candidate_metadata or {}).get(resolved_id) or {}
            source_tag = str(metadata.get("tag") or "").strip()
            output_tag = str(obj.get("tag") or "").strip()
            try:
                gap_hours = float(metadata.get("merge_gap_hours"))
            except (TypeError, ValueError):
                gap_hours = None
            merge_reason = _normalize_merge_reason(obj.get("merge_reason"))
            if (
                "卧室" in {source_tag, output_tag}
                and gap_hours is not None
                and gap_hours > _BEDROOM_CONTINUOUS_MERGE_MAX_GAP_HOURS
                and merge_reason not in {"correction", "habit_generalization"}
            ):
                issue = "bedroom_cross_day_merge_disallowed"
        if (
            not issue
            and action in ("new", "merge")
            and _looks_like_round_raw_copy(str(obj.get("content") or ""), round_messages)
        ):
            issue = "content_raw_copy"
        if issue:
            issues.append(
                {
                    "index": idx + 1,
                    "issue": issue,
                    "action": action,
                    "content": str(obj.get("content") or "").strip(),
                }
            )
    return issues


def _two_stage_items_from_content(content: str) -> Optional[list]:
    obj = _extract_json_from_ds_response(content)
    if not isinstance(obj, dict):
        return None
    items = obj.get("items")
    return items if isinstance(items, list) else None


def _message_evidence_text(message: dict, field: str) -> str:
    value = message.get(field)
    if isinstance(value, str):
        return value
    if field == "content" and isinstance(value, list):
        return " ".join(
            str(part.get("text") or "")
            for part in value
            if isinstance(part, dict) and part.get("type") == "text"
        )
    if value in (None, ""):
        return ""
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _source_evidence_issues(value: Any, round_messages: list, *, required: bool) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list):
        return ["source_evidence_not_array"]
    if required and not value:
        return ["source_evidence_missing"]

    issues: list[str] = []
    for evidence in value:
        if not isinstance(evidence, dict):
            issues.append("source_evidence_not_object")
            continue
        message_index = evidence.get("message_index")
        field = str(evidence.get("field") or "").strip()
        quote = str(evidence.get("quote") or "").strip()
        if isinstance(message_index, bool) or not isinstance(message_index, int):
            issues.append("source_evidence_invalid_message_index")
            continue
        if message_index < 0 or message_index >= len(round_messages):
            issues.append("source_evidence_invalid_message_index")
            continue
        if field not in {"content", "thinking"}:
            issues.append("source_evidence_invalid_field")
            continue
        if not quote:
            issues.append("source_evidence_empty_quote")
            continue
        source_text = _message_evidence_text(round_messages[message_index], field)
        if not source_text or quote not in source_text:
            issues.append("source_evidence_quote_not_found")
    return issues


def _normalize_source_evidence(value: Any, round_messages: list) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    for evidence in value if isinstance(value, list) else []:
        if not isinstance(evidence, dict):
            continue
        message_index = evidence.get("message_index")
        field = str(evidence.get("field") or "").strip()
        quote = str(evidence.get("quote") or "").strip()
        if isinstance(message_index, bool) or not isinstance(message_index, int):
            continue
        if message_index < 0 or message_index >= len(round_messages):
            continue
        if field not in {"content", "thinking"} or not quote:
            continue
        if quote not in _message_evidence_text(round_messages[message_index], field):
            continue
        key = (message_index, field, quote)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "message_index": message_index,
                "role": str(round_messages[message_index].get("role") or "").strip(),
                "field": field,
                "quote": quote,
            }
        )
    return out


def _decision_plan_issues(
    items: Any,
    round_messages: list,
    ref_to_id: dict[str, str],
    valid_ids: set[str],
    candidate_metadata: dict[str, dict],
    merge_locked_ids: set[str],
) -> list[dict]:
    if not isinstance(items, list):
        return [{"index": 0, "issue": "decision_items_parse_failed"}]
    if not items:
        return [{"index": 0, "issue": "decision_items_empty"}]

    issues: list[dict] = []
    item_ids: set[str] = set()
    merged_ids: set[str] = set()
    actionable_evidence: list[tuple[int, str, list[dict]]] = []
    for idx, item in enumerate(items):
        issue = ""
        if not isinstance(item, dict):
            issues.append({"index": idx + 1, "issue": "decision_not_object"})
            continue
        item_id = str(item.get("item_id") or "").strip()
        action = str(item.get("action") or "").strip().lower()
        if not item_id:
            issue = "missing_item_id"
        elif item_id in item_ids:
            issue = "duplicate_item_id"
        else:
            item_ids.add(item_id)
        if not issue and not str(item.get("item_brief") or "").strip():
            issue = "missing_item_brief"
        if not issue and action not in {"new", "merge", "skip"}:
            issue = "invalid_action"
        if not issue:
            evidence_issues = _source_evidence_issues(
                item.get("source_evidence"),
                round_messages,
                required=action in {"new", "merge"},
            )
            if evidence_issues:
                issue = evidence_issues[0]
        if not issue and action in {"new", "merge"}:
            if str(item.get("tag") or "").strip() not in _VALID_MEMORY_TAGS:
                issue = "missing_or_invalid_tag"
            elif _coerce_int_1_to_4(item.get("importance"), default=0) <= 0:
                issue = "missing_or_invalid_importance"
        if not issue and action == "merge":
            merge_reason = _normalize_merge_reason(item.get("merge_reason"))
            resolved_id = _resolve_fused_with_id(item.get("fused_with_id"), ref_to_id, valid_ids)
            if not merge_reason:
                issue = "merge_missing_or_invalid_reason"
            elif not resolved_id:
                issue = "merge_missing_or_invalid_ref"
            elif resolved_id in merge_locked_ids:
                issue = "merge_target_locked"
            elif resolved_id in merged_ids:
                issue = "duplicate_merge_target"
            else:
                merged_ids.add(resolved_id)
                metadata = candidate_metadata.get(resolved_id) or {}
                try:
                    gap_hours = float(metadata.get("merge_gap_hours"))
                except (TypeError, ValueError):
                    gap_hours = None
                if (
                    "卧室" in {str(metadata.get("tag") or "").strip(), str(item.get("tag") or "").strip()}
                    and gap_hours is not None
                    and gap_hours > _BEDROOM_CONTINUOUS_MERGE_MAX_GAP_HOURS
                    and merge_reason not in {"correction", "habit_generalization"}
                ):
                    issue = "bedroom_cross_day_merge_disallowed"
        if issue:
            issues.append(
                {
                    "index": idx + 1,
                    "item_id": item_id,
                    "action": action,
                    "issue": issue,
                }
            )
        elif action in {"new", "merge"}:
            actionable_evidence.append(
                (
                    idx + 1,
                    item_id,
                    _normalize_source_evidence(item.get("source_evidence"), round_messages),
                )
            )

    for left_index in range(len(actionable_evidence)):
        left_item_index, left_item_id, left_evidence = actionable_evidence[left_index]
        for right_item_index, right_item_id, right_evidence in actionable_evidence[left_index + 1 :]:
            overlap_found = False
            for left in left_evidence:
                for right in right_evidence:
                    if (
                        left.get("message_index") != right.get("message_index")
                        or left.get("field") != right.get("field")
                    ):
                        continue
                    left_quote = str(left.get("quote") or "")
                    right_quote = str(right.get("quote") or "")
                    if left_quote and right_quote and (
                        left_quote == right_quote
                        or left_quote in right_quote
                        or right_quote in left_quote
                    ):
                        overlap_found = True
                        break
                if overlap_found:
                    break
            if overlap_found:
                issues.append(
                    {
                        "index": right_item_index,
                        "item_id": right_item_id,
                        "action": str(items[right_item_index - 1].get("action") or "").strip().lower(),
                        "issue": "source_evidence_cross_item_overlap",
                        "conflicts_with_index": left_item_index,
                        "conflicts_with_item_id": left_item_id,
                    }
                )
    return issues


def _normalize_decision_plan(
    items: list,
    round_messages: list,
    ref_to_id: dict[str, str],
    valid_ids: set[str],
    candidate_metadata: dict[str, dict],
) -> list[dict]:
    plans: list[dict] = []
    for item in items:
        action = str(item.get("action") or "skip").strip().lower()
        fused_with_ref = _normalize_fused_with_id(item.get("fused_with_id")) if action == "merge" else None
        fused_with_id = (
            _resolve_fused_with_id(fused_with_ref, ref_to_id, valid_ids)
            if action == "merge"
            else None
        )
        metadata = candidate_metadata.get(str(fused_with_id or "")) or {}
        try:
            merge_gap_hours = float(metadata.get("merge_gap_hours"))
        except (TypeError, ValueError):
            merge_gap_hours = None
        tag = str(item.get("tag") or "").strip()
        plans.append(
            {
                "item_id": str(item.get("item_id") or "").strip(),
                "item_brief": str(item.get("item_brief") or "").strip(),
                "source_evidence": _normalize_source_evidence(item.get("source_evidence"), round_messages),
                "tag": tag,
                "action": action,
                "importance": _coerce_int_1_to_4(item.get("importance"), default=0),
                "content": "",
                "fused_with_id": fused_with_id,
                "fused_with_ref": fused_with_ref,
                "merge_reason": _normalize_merge_reason(item.get("merge_reason")) if action == "merge" else "",
                "emotion_label": str(item.get("emotion_label") or "").strip().lower(),
                "scene_type": str(item.get("scene_type") or "").strip(),
                "target_type": str(item.get("target_type") or "").strip(),
                "merge_gap_hours": metadata.get("merge_gap_hours"),
                "merge_source_tag": str(metadata.get("tag") or ""),
                "bedroom_cross_day": bool(
                    merge_gap_hours is not None
                    and merge_gap_hours > _BEDROOM_CONTINUOUS_MERGE_MAX_GAP_HOURS
                    and "卧室" in {str(metadata.get("tag") or "").strip(), tag}
                ),
            }
        )
    return plans


def _writing_prompt_items(
    plans: list[dict],
    candidates: list[dict],
) -> list[dict]:
    memories_by_id = {
        str(memory.get("id") or "").strip(): memory
        for memory in candidates
        if isinstance(memory, dict) and str(memory.get("id") or "").strip()
    }

    out: list[dict] = []
    for plan in plans:
        if plan.get("action") not in {"new", "merge"}:
            continue
        item = {
            "item_id": plan.get("item_id"),
            "action": plan.get("action"),
            "importance": plan.get("importance"),
            "tag": plan.get("tag"),
            "emotion_label": plan.get("emotion_label"),
            "scene_type": plan.get("scene_type"),
            "target_type": plan.get("target_type"),
            "fused_with_id": plan.get("fused_with_id"),
            "merge_reason": plan.get("merge_reason") or None,
            "source_evidence": plan.get("source_evidence") or [],
            "original_content": None,
        }
        if plan.get("action") == "merge":
            memory = memories_by_id.get(str(plan.get("fused_with_id") or ""))
            item["original_content"] = str((memory or {}).get("content") or "").strip()
        out.append(item)
    return out


def _writing_result_issues(
    items: Any,
    expected_ids: list[str],
    round_messages: list,
) -> list[dict]:
    if not isinstance(items, list):
        return [{"index": 0, "issue": "writing_items_parse_failed"}]
    issues: list[dict] = []
    seen: set[str] = set()
    expected = set(expected_ids)
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append({"index": idx + 1, "issue": "writing_item_not_object"})
            continue
        item_id = str(item.get("item_id") or "").strip()
        content = str(item.get("content") or "").strip()
        issue = ""
        if not item_id:
            issue = "missing_item_id"
        elif item_id in seen:
            issue = "duplicate_item_id"
        elif item_id not in expected:
            issue = "unexpected_item_id"
        else:
            seen.add(item_id)
        if not issue:
            issue = _content_quality_issue(content)
        if not issue and _looks_like_round_raw_copy(content, round_messages):
            issue = "content_raw_copy"
        if issue:
            issues.append({"index": idx + 1, "item_id": item_id, "issue": issue})
    missing = [item_id for item_id in expected_ids if item_id not in seen]
    if missing:
        issues.append({"index": 0, "issue": "missing_writing_items", "item_ids": missing})
    return issues


def _dynamic_layer_stage_worker(provider: str, model_variant: str) -> WorkerModelSpec:
    base = get_worker_model("background_reasoning", provider=provider)
    provider_key = str(base.provider or provider or "").strip().lower()
    model = {
        ("opencode_go", "pro"): "deepseek-v4-pro",
        ("opencode_go", "flash"): "deepseek-v4-flash",
        ("siliconflow", "pro"): "deepseek-ai/DeepSeek-V4-Pro",
        ("siliconflow", "flash"): "deepseek-ai/DeepSeek-V4-Flash",
    }.get((provider_key, str(model_variant or "").strip().lower()))
    if not model:
        raise ValueError(f"unsupported dynamic layer worker variant: {provider_key}/{model_variant}")
    return WorkerModelSpec(
        role=str(base.role or "background_reasoning"),
        provider=provider_key,
        protocol=str(getattr(base, "protocol", "openai_chat") or "openai_chat"),
        api_url=str(base.api_url or ""),
        api_key=str(base.api_key or ""),
        model=model,
    )


def _post_dynamic_layer_stage(
    worker: Any,
    prompt: str,
    *,
    stage: str,
    disable_thinking: bool,
    read_timeout_seconds: int,
    on_http_attempt: Optional[Callable[[bool], None]] = None,
) -> str:
    payload: dict[str, Any] = {
        "model": worker.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
    }
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    response = None
    for attempt_index in range(4):
        if on_http_attempt is not None:
            on_http_attempt(attempt_index > 0)
        response = requests.post(
            worker.api_url,
            headers={"Authorization": f"Bearer {worker.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(60, read_timeout_seconds),
        )
        if response.status_code not in {500, 502, 503, 504} or attempt_index == 3:
            break
        logger.warning(
            "动态层 DS provider=%s %s API 第%s次请求返回可重试状态 status=%s，同请求最多重试三次",
            worker.provider,
            stage,
            attempt_index + 1,
            response.status_code,
        )
    assert response is not None
    if response.status_code >= 400:
        logger.error(
            "动态层 DS %s API 错误 status=%s body=%s",
            stage,
            response.status_code,
            (response.text or "")[:800],
        )
    response.raise_for_status()
    data = response.json()
    record_response_usage(role=worker.role, provider=worker.provider, model=worker.model, data=data)
    return str((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def _post_dynamic_layer_stage_with_fallback(
    primary_worker: Any,
    prompt: str,
    *,
    stage: str,
    disable_thinking: bool,
    model_variant: str,
    read_timeout_seconds: int,
    prefer_fallback: bool = False,
    on_http_attempt: Optional[Callable[[str, bool, bool], None]] = None,
) -> tuple[str, str, bool]:
    def _attempt_callback(worker: Any, *, is_fallback: bool) -> Callable[[bool], None]:
        def _register(is_retry: bool) -> None:
            if on_http_attempt is not None:
                on_http_attempt(str(worker.provider or ""), is_retry, is_fallback)

        return _register

    if prefer_fallback:
        fallback_worker = _dynamic_layer_stage_worker("siliconflow", model_variant)
        content = _post_dynamic_layer_stage(
            fallback_worker,
            prompt,
            stage=stage,
            disable_thinking=disable_thinking,
            read_timeout_seconds=read_timeout_seconds,
            on_http_attempt=_attempt_callback(fallback_worker, is_fallback=True),
        )
        return content, str(fallback_worker.provider or ""), True

    try:
        content = _post_dynamic_layer_stage(
            primary_worker,
            prompt,
            stage=stage,
            disable_thinking=disable_thinking,
            read_timeout_seconds=read_timeout_seconds,
            on_http_attempt=_attempt_callback(primary_worker, is_fallback=False),
        )
        return content, str(primary_worker.provider or ""), False
    except requests.RequestException as primary_error:
        fallback_worker = _dynamic_layer_stage_worker("siliconflow", model_variant)
        if not fallback_worker.api_key or not fallback_worker.api_url:
            raise
        logger.warning(
            "动态层 DS %s primary provider=%s 请求失败，切换 fallback provider=%s error_type=%s",
            stage,
            primary_worker.provider,
            fallback_worker.provider,
            type(primary_error).__name__,
        )
        content = _post_dynamic_layer_stage(
            fallback_worker,
            prompt,
            stage=stage,
            disable_thinking=disable_thinking,
            read_timeout_seconds=read_timeout_seconds,
            on_http_attempt=_attempt_callback(fallback_worker, is_fallback=True),
        )
        return content, str(fallback_worker.provider or ""), True


def call_dynamic_layer_ds(
    round_messages: list,
    current_memories: list,
    *,
    window_id: str = "",
    round_index: int | None = None,
    candidate_memory_ids: Optional[list[str]] = None,
    query_topic_state: Optional[dict] = None,
) -> list[dict]:
    """
    实时动态层两阶段：先拆事项并决定 new/merge/skip，再按事项分别生成可写正文。
    第一阶段不覆盖 provider 的默认 thinking 行为；第二阶段显式关闭 thinking。
    任一事项的正文阶段无效都不返回可写决策，避免部分正文进入现有逐条应用层。
    """
    default = {
        "tag": "",
        "action": "skip",
        "importance": 0,
        "content": "",
        "fused_with_id": None,
        "merge_reason": "",
        "emotion_label": "",
        "scene_type": "",
        "target_type": "",
    }

    decision_round_messages = _memory_decision_round_messages(round_messages)
    decision_worker = _dynamic_layer_stage_worker("opencode_go", "pro")
    if not decision_worker.api_key or not decision_worker.api_url:
        return [default]

    # 直接复用主聊天本轮 reranker 前宽候选池，不再执行第二套向量召回。
    # 这里只传 ID，并在执行时从当前动态/核心记忆重新取正文，避免使用过期快照。
    candidates = _rehydrate_round_recall_candidates(list(candidate_memory_ids or []), current_memories)

    current_round_time = now_beijing_iso()
    prompt_memories, ref_to_id, valid_ids = _build_memory_ref_prompt_items(candidates)
    merge_locked_ids = _merge_locked_memory_ids(candidates)
    candidate_metadata = _build_merge_candidate_metadata(candidates, current_round_time)
    _attach_merge_candidate_metadata(prompt_memories, ref_to_id, candidate_metadata)
    _attach_merge_review_feedback(prompt_memories, ref_to_id)
    decision_prompt = _DYNAMIC_LAYER_DECISION_PROMPT.format(
        current_round_time=current_round_time,
        current_memories_json=json.dumps(prompt_memories or [], ensure_ascii=False),
        round_messages_json=json.dumps(decision_round_messages or [], ensure_ascii=False),
        query_topic_state_json=json.dumps(query_topic_state or {}, ensure_ascii=False),
    )
    if not prompt_memories:
        decision_prompt += (
            "\n\n【本轮候选状态】\n"
            "当前没有可用的旧记忆候选，因此 action 只能是 new 或 skip，禁止 merge，"
            "fused_with_id 与 merge_reason 必须为 null。"
        )

    stage_records: list[dict] = []
    http_request_count = 0
    http_retry_count = 0
    fallback_request_count = 0
    fallback_retry_count = 0
    provider_request_counts: dict[str, int] = {}
    provider_retry_counts: dict[str, int] = {}
    fallback_pinned = False
    active_stage = "decision"

    def register_http_attempt(provider: str, is_retry: bool, is_fallback: bool) -> None:
        nonlocal http_request_count, http_retry_count, fallback_request_count, fallback_retry_count
        provider_key = str(provider or "unknown")
        http_request_count += 1
        provider_request_counts[provider_key] = provider_request_counts.get(provider_key, 0) + 1
        if is_fallback:
            fallback_request_count += 1
        if is_retry:
            http_retry_count += 1
            provider_retry_counts[provider_key] = provider_retry_counts.get(provider_key, 0) + 1
            if is_fallback:
                fallback_retry_count += 1

    def emit_audit(status: str, results: list[dict], issue: str = "") -> None:
        primary = next((item for item in results if item.get("action") in {"new", "merge"}), results[0])
        _emit_dynamic_ds_audit_event(
            {
                "source": "single_items_two_stage",
                "window_id": window_id,
                "round_index": round_index,
                "round_preview": _round_messages_preview(decision_round_messages),
                "final_status": status,
                "final_action": primary.get("action") or "skip",
                "final_tag": primary.get("tag") or "",
                "final_importance": primary.get("importance") or 0,
                "final_content": primary.get("content") or "",
                "final_fused_with_id": primary.get("fused_with_id"),
                "final_merge_reason": primary.get("merge_reason") or "",
                "final_issue": issue,
                "final_decisions": [
                    {
                        "action": item.get("action"),
                        "tag": item.get("tag"),
                        "importance": item.get("importance"),
                        "content": item.get("content"),
                        "fused_with_id": item.get("fused_with_id"),
                        "merge_reason": item.get("merge_reason"),
                        "merge_gap_hours": item.get("merge_gap_hours"),
                        "bedroom_cross_day": item.get("bedroom_cross_day"),
                    }
                    for item in results
                ],
                "action_counts": _decision_action_counts(results),
                "request_count": http_request_count,
                "attempt_count": http_request_count,
                "http_retry_count": http_retry_count,
                "provider_request_counts": dict(provider_request_counts),
                "provider_retry_counts": dict(provider_retry_counts),
                "fallback_request_count": fallback_request_count,
                "fallback_retry_count": fallback_retry_count,
                "fallback_pinned": fallback_pinned,
                "stage_count": len(stage_records),
                "retry_count": 0,
                "stages": stage_records,
            }
        )

    try:
        decision_content, decision_provider, decision_used_fallback = _post_dynamic_layer_stage_with_fallback(
            decision_worker,
            decision_prompt,
            stage="decision",
            disable_thinking=False,
            model_variant="pro",
            read_timeout_seconds=240,
            prefer_fallback=fallback_pinned,
            on_http_attempt=register_http_attempt,
        )
        fallback_pinned = fallback_pinned or decision_used_fallback
        decision_items = _two_stage_items_from_content(decision_content)
        decision_issues = _decision_plan_issues(
            decision_items,
            decision_round_messages,
            ref_to_id,
            valid_ids,
            candidate_metadata,
            merge_locked_ids,
        )
        stage_records.append(
            {
                "stage": "decision",
                "provider": decision_provider,
                "parsed": isinstance(decision_items, list),
                "issue": "; ".join(str(item.get("issue") or "") for item in decision_issues[:5]),
                "preview": _one_line_preview(decision_content),
            }
        )
        if decision_issues:
            issue = stage_records[-1]["issue"]
            logger.warning("动态层 DS 决策阶段输出无效 issues=%s preview=%s", issue, _one_line_preview(decision_content))
            emit_audit("failed_decision", [default], issue)
            return [default]

        plans = _normalize_decision_plan(
            decision_items or [],
            decision_round_messages,
            ref_to_id,
            valid_ids,
            candidate_metadata,
        )
        actionable_plans = [plan for plan in plans if plan.get("action") in {"new", "merge"}]
        if not actionable_plans:
            results = [_normalize_single_decision(plan) for plan in plans] or [default]
            emit_audit("skip", results)
            return results

        writing_items = _writing_prompt_items(plans, candidates)
        if any(item.get("action") == "merge" and not str(item.get("original_content") or "").strip() for item in writing_items):
            issue = "merge_original_memory_missing"
            stage_records.append({"stage": "writing_precheck", "parsed": False, "issue": issue})
            emit_audit("failed_writing", [default], issue)
            return [default]

        writing_by_item_id = {
            str(item.get("item_id") or "").strip(): item
            for item in writing_items
            if isinstance(item, dict) and str(item.get("item_id") or "").strip()
        }
        content_by_item_id: dict[str, str] = {}
        original_content_by_item_id: dict[str, str] = {}
        writing_worker = _dynamic_layer_stage_worker("opencode_go", "flash")
        for plan in actionable_plans:
            item_id = str(plan.get("item_id") or "").strip()
            writing_item = writing_by_item_id.get(item_id)
            if not isinstance(writing_item, dict):
                issue = "writing_item_missing"
                stage_records.append(
                    {"stage": "writing_precheck", "item_id": item_id, "parsed": False, "issue": issue}
                )
                emit_audit("failed_writing", [default], issue)
                return [default]
            writing_prompt = _DYNAMIC_LAYER_WRITING_PROMPT.format(
                writing_items_json=json.dumps([writing_item], ensure_ascii=False),
            )
            active_stage = f"writing:{item_id}"
            writing_content, writing_provider, writing_used_fallback = _post_dynamic_layer_stage_with_fallback(
                writing_worker,
                writing_prompt,
                stage=active_stage,
                disable_thinking=True,
                model_variant="flash",
                read_timeout_seconds=180,
                prefer_fallback=fallback_pinned,
                on_http_attempt=register_http_attempt,
            )
            fallback_pinned = fallback_pinned or writing_used_fallback
            writing_results = _two_stage_items_from_content(writing_content)
            writing_issues = _writing_result_issues(
                writing_results,
                [item_id],
                decision_round_messages,
            )
            stage_records.append(
                {
                    "stage": "writing",
                    "item_id": item_id,
                    "provider": writing_provider,
                    "parsed": isinstance(writing_results, list),
                    "issue": "; ".join(str(item.get("issue") or "") for item in writing_issues[:5]),
                    "preview": _one_line_preview(writing_content),
                }
            )
            if writing_issues:
                issue = stage_records[-1]["issue"]
                logger.warning(
                    "动态层 DS 正文阶段输出无效 item_id=%s issues=%s preview=%s",
                    item_id,
                    issue,
                    _one_line_preview(writing_content),
                )
                emit_audit("failed_writing", [default], issue)
                return [default]
            writing_result = (writing_results or [])[0]
            content_by_item_id[item_id] = str(writing_result.get("content") or "").strip()
            if plan.get("action") == "merge":
                original_content_by_item_id[item_id] = str(writing_item.get("original_content") or "")

        results: list[dict] = []
        for plan in plans:
            normalized_input = dict(plan)
            if plan.get("action") in {"new", "merge"}:
                normalized_input["content"] = content_by_item_id.get(str(plan.get("item_id") or ""), "")
            result = _normalize_single_decision(normalized_input)
            if plan.get("action") == "merge":
                result["_merge_original_content"] = original_content_by_item_id.get(
                    str(plan.get("item_id") or ""),
                    "",
                )
            result["merge_gap_hours"] = plan.get("merge_gap_hours")
            result["merge_source_tag"] = plan.get("merge_source_tag") or ""
            result["bedroom_cross_day"] = bool(plan.get("bedroom_cross_day"))
            results.append(result)

        if any(result.get("action") not in {"new", "merge", "skip"} for result in results):
            issue = "materialized_decision_invalid"
            emit_audit("failed_writing", [default], issue)
            return [default]
        emit_audit("ok", results)
        return results
    except Exception as e:
        logger.error("动态层 DS %s 阶段调用失败 error=%s", active_stage, e, exc_info=True)
        stage_records.append(
            {
                "stage": active_stage,
                "parsed": False,
                "issue": str(e),
            }
        )
        emit_audit("api_error", [default], f"{active_stage}:{e}")
        return [default]


def _normalize_single_decision(obj: Any) -> dict:
    """把 DS 返回的单条对象规范成网关用的 decision dict。"""
    default = {
        "tag": "",
        "action": "skip",
        "importance": 0,
        "content": "",
        "fused_with_id": None,
        "merge_reason": "",
        "emotion_label": "",
        "scene_type": "",
        "target_type": "",
    }
    if not isinstance(obj, dict):
        return default
    tag = (obj.get("tag") or "").strip()
    action = (obj.get("action") or "skip").strip().lower()
    action = action if action in ("new", "merge", "skip") else "skip"
    importance = _coerce_int_1_to_4(obj.get("importance"), default=0)
    content_text = (obj.get("content") or "").strip()
    fused_with_id = obj.get("fused_with_id")
    merge_reason = _normalize_merge_reason(obj.get("merge_reason")) if action == "merge" else ""
    emotion_label = str(obj.get("emotion_label") or "").strip().lower()
    scene_type = str(obj.get("scene_type") or "").strip()
    target_type = str(obj.get("target_type") or "").strip()
    if fused_with_id is not None and not isinstance(fused_with_id, str):
        fused_with_id = str(fused_with_id) if fused_with_id else None
    elif fused_with_id is not None and not fused_with_id.strip():
        fused_with_id = None
    if action in ("new", "merge"):
        issue = _content_quality_issue(content_text)
        if issue:
            logger.warning("动态层 DS batch 单条内容不完整，按 skip 处理 issue=%s preview=%s", issue, _one_line_preview(content_text))
            action = "skip"
            content_text = ""
            fused_with_id = None
            merge_reason = ""
    return {
        "tag": tag,
        "action": action,
        "importance": importance,
        "content": content_text,
        "fused_with_id": fused_with_id,
        "merge_reason": merge_reason,
        "emotion_label": emotion_label if emotion_label in ("positive", "negative", "neutral") else "neutral",
        "scene_type": scene_type,
        "target_type": target_type,
        "timestamp": obj.get("timestamp"),
        "last_mentioned": obj.get("last_mentioned"),
        "mention_count": obj.get("mention_count"),
    }


def _decision_action_counts(decisions: list) -> dict:
    counts = {"new": 0, "merge": 0, "skip": 0, "other": 0}
    for item in decisions or []:
        action = str((item or {}).get("action") if isinstance(item, dict) else "").strip().lower()
        if action in counts:
            counts[action] += 1
        else:
            counts["other"] += 1
    return counts


def _batch_structural_issues(arr: Any, expected_len: int, batch_rounds: list | None = None) -> list[dict]:
    issues: list[dict] = []
    if not isinstance(arr, list):
        return [{"index": 0, "issue": "batch_parse_failed", "content": ""}]
    if len(arr) != expected_len:
        issues.append({"index": 0, "issue": f"batch_length_mismatch:{len(arr)}!={expected_len}", "content": ""})
    for idx, obj in enumerate(arr[:expected_len]):
        if not isinstance(obj, dict):
            issues.append({"index": idx + 1, "issue": "decision_not_object", "content": ""})
            continue
        issue = _decision_structural_issue(obj)
        if (
            not issue
            and str(obj.get("action") or "").strip().lower() in ("new", "merge")
            and batch_rounds
            and idx < len(batch_rounds)
            and _looks_like_round_raw_copy(
                str(obj.get("content") or ""),
                _round_messages_from_batch_item(batch_rounds[idx]),
            )
        ):
            issue = "content_raw_copy"
        if issue:
            issues.append(
                {
                    "index": idx + 1,
                    "issue": issue,
                    "action": str(obj.get("action") or "").strip().lower(),
                    "content": str(obj.get("content") or "").strip(),
                }
            )
    return issues


def _repair_batch_content_tails(arr: Any) -> list[dict]:
    repairs: list[dict] = []
    if not isinstance(arr, list):
        return repairs
    for idx, obj in enumerate(arr):
        if not isinstance(obj, dict):
            continue
        repaired = _repair_decision_content_if_possible(obj)
        if repaired:
            repairs.append({"index": idx + 1, "content": repaired})
    return repairs


def call_dynamic_layer_ds_batch(batch_rounds: list, current_memories: list) -> list:
    """
    一次请求处理多轮：把多轮对话发给 DS，解析出决策列表，与 batch_rounds 一一对应。
    本批内只做 new/skip（prompt 已约束不 merge 本批内新记忆）。
    """
    if not batch_rounds:
        return []
    worker = get_worker_model("background_reasoning", provider="opencode_go")
    if not worker.api_key or not worker.api_url:
        return [_normalize_single_decision(None) for _ in batch_rounds]

    prompt_memories, _ref_to_id, _valid_ids = _build_memory_ref_prompt_items(current_memories or [])
    rounds_batch_json = json.dumps(batch_rounds or [], ensure_ascii=False)
    prompt = _DYNAMIC_LAYER_BATCH_PROMPT.format(
        current_memories_json=json.dumps(prompt_memories or [], ensure_ascii=False),
        rounds_batch_json=rounds_batch_json,
    )
    headers = {"Authorization": f"Bearer {worker.api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": worker.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }
    attempts: list[dict] = []
    try:
        for attempt in range(_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS):
            request_payload = payload
            if attempt > 0:
                last_issue = attempts[-1].get("issue") if attempts else ""
                last_content = attempts[-1].get("content") if attempts else ""
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                            + _dynamic_layer_retry_instruction(str(last_issue or ""), str(last_content or ""), batch=True),
                        }
                    ],
                }
            r = requests.post(worker.api_url, headers=headers, json=request_payload, timeout=(120, 180))
            r.raise_for_status()
            data = r.json()
            record_response_usage(role=worker.role, provider=worker.provider, model=worker.model, data=data)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            arr = _extract_json_array_from_ds_response(content)
            repairs = _repair_batch_content_tails(arr) if attempt == _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1 else []
            issues = _batch_structural_issues(arr, len(batch_rounds), batch_rounds)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "parsed": isinstance(arr, list),
                    "issue": "; ".join(f"#{x.get('index')}:{x.get('issue')}" for x in issues[:5]),
                    "content": _one_line_preview((issues[0].get("content") if issues else "") or content, limit=220),
                    "action_counts": _decision_action_counts(arr if isinstance(arr, list) else []),
                    "repairs": repairs,
                }
            )
            if issues:
                logger.warning(
                    "动态层 DS batch 输出未达标 attempt=%s issues=%s",
                    attempt + 1,
                    attempts[-1].get("issue"),
                )
                if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                    continue
                _emit_dynamic_ds_audit_event(
                    {
                        "source": "batch",
                        "batch_size": len(batch_rounds),
                        "final_status": "failed_incomplete",
                        "final_action": "skip",
                        "final_issue": attempts[-1].get("issue"),
                        "attempt_count": len(attempts),
                        "retry_count": max(0, len(attempts) - 1),
                        "attempts": attempts,
                    }
                )
                return [_normalize_single_decision(None) for _ in batch_rounds]
            out = [_normalize_single_decision(x) for x in arr]
            _emit_dynamic_ds_audit_event(
                {
                    "source": "batch",
                    "batch_size": len(batch_rounds),
                    "final_status": "ok",
                    "action_counts": _decision_action_counts(out),
                    "attempt_count": len(attempts),
                    "retry_count": max(0, len(attempts) - 1),
                    "attempts": attempts,
                }
            )
            return out
    except Exception as e:
        logger.error("动态层 DS batch 调用失败 error=%s", e, exc_info=True)
        _emit_dynamic_ds_audit_event(
            {
                "source": "batch",
                "batch_size": len(batch_rounds),
                "final_status": "api_error",
                "final_action": "skip",
                "final_issue": str(e),
                "attempt_count": len(attempts),
                "retry_count": max(0, len(attempts) - 1),
                "attempts": attempts,
            }
        )
        return [_normalize_single_decision(None) for _ in batch_rounds]


# ---------- 归档脚本专用：读 scripts/archive_ds_prompt.txt，批处理一次请求 ----------
_ARCHIVE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "archive_ds_prompt.txt"


def _load_archive_batch_prompt_template() -> str:
    """归档脚本批处理用 prompt，占位符 current_memories_json、rounds_batch_json。"""
    if not _ARCHIVE_PROMPT_PATH.exists():
        logger.warning("归档 prompt 文件不存在 path=%s，将回退网关批处理 prompt", _ARCHIVE_PROMPT_PATH)
        return _DYNAMIC_LAYER_BATCH_PROMPT
    try:
        return _ARCHIVE_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取归档 prompt 失败 path=%s error=%s，将回退网关批处理 prompt", _ARCHIVE_PROMPT_PATH, e)
        return _DYNAMIC_LAYER_BATCH_PROMPT


def call_archive_batch_ds(batch_rounds: list, current_memories: list) -> list:
    """
    归档脚本批处理：用 scripts/archive_ds_prompt.txt 一次请求多轮，解析出决策列表。
    与 call_dynamic_layer_ds_batch 同逻辑，仅 prompt 来源不同。
    """
    if not batch_rounds:
        return []
    worker = get_worker_model("background_reasoning", provider="opencode_go")
    if not worker.api_key or not worker.api_url:
        return [_normalize_single_decision(None) for _ in batch_rounds]

    template = _load_archive_batch_prompt_template()
    # 只传最近 N 条记忆，避免单次请求超 131072 context（current_memories 会越积越多）
    _ARCHIVE_MEMORIES_MAX = 50
    memories_for_prompt = (current_memories or [])[-_ARCHIVE_MEMORIES_MAX:]
    # 每轮对话截断到最多 2500 字再发给 DS，避免单批 6 轮合起来超长
    _MAX_CHARS_PER_ROUND = 2500
    rounds_for_prompt = []
    for r in batch_rounds or []:
        if not isinstance(r, dict):
            rounds_for_prompt.append(r)
            continue
        msgs = r.get("messages") or []
        parts = []
        n = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            s = (m.get("content") or "").strip()
            if not s:
                continue
            if n + len(s) > _MAX_CHARS_PER_ROUND:
                s = s[: max(0, _MAX_CHARS_PER_ROUND - n)] + "…"
            parts.append({"role": m.get("role", "user"), "content": s})
            n += len(s)
            if n >= _MAX_CHARS_PER_ROUND:
                break
        rounds_for_prompt.append({"round_timestamp": r.get("round_timestamp") or "", "messages": parts})
    prompt = template.replace(
        "{current_memories_json}", json.dumps(memories_for_prompt, ensure_ascii=False)
    ).replace(
        "{rounds_batch_json}", json.dumps(rounds_for_prompt, ensure_ascii=False)
    )
    headers = {"Authorization": f"Bearer {worker.api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": worker.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }
    last_err: Exception | None = None
    attempts: list[dict] = []
    final_failure_status = "api_error"
    for attempt in range(_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS):
        try:
            request_payload = payload
            if attempt > 0 and attempts and attempts[-1].get("issue"):
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                            + _dynamic_layer_retry_instruction(
                                str(attempts[-1].get("issue") or ""),
                                str(attempts[-1].get("content") or ""),
                                batch=True,
                            ),
                        }
                    ],
                }
            r = requests.post(worker.api_url, headers=headers, json=request_payload, timeout=(120, 180))
            if r.status_code >= 400:
                logger.error(
                    "归档 DS API 错误 status=%s body=%s",
                    r.status_code,
                    (r.text or "")[:800],
                )
            r.raise_for_status()
            data = r.json()
            record_response_usage(role=worker.role, provider=worker.provider, model=worker.model, data=data)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            arr = _extract_json_array_from_ds_response(content)
            repairs = _repair_batch_content_tails(arr) if attempt == _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1 else []
            issues = _batch_structural_issues(arr, len(batch_rounds), batch_rounds)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "parsed": isinstance(arr, list),
                    "issue": "; ".join(f"#{x.get('index')}:{x.get('issue')}" for x in issues[:5]),
                    "content": _one_line_preview((issues[0].get("content") if issues else "") or content, limit=220),
                    "action_counts": _decision_action_counts(arr if isinstance(arr, list) else []),
                    "repairs": repairs,
                }
            )
            if issues:
                logger.warning(
                    "归档 DS batch 输出未达标 attempt=%s issues=%s",
                    attempt + 1,
                    attempts[-1].get("issue"),
                )
                if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                    continue
                last_err = RuntimeError("归档 DS 本批输出仍有残缺记忆，不写断点以便下次重跑")
                final_failure_status = "failed_incomplete"
                break
            out = [_normalize_single_decision(x) for x in arr]
            _emit_dynamic_ds_audit_event(
                {
                    "source": "archive_batch",
                    "batch_size": len(batch_rounds),
                    "final_status": "ok",
                    "action_counts": _decision_action_counts(out),
                    "attempt_count": len(attempts),
                    "retry_count": max(0, len(attempts) - 1),
                    "attempts": attempts,
                }
            )
            return out
        except Exception as e:
            last_err = e
            logger.warning("归档 DS batch 第 %s 次失败 error=%s", attempt + 1, e)
            if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                time.sleep(2)
    _emit_dynamic_ds_audit_event(
        {
            "source": "archive_batch",
            "batch_size": len(batch_rounds),
            "final_status": final_failure_status,
            "final_action": "retry_later",
            "final_issue": str(last_err or ""),
            "attempt_count": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
            "attempts": attempts,
        }
    )
    logger.error("归档 DS batch 调用失败（已重试 %s 次） error=%s", _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS, last_err, exc_info=True)
    raise RuntimeError("归档 DS 本批请求失败，不写断点以便重跑从本批重试") from last_err
