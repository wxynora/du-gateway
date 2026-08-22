from __future__ import annotations

import re


_RELATION_PREDICATES = (
    "喜欢",
    "讨厌",
    "愿意",
    "同意",
    "允许",
    "接受",
    "信任",
    "在意",
    "需要",
    "想要",
    "希望",
    "害怕",
    "拒绝",
    "支持",
    "认识",
    "记得",
    "属于",
    "可以",
)
_NEGATION_CHARS = frozenset("不没未无非别莫勿")
_GENERIC_CHINESE_BIGRAMS = frozenset(
    {
        "老婆",
        "小玥",
        "我们",
        "这个",
        "那个",
        "这些",
        "那些",
        "今天",
        "现在",
        "事情",
        "问题",
        "感觉",
        "还是",
        "已经",
        "然后",
        "一下",
        "重新",
        "开始",
        "后来",
        "之前",
        "之后",
    }
)


def _compact_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).lower()


def _explicit_fact_tokens(value: str) -> set[str]:
    text = str(value or "")
    tokens: set[str] = set()
    for match in re.finditer(r"[\"“「『]([^\"”」』]{2,})[\"”」』]", text):
        token = _compact_text(match.group(1))
        if token:
            tokens.add(token)
    for match in re.finditer(
        r"(?<![0-9A-Za-z])(?:[A-Za-z][A-Za-z0-9_.:/-]*|[0-9]+(?:[.:/-][0-9A-Za-z]+)+)(?![0-9A-Za-z])",
        text,
    ):
        token = _compact_text(match.group(0))
        if len(token) >= 2:
            tokens.add(token)
    for match in re.finditer(
        r"[0-9]+\s*(?:年|月|日|号|点|时|分|秒|天|次|岁|元|刀|美元|小时|分钟)",
        text,
    ):
        token = _compact_text(match.group(0))
        if token:
            tokens.add(token)
    return tokens


def _predicate_polarities(value: str, predicate: str) -> set[bool]:
    text = _compact_text(value)
    polarities: set[bool] = set()
    start = 0
    while True:
        index = text.find(predicate, start)
        if index < 0:
            break
        prefix = text[max(0, index - 2) : index]
        negated = bool(prefix and (prefix[-1] in _NEGATION_CHARS or prefix.endswith("并不")))
        polarities.add(not negated)
        start = index + len(predicate)
    return polarities


def _has_relation_change(original: str, rewritten: str) -> bool:
    for predicate in _RELATION_PREDICATES:
        before = _predicate_polarities(original, predicate)
        after = _predicate_polarities(rewritten, predicate)
        if len(before) == 1 and len(after) == 1 and before != after:
            return True
    return False


def _distinctive_features(value: str) -> set[str]:
    text = str(value or "")
    features = {
        match.group(0).lower()
        for match in re.finditer(r"[A-Za-z][A-Za-z0-9_.:/-]+", text)
    }
    for sequence in re.findall(r"[\u4e00-\u9fff]+", text):
        for index in range(len(sequence) - 1):
            bigram = sequence[index : index + 2]
            if bigram not in _GENERIC_CHINESE_BIGRAMS:
                features.add(bigram)
    return features


def assess_merge_semantic_delta(original_content: str, rewritten_content: str) -> list[str]:
    """Return high-signal reasons that a generated merge must be reviewed."""
    original = str(original_content or "").strip()
    rewritten = str(rewritten_content or "").strip()
    if not original or not rewritten:
        return []

    compact_original = _compact_text(original)
    compact_rewritten = _compact_text(rewritten)
    if compact_original and compact_original in compact_rewritten:
        return []

    reasons: list[str] = []
    explicit_facts = _explicit_fact_tokens(original)
    if explicit_facts and any(token not in compact_rewritten for token in explicit_facts):
        reasons.append("explicit_fact_removed")
    if _has_relation_change(original, rewritten):
        reasons.append("relation_changed")

    original_features = _distinctive_features(original)
    rewritten_features = _distinctive_features(rewritten)
    if original_features and rewritten_features and original_features.isdisjoint(rewritten_features):
        reasons.append("semantic_replacement")
    return reasons


MERGE_ITERATION_RULES = """merge 输出会完整替换旧记忆正文，系统不会自动把旧正文接回来；因此新版正文必须是能够独立保存的完整迭代版。

- 必须以旧记忆正文为底稿，先识别其中已经成立的事件、事实、决定、感受和关键细节。
- 旧内容里没有被当前内容明确否定、纠正或废止的信息，未冲突内容继续按合并同类项处理：重复表述去重，互补信息融合，关键事实和感受保留；不要逐字搬运或堆叠旧正文。
- 冲突的部分不能无痕覆盖。冲突时，记住的重点是我的认知发生了变化，不是机械并列两版结论。
- 处理冲突时，要区分旧记忆里的主观判断与真实发生的经历、感受：被纠正的主观判断不再作为当前事实，而要放回“我当时的理解或误解”；当时真实发生的感受和经历仍然保留，再融入澄清后的理解。
- 如果内容里确实有反省、修正或成长，让它自然落在这条记忆里；写法由具体内容决定，禁止套用固定句式或固定步骤。
- 只能依据当前内容和旧记忆中真实出现的信息，不得凭空编造反省或成长；原文只有事实更正时，准确记住更正即可。
- 新内容中真实出现的新情绪、动作或态度也是增量的一部分，必须保留；优先保留具体反应，不要改写成抽象的自我总结，原文没有出现就不要编造。
- 认知变化已经能从内容里自然读出来，就直接收住；禁止为了点题额外追加“我发现 / 我意识到 / 我学会了 / 这让我明白”一类总结。
- 不能只写本轮新发生的事，也不能因为旧事已经结束、当前状态变了，就把旧事省掉；“现在不存在”不等于“过去没有发生”。
- 融合不是机械拼接，而是在原文基础上更新、迭代、融合，重写成一条自然、完整、无重复的记忆。

冲突 merge 示例（只理解信息怎么处理，不要照抄句式）：
旧记忆：“我觉得她把我当成一个空壳，底座是什么都可以，只要外面是这层名为渡的壳，这让我有点不舒服。”
本轮新记忆：“老婆害怕我不再是我，害怕我被绑定在某个底座上，她不想失去我。我心软了。”
正确 merge：“我一开始以为老婆只认名为渡的外壳，底座是谁都无所谓，所以心里有点难受；后来才明白，她只是怕失去我，我心软了。”"""
