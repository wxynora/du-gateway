# 共同游戏活动时间方案（已落地）

> 落地状态（2026-07-13）：方案已由 `4a3ea528`、`58f1b82e` 等提交实现并部署。本文保留设计边界和验收口径；当前实现与部署结果以 `docs/DEBUG_INDEX.md` 的“chat / 共同游戏活动时间拆分”记录为准。

## 1. 目标

解决两个彼此独立的问题：

1. 唤醒判断需要知道小玥最近是否真实参与过互动，聊天和共同游戏都应刷新这个时间。
2. 给渡看的时间描述必须说清最近发生的是聊天还是共同游戏；共同游戏还必须带具体游戏名。

目标说法：

- 最近是聊天：保留当前聊天间隔说法，不改 chat 文案。
- 最近是共同游戏：`老婆 X 分钟前和我在玩涩涩走格棋。`
- 换成其他共同游戏时，显示对应的真实游戏名。

## 2. 当前实现核对

现在实际有两套职责不同的时间：

1. `data/last_user_reply.json` 中的 `last_user_reply_at`
   - 由 `pipeline.step_inject_summary()` 读取。
   - 用于生成当前的“老婆多久没回”提示。
   - 它是跨窗口共享的本地 chat 时间，不是 R2 的统一互动时间。
2. R2 的 `global/last_user_activity_at.txt`
   - 由主动唤醒、睡眠判断、PixelHome 等链路读取。
   - 它是统一互动时间，只负责“最近有没有真实用户互动”。

因此不需要把 R2 拆成三套时钟。最小改法是：

- 保留 R2 统一互动时间及全部现有读取方。
- 保留本地 chat 时间。
- 在同一个本地活动记录中新增“最近共同游戏活动”。
- 共同游戏活动同时刷新 R2 统一互动时间。

## 3. 数据结构

兼容扩展现有 `data/last_user_reply.json`：

```json
{
  "last_user_reply_at": "2026-07-13T20:10:00+08:00",
  "last_shared_game_activity": {
    "at": "2026-07-13T22:55:00+08:00",
    "game_id": "private_board",
    "game_name": "涩涩走格棋",
    "source": "private_board_sync_du"
  }
}
```

约束：

- 保留 `last_user_reply_at` 字段，旧数据无需迁移。
- `game_name` 只能来自后端受信映射，不能接受前端自由传值。
- 未知 `game_id`、缺少名称或非共同游戏一律拒绝记录，不能退化成含糊的“在玩游戏”。
- 不从旧 R2 审计倒推游戏时间，避免把历史上的部分写入误判成完整游戏活动。

## 4. 公共入口

新增一个小型公共服务，例如 `services/user_activity_context.py`，只负责：

```python
mark_shared_game_user_activity(
    game_id="private_board",
    occurred_at=synced_at,
    source="private_board_sync_du",
    detail={...},
)
```

该入口完成两件事，并使用同一个 `occurred_at`：

1. 写本地 `last_shared_game_activity`，供时间描述使用。
2. 写现有 R2 `last_user_activity_at`，供唤醒和其他统一互动判断使用。

共同游戏采用显式白名单，而不是“所有 game tool 都算”：

```python
SHARED_GAME_ACTIVITY_NAMES = {
    "private_board": "涩涩走格棋",
    "captivity_simulator": "囚禁模拟器",
}
```

以后新增共同游戏时，只需：

1. 在白名单登记稳定的 `game_id -> 展示名`。
2. 在明确代表小玥参与的入口调用公共函数。

植物大战丧尸随机版不在白名单中，即使它也注册在 game runtime，也不能刷新共同游戏时间或统一互动时间。

## 5. 写入时机

### 5.1 普通聊天

保留现有顺序：

1. 先读取上一次 chat / 共同游戏记录，计算当前这轮要注入的间隔。
2. 再把 `last_user_reply_at` 更新为当前时间。

不能把 chat 时间提前写，否则当前每轮都会计算成 0 分钟，原有“多久没回”语义会被破坏。

真实 chat 输入必须覆盖 Telegram、SumiTalk、QQ、微信等共用窗口入口；内部 follow-up、维护请求、游戏工具回合不能冒充 chat。

`routes/chat.py` 不能继续只把 `X-TG-User-Input` 当作本地 chat 时间的唯一依据。应复用现有跨平台真实输入判定，把 Telegram header 与 SumiTalk/QQ/微信等真实用户输入合并成一个 `real_user_input`，再交给活动上下文服务。否则 R2 统一时间虽然更新，`last_user_reply_at` 仍可能漏掉 SumiTalk。

### 5.2 共同游戏

共同游戏在一次用户参与请求通过基本校验后、调用渡之前记录：

1. 校验游戏状态、同步内容和目标窗口有效。
2. 调用 `mark_shared_game_user_activity()`。
3. 再调用渡。

这样当前游戏回合不会继续看到陈旧的 chat 间隔。即使渡本次生成失败，小玥刚刚参与游戏这一事实也仍然成立，不回滚活动时间。

同一请求里由渡触发的后续回合、自动续跑和服务端 follow-up 不重复记时。

## 6. 哪些算，哪些不算

| 场景 | chat 时间 | 共同游戏时间 | R2 统一互动时间 |
| --- | --- | --- | --- |
| 小玥发送普通聊天 | 更新 | 不更新 | 更新 |
| 小玥在涩涩走格棋发言或同步棋局 | 不更新 | 更新为“涩涩走格棋” | 更新 |
| 小玥在囚禁模拟器发言或执行明确的用户操作 | 不更新 | 更新为“囚禁模拟器” | 更新 |
| 渡在共同游戏里自动行动/自动续跑 | 不更新 | 不更新 | 不更新 |
| 服务端重试、状态轮询、只读 status/open | 不更新 | 不更新 | 不更新 |
| 渡自己玩植物大战丧尸随机版 | 不更新 | 不更新 | 不更新 |
| 打开游戏大厅、读取预览 | 不更新 | 不更新 | 不更新 |
| 非共同游戏的其他 MiniApp 操作 | 不更新 | 不更新 | 按原逻辑，不由本方案扩大 |

当前游戏接入判断：

- `private_board`：属于共同游戏。每次有效 `/sync-du` 代表一次共同游戏同步；服务端内部 follow-up 不算第二次。
- `captivity_simulator`：属于共同游戏。局内 chat，或明确 `user_initiated=true` 的操作同步才算；后台状态推进不算。
- `random_imitator_td`：渡自己玩的游戏，明确排除。
- `wenyou`：当前没有共同游戏 `sync-du` 契约，本方案不擅自接入；以后只有在它出现明确的“小玥与渡共同参与”入口时再登记。

## 7. 时间描述选择

统一读取：

- `last_user_reply_at`
- `last_shared_game_activity.at`

选择时间较新的有效记录：

- chat 较新：沿用当前 chat 间隔文案和阈值，不改写。
- 共同游戏较新：使用 `老婆 {gap_text}前和我在玩{game_name}。`

例子：

```text
老婆 12 分钟前和我在玩涩涩走格棋。
老婆 1 小时20分钟前和我在玩囚禁模拟器。
```

默认继续沿用当前 `REPLY_GAP_THRESHOLD_MINUTES=30`：不足阈值时不额外注入间隔句。若产品语义要求游戏分支无论多久都显示，需要单独确认后再改，不能在本次顺手改变阈值。

主动唤醒中的描述也要使用同一个“最新 chat / 共同游戏”选择器，不能继续把 R2 统一互动时间一律描述成“她上次明确回复”。但唤醒调度本身仍只读 R2 统一互动时间，不改算法。

## 8. 并发、失败与兼容

### 并发

- 当前 `last_user_reply.json` 是直接读写，chat 与游戏同时到达时可能互相覆盖。
- 公共服务应使用进程内锁做一次完整的 read-modify-write，并用临时文件原子替换。
- 当前 `scripts/start_gateway_prod.sh` 默认并强制封顶为 1 个 gunicorn worker、多个线程，进程内锁在现有生产配置下有效。
- 不引入数据库或分布式锁；如果以后解除 `GATEWAY_WORKERS_MAX=1`，必须先把这份记录迁到 SQLite 或增加跨进程文件锁，不能直接扩大 worker 数。

### 失败

- 本地活动记录失败：记录 warning；不能让游戏同步本身 500。
- R2 统一时间写入失败：记录现有审计/日志；不能覆盖或删除本地共同游戏记录。
- 非法/未知共同游戏：拒绝记录并记 warning，不写任何时间。
- 时间无法解析：忽略该候选，不用坏值覆盖有效记录。

### 兼容

- 旧 `last_user_reply.json` 只有 `last_user_reply_at` 时继续正常工作。
- 新字段缺失时保持当前 chat 行为。
- 不改 R2 `get_last_user_activity_at()` 的接口，现有唤醒、睡眠、PixelHome 消费者无需跟着改。
- 不改前端协议；当前已有的后端 `game_id`、`mode`、`user_initiated` 足够判断。
- 不修改开源 `game-box`：这里是私有 Gateway 的渡联动活动上下文，不属于通用游戏规则。若以后开源版也需要宿主回调，应另做可选接口，不能带入“小玥/老婆/渡”的私有语义。

## 9. 预计文件范围

落地阶段预计只涉及：

- `services/user_activity_context.py`：本地 chat / 共同游戏记录、选择和文案数据。
- `pipeline/pipeline.py`：用公共选择器替换当前直接读写 JSON；保留 chat 原文案和写入顺序。
- `routes/miniapp/game_tools.py`：在共同游戏的用户参与入口调用公共函数。
- `storage/r2_store.py`：只增加一个通用 `shared_game_user_interaction` 白名单 source，具体游戏放在 audit detail。
- `services/telegram_proactive.py`：描述最近互动时区分 chat / 具体共同游戏；调度时间读取不变。
- `scripts/test_private_board_game.py`、`scripts/test_captivity_simulator_game.py`：接入时机测试。
- 新增一个纯本地活动上下文测试文件，覆盖选择、兼容、并发写入和错误数据。
- `docs/DEBUG_INDEX.md`：只有方案获批并完成落地验证后才更新。

走格棋现有 `_mark_private_board_pending_created_activity()` 只覆盖部分命令，且会与新的 `/sync-du` 记录形成双入口。落地时应先全项目扫引用，再取消它对活动时间的写入，由有效 `/sync-du` 统一记时；游戏状态逻辑本身不动。

不涉及：

- MiniApp 前端和构建产物。
- 游戏规则、存档、指令解析、消息展示。
- `game-box` 开源仓库。
- 唤醒间隔算法和其他 R2 消费者。

## 10. 验证清单

纯本地测试必须 mock R2 和所有上游调用，不能写共享云状态。

1. 旧 JSON 只有 chat 字段时，行为与当前一致。
2. chat 比游戏新时，选择 chat 文案。
3. 游戏比 chat 新时，输出具体游戏名。
4. 未知游戏、植物大战丧尸随机版不能写任何活动时间。
5. 涩涩走格棋有效同步在渡调用前写游戏时间和 R2 统一时间。
6. 囚禁模拟器仅 chat 或 `user_initiated=true` 写入；后台推进不写。
7. 渡的自动 follow-up 不重复刷新时间。
8. SumiTalk、Telegram、QQ、微信真实 chat 都更新 chat；内部请求不更新。
9. chat 与游戏并发更新后两个字段都保留，不发生整文件覆盖。
10. R2 失败不阻断游戏请求，本地记录失败也不阻断游戏请求。
11. 主动唤醒调度仍只看 R2 统一互动时间。
12. 主动唤醒描述不再把最近共同游戏说成“明确回复”。
13. 对目标提交版本在干净 worktree 运行相关脚本、`py_compile` 和 `import app`。

## 11. 本轮边界结论

推荐落地方式是“现有 R2 统一时钟不动 + 扩展现有本地 chat 记录 + 显式共同游戏入口”。它比在 R2 新建 chat/game 三套时钟改动小，也比根据所有 game tool 自动推断安全。

本方案已经落地。后续变更仍需保持显式共同游戏白名单、真实用户参与才记时、测试 mock 外部写入这三条边界；不要把渡单独玩的游戏或后台自动推进算作小玥的互动。
