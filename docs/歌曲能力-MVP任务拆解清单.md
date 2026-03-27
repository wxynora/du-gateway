# 歌曲能力 MVP 任务拆解清单（歌词由渡实时生成）

## 0. 目标与范围

### 0.1 目标
在 `du-gateway` 内实现一个最小闭环：
1. 用户发起“写歌并演唱”请求
2. 渡先自己写歌词
3. 生成伴奏
4. 用 MiniMax 生成演唱人声
5. 混音导出 `mp3` 并返回试听地址

### 0.2 非目标（本期不做）
- 多风格精调 UI
- 复杂 DAW 级别后期
- 公开发布能力
- 多音色市场管理

### 0.3 验收标准
- 一次请求可稳定产出可播放 `final_mix_url`
- 全链路失败有明确状态和错误信息
- 支持最少 1 个“渡”音色配置

---

## 1. 开工前准备（半天）

- [ ] 确认 MiniMax 可用账号与 key（仅环境变量）
- [ ] 确认伴奏生成来源（可先选一个稳定 provider）
- [ ] 确认音频存储方式（本地目录或对象存储）
- [ ] 确认本期统一输出格式：`mp3`, `44.1kHz`, `192kbps`
- [ ] 约定任务超时（建议 10 分钟）

交付物：
- 《能力边界确认记录》
- `.env.example` 增加占位字段（不填真实 key）

---

## 2. 数据结构与状态机（半天）

### 2.1 任务状态
- `PENDING`
- `LYRICS_GENERATING`
- `INSTRUMENTAL_GENERATING`
- `VOCAL_GENERATING`
- `MIXING`
- `SUCCESS`
- `FAILED`

### 2.2 SongJob 字段（MVP）
- `job_id`
- `user_id`（若无用户体系可先匿名）
- `topic`
- `mood`
- `duration_sec`
- `voice_profile_id`
- `status`
- `lyrics_text`
- `instrumental_url`
- `vocal_url`
- `final_mix_url`
- `error_step`
- `error_message`
- `created_at`
- `updated_at`

### 2.3 子任务日志字段
- `step_name`
- `attempt`
- `latency_ms`
- `provider_request_id`
- `result_summary`

交付物：
- `SongJob` 结构定义
- 状态流转图（文本或 mermaid）

---

## 3. 接口定义（半天）

### 3.1 创建任务
`POST /v1/song/jobs`

请求：
```json
{
  "topic": "深夜下雨想念一个人",
  "mood": "治愈",
  "duration_sec": 60,
  "voice_profile_id": "du_default"
}
```

响应：
```json
{
  "job_id": "song_xxx",
  "status": "PENDING"
}
```

### 3.2 查询任务
`GET /v1/song/jobs/{job_id}`

响应：
```json
{
  "job_id": "song_xxx",
  "status": "MIXING",
  "lyrics_text": "...",
  "instrumental_url": "...",
  "vocal_url": "...",
  "final_mix_url": null,
  "error_step": null,
  "error_message": null
}
```

交付物：
- OpenAPI 草案或 markdown 接口文档

---

## 4. 编排器实现（1 天）

### 4.1 Song Pipeline（顺序执行）
1. `generate_lyrics_by_du()`
2. `generate_instrumental()`
3. `generate_vocal_with_minimax()`
4. `mix_and_export()`
5. 更新任务为 `SUCCESS`

### 4.2 失败与重试策略
- 每一步最多重试 2 次
- 指数退避：2s / 5s
- 重试后仍失败：置 `FAILED`，记录 `error_step`

### 4.3 幂等
- 同一个 `job_id` 不可重复并发执行
- 若进程重启，可根据状态恢复（至少支持从失败步重跑）

交付物：
- `song_orchestrator` 模块
- 步骤级日志输出

---

## 5. 歌词生成（由渡自己写）（半天）

### 5.1 Prompt 约束
- 固定段落结构：`主歌-副歌-主歌-副歌`
- 每行 8-14 字，避免超长句
- 主题与情绪必须贴合输入
- 输出纯文本歌词（MVP 不强制 JSON）

### 5.2 质量兜底
- 如果生成空歌词或过短（<8 行），自动重试一次
- 若仍失败，返回模板化兜底歌词（可配置）

交付物：
- `lyrics_prompt_template`
- `generate_lyrics_by_du()` 实现说明

---

## 6. 伴奏生成（1 天）

### 6.1 输入
- `mood`
- `duration_sec`
- 可选：`bpm`, `key`

### 6.2 输出
- `instrumental_url`
- 元数据：`duration_actual`, `bpm_actual`

### 6.3 兜底
- provider 超时：重试
- provider 挂了：返回失败并记录 provider 细节

交付物：
- `instrumental_client`
- provider 配置项

---

## 7. MiniMax 演唱（1 天）

### 7.1 输入
- `lyrics_text`
- `voice_profile_id`
- `instrumental_url`（如接口支持）
- `mood` / `style_tag`

### 7.2 输出
- `vocal_url`
- 可选：对齐信息（若返回）

### 7.3 音色配置管理
- `voice_profile_id -> minimax_voice_id` 映射配置
- 先支持 `du_default` 一个档位

交付物：
- `minimax_vocal_client`
- 音色映射配置文件

---

## 8. 混音导出（半天）

### 8.1 处理项（MVP）
- 人声音量 -2dB（可调）
- 伴奏音量 -5dB（可调）
- 峰值限制避免爆音
- 导出 `mp3`

### 8.2 工具建议
- `ffmpeg` 命令行集成（最稳、最快）

交付物：
- `mix_and_export()` 实现
- 导出文件路径策略（按 `job_id` 归档）

---

## 9. 配置与安全（半天）

- [ ] 新增环境变量：
  - `MINIMAX_API_KEY`
  - `MINIMAX_BASE_URL`
  - `SONG_STORAGE_PATH`
  - `SONG_TIMEOUT_SEC`
- [ ] 日志脱敏（key/token 不落盘）
- [ ] 限制最大时长（例如 <= 120 秒）

交付物：
- 配置加载与校验逻辑
- `.env.example` 更新

---

## 10. 测试清单（1 天）

### 10.1 单元测试
- [ ] 状态机流转正确
- [ ] 重试次数正确
- [ ] 参数校验正确

### 10.2 集成测试
- [ ] 正常链路：从创建任务到拿到 `final_mix_url`
- [ ] MiniMax 超时后可重试成功
- [ ] 伴奏失败后任务标记 `FAILED`
- [ ] 混音失败有可读错误

### 10.3 人耳验收（最关键）
- [ ] 歌词可听清
- [ ] 副歌明显
- [ ] 总时长符合输入预期
- [ ] 无明显爆音/破音

交付物：
- 测试报告（通过/失败项）
- 3 条样例任务结果链接

---

## 11. 与现有机器人入口集成（半天）

- [ ] 增加一条指令（例：`/song 主题|情绪|时长`）
- [ ] 返回 `job_id` 与进度提示
- [ ] 完成后回传试听链接

交付物：
- 机器人命令说明
- 示例交互文案

---

## 12. 里程碑与工时估算

### M1（第 1 天）
- 完成：数据结构、接口定义、状态机骨架
- 结果：任务可创建、可查状态（空跑）

### M2（第 2 天）
- 完成：歌词 + 伴奏 + MiniMax 串通
- 结果：有 `vocal_url`

### M3（第 3 天）
- 完成：混音导出、机器人入口、测试
- 结果：端到端可试听

总计：约 3 天（单人 MVP）

---

## 13. 风险与应对

- 风险：第三方接口抖动
  - 应对：重试 + 超时 + 失败可续跑

- 风险：歌词过长导致唱不清
  - 应对：行长限制 + 段落模板

- 风险：音量失衡
  - 应对：固定增益参数 + 峰值限制

- 风险：生成耗时过长
  - 应对：异步任务 + 进度查询

---

## 14. 开工任务分派模板（可直接贴看板）

- [ ] TASK-01 定义 SongJob 模型与状态机
- [ ] TASK-02 实现 `/v1/song/jobs` 创建与查询接口
- [ ] TASK-03 实现歌词生成模块（渡）
- [ ] TASK-04 接入伴奏生成 client
- [ ] TASK-05 接入 MiniMax 演唱 client
- [ ] TASK-06 实现 ffmpeg 混音与导出
- [ ] TASK-07 打通编排器与重试机制
- [ ] TASK-08 增加机器人命令入口
- [ ] TASK-09 完成集成测试与试听验收
- [ ] TASK-10 补齐文档与运维说明
