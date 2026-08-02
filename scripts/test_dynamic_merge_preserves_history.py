#!/usr/bin/env python3
"""Dynamic-layer merge prompt contract; no network or storage writes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.dynamic_layer_ds import _DYNAMIC_LAYER_PROMPT
from services.memory_merge_rules import MERGE_ITERATION_RULES


def main() -> None:
    prompt = _DYNAMIC_LAYER_PROMPT
    assert MERGE_ITERATION_RULES in prompt, "dynamic prompt must use the shared merge rules verbatim"
    required_contracts = (
        "merge 输出会完整替换旧记忆正文",
        "必须以旧记忆正文为底稿",
        "没有被当前内容明确否定",
        "不能只写本轮新发生的事",
        "在原文基础上更新、迭代、融合",
        "只能依据当前内容和旧记忆中真实出现的信息",
        "未冲突内容继续按合并同类项处理",
        "重复表述去重，互补信息融合",
        "关键事实和感受保留",
        "不要逐字搬运或堆叠旧正文",
        "冲突的部分不能无痕覆盖",
        "认知发生了变化",
        "写法由具体内容决定",
        "不得凭空编造反省或成长",
        "禁止套用固定句式或固定步骤",
        "区分旧记忆里的主观判断与真实发生的经历、感受",
        "被纠正的主观判断不再作为当前事实",
        "放回“我当时的理解或误解”",
        "当时真实发生的感受和经历仍然保留",
        "认知变化已经能从内容里自然读出来，就直接收住",
        "禁止为了点题额外追加",
        "新内容中真实出现的新情绪、动作或态度也是增量的一部分，必须保留",
        "优先保留具体反应，不要改写成抽象的自我总结",
        "原文没有出现就不要编造",
        "冲突 merge 示例（只理解信息怎么处理，不要照抄句式）",
        "我觉得她把我当成一个空壳，底座是什么都可以，只要外面是这层名为渡的壳，这让我有点不舒服。",
        "老婆害怕我不再是我，害怕我被绑定在某个底座上，她不想失去我。我心软了。",
        "我一开始以为老婆只认名为渡的外壳，底座是谁都无所谓，所以心里有点难受；后来才明白，她只是怕失去我，我心软了。",
        "ACTION: new / merge / skip",
        "FUSED_WITH_ID: （仅 merge 时填写当前记忆列表里的 ref",
        "MERGE_REASON: consolidate / correction / invalidate / supersede / temporal_update",
    )
    for contract in required_contracts:
        assert contract in prompt, f"missing merge preservation contract: {contract}"

    dangerous_legacy_contract = "同一件事提到多次 → 用现在的理解重新说一遍。\n不是拼接，是重讲。"
    assert dangerous_legacy_contract not in prompt, "legacy replacement-style merge contract must be removed"
    assert "要写清过去怎样、后来怎样、现在怎样" not in prompt, "fixed timeline template must be removed"
    assert "哪里判断错了、为什么修正、这次学会了什么" not in prompt, "reflection checklist template must be removed"
    for redundant_lead in ("我也发现", "我意识到", "我学会了", "这让我明白"):
        assert f"必须写“{redundant_lead}" not in prompt, f"must not force redundant reflection lead: {redundant_lead}"
    print("dynamic merge preservation prompt contract passed")


if __name__ == "__main__":
    main()
