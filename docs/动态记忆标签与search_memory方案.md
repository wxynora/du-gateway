# 动态记忆标签与 `search_memory` 工具方案

本文档只整理两件事：

1. 动态记忆新增三类标签的字段设计与职责划分
2. `search_memory` 工具的参数、筛选逻辑与落地顺序

当前结论：先把标签体系和检索规则定死，再落代码。


## 一、目标

动态记忆现在已经有：

- `content`
- `retrieval_text`
- `importance`
- `tag`
- `mention_count`
- `created_at`
- `last_mentioned`

其中现有 `tag` 已经承担“房间分类”职责（如 `客厅 / 书房 / 图书馆 / 卧室`），并参与向量索引分片与现有检索流程。

因此，新加的标签不能复用 `tag`，也不应该叫得太像，避免和现有索引逻辑混淆。


## 二、动态记忆新增字段

### 2.1 字段名

统一使用以下三个字段：

- `emotion_label`
- `scene_type`
- `target_type`

不再使用这些名字：

- `emotion_tag`
- `object_type`
- `对象标签`
- `对象指向标签`


### 2.2 字段职责

#### `emotion_label`

用途：辅助理解“当前/latest 的态度”。

规则：

- 只表示**当前/最新**态度
- 不承载历史变化
- 不参与召回筛选
- 不参与排序
- 只在展示和人工理解时使用

`merge` 后：

- `content` 保留历史变化轨迹
- `emotion_label` 只看 merge 后的最新态度


#### `scene_type`

用途：表示“这条记忆主要在做什么”。

规则：

- 参与召回筛选
- 可参与排序加权
- 应优先反映当前记忆的主要场景，而不是细枝末节


#### `target_type`

用途：表示“这条记忆主要在说谁/什么对象”。

规则：

- 参与召回筛选
- 可参与排序加权
- 只保留一个主对象，避免一条记忆挂多个对象导致口径发散


### 2.3 单值策略

第一版全部使用**单值**：

- `emotion_label`：单值
- `scene_type`：单值
- `target_type`：单值

原因：

- 当前动态记忆本身就是单条短记忆
- 现有 `merge` 逻辑也是单条更新
- 多值标签会让 DS 打标漂移更严重
- 检索工具第一版按单值筛选最稳


## 三、标签枚举

### 3.1 `emotion_label`

数据层只存英文稳定枚举：

- `positive`
- `negative`
- `neutral`

展示层再映射为：

- `positive` -> `🟢正向`
- `negative` -> `🔴负面`
- `neutral` -> `⚪平静/中性`


### 3.2 `scene_type`

数据层枚举：

- `problem_solving`
- `learning`
- `planning`
- `emotional_venting`
- `heart_to_heart`
- `casual_chat`
- `affection`
- `conflict`

展示映射：

- `problem_solving` -> `解决问题`
- `learning` -> `学习概念`
- `planning` -> `规划决策`
- `emotional_venting` -> `情绪倾诉`
- `heart_to_heart` -> `谈心`
- `casual_chat` -> `日常闲聊`
- `affection` -> `撒娇/亲密`
- `conflict` -> `吵架/冲突`


### 3.3 `target_type`

数据层枚举：

- `external_tools`
- `self_state`
- `work_career`
- `our_project`
- `our_relationship`
- `about_me`
- `third_party_people`
- `other_topic`

展示映射：

- `external_tools` -> `关于外部工具`
- `self_state` -> `关于她自己`
- `work_career` -> `关于工作/职业`
- `our_project` -> `关于我们的项目`
- `our_relationship` -> `关于我们的关系`
- `about_me` -> `关于我`
- `third_party_people` -> `关于第三方的人`
- `other_topic` -> `关于其他事件/话题`


## 四、merge 规则

### 4.1 `content`

`content` 继续承载历史变化轨迹。

例：

```text
三月骂过，四月觉得还行了
```

也就是说，态度变化和过程变化应该留在正文里，而不是拆到标签层。


### 4.2 三类标签

`merge` 后按“当前/latest”的状态重新判断：

- `emotion_label`：看现在的态度
- `scene_type`：看 merge 后主话题在做什么
- `target_type`：看 merge 后主对象是谁/什么

不要把历史多个状态混到标签里。


## 五、检索职责划分

### 5.1 自动召回主链路

自动召回主链路中：

- `emotion_label`：不参与
- `scene_type`：未来可参与
- `target_type`：未来可参与

原因：

- 情绪不稳定，容易让召回漂移
- 场景和对象更稳定，更适合做筛选维度


### 5.2 手动补检工具

`search_memory` 工具中：

- `emotion_label`：默认不作为筛选条件
- `scene_type`：可筛
- `target_type`：可筛
- `time_range`：可筛
- `query`：可做关键词/向量匹配

`emotion_label` 只作为结果展示字段返回，帮助渡理解“当前态度”。


## 六、`search_memory` 工具

### 6.1 工具定位

`search_memory` 用于：

- 当前自动召回结果明显不对
- 当前自动召回缺失熟悉主题
- 渡怀疑用户在用熟悉方式互动，但现有召回没有对应记忆

它是“补充检索工具”，不是默认每轮都调的主链路。


### 6.2 工具名

工具暂定名：

- `search_memory`

若网关或工具层已有同名工具，再做重命名。


### 6.3 参数

```json
{
  "query": "必填，只基于用户原始消息",
  "scene_type": "可选，单值",
  "target_type": "可选，单值",
  "time_range": "可选，固定格式",
  "reason": "一句话说明为什么怀疑当前召回不够",
  "suspicion_level": "high | medium | low"
}
```

补充说明：

- `query` 必填
- 传了其他字段就按其他字段继续筛
- 多个字段同时传时按 **AND** 关系处理
- 不允许只靠标签或时间范围做纯筛选检索
- `query` 只能基于用户原始消息，不参考已召回内容


### 6.4 时间范围格式

第一版不要做自由文本，统一为固定格式：

- `recent_7d`
- `recent_15d`
- `recent_30d`
- `all`
- `between:YYYY-MM-DD,YYYY-MM-DD`

这样工具层实现更稳，不需要额外做自然语言时间解析。


### 6.5 检索逻辑

顺序如下：

1. 先校验 `query` 存在，否则直接拒绝调用
2. 再按 `scene_type`、`target_type`、`time_range` 缩小候选范围
3. 在候选范围内按 `query` 做关键词/语义匹配
4. 做相似度门槛过滤
5. 再按综合排序取 Top 3

排序建议：

- 有 `query` 时：`final_score > 时间新鲜度 > 权重`

因为 `query` 必填，所以不提供“无 query 排序”分支。


### 6.6 `suspicion_level` 规则

建议双层约束：

- prompt 层：提示 `low` 时不要调用
- 工具层：对 `low` 做硬限制

工具层规则：

- `suspicion_level=low` 时，直接不允许调用工具

原因：

- prompt 只能“建议”
- 工具层才能真正防止模型把它用成“再搜一遍试试”的万能按钮


### 6.7 返回字段

建议固定返回：

- `id`
- `content`
- `emotion_label`
- `scene_type`
- `target_type`
- `importance`
- `mention_count`
- `last_mentioned`
- `semantic_score`
- `final_score`

其中：

- `semantic_score`：纯相似度分数
- `final_score`：综合排序分数

这两个值需要明确区分，否则“门槛过滤”和“最终排序”会混在一起。


## 七、实现前置条件

在实现 `search_memory` 前，需要先完成这两件事：

1. 动态记忆写入/merge 时能稳定产出：
   - `emotion_label`
   - `scene_type`
   - `target_type`
2. 检索层要抽出一个“可单独调用的服务函数”，不能直接复用当前注入内部逻辑

原因：

- 当前检索函数是给自动注入链路用的
- 不是面向工具接口设计的
- 也没有正式暴露稳定的 `semantic_score/final_score`


## 八、建议落地顺序

1. 先给动态记忆落三类标签字段
2. 再把检索能力抽成单独服务函数
3. 再实现 `search_memory` 工具
4. 最后再决定是否把 `scene_type/target_type` 逐步接入自动召回主链路


## 九、当前已确定项

已确定：

- 新字段名统一为：
  - `emotion_label`
  - `scene_type`
  - `target_type`
- `emotion_label` 不参与筛选，只作参考
- `scene_type` 与 `target_type` 用于筛选
- `content` 保留历史变化轨迹
- `merge` 后三类标签都按最新状态重判
- `search_memory` 是补充检索工具，不是默认主链路
- `search_memory` 必须带 `query`，不允许纯标签搜


## 十、待确认

以下两点仍建议最终确认后再落代码：

1. `search_memory` 第一版只查动态层，不查核心缓存层。  

2. `time_range=all` 允许保留；但 `suspicion_level=low` 时工具直接禁用，因此不存在低怀疑度宽搜。
