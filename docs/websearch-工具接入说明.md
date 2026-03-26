# WebSearch 工具接入说明（Phase1）

## 能力范围
- 工具名：`web_search`
- 当前阶段：仅搜索，不做网页抓取解析
- Provider 策略：`tavily`

## 配置项
在 `.env` 中配置以下参数：

- `WEBSEARCH_ENABLED=1`
- `WEBSEARCH_PROVIDER_ORDER=tavily`
- `TAVILY_API_KEY=...`
- `TAVILY_SEARCH_ENDPOINT=https://api.tavily.com/search`
- `WEBSEARCH_TIMEOUT_SECONDS=8`
- `WEBSEARCH_MAX_RESULTS=5`

## 返回结构
工具返回 JSON 字符串，核心字段：

- `ok`: 是否成功
- `query`: 搜索词
- `items`: 搜索结果列表（`title/url/snippet/source/published_at`）
- `meta.provider_used`: 实际命中的 provider
- `meta.fallback_chain`: 本次尝试过的 provider 顺序
- `meta.degraded`: 是否发生降级

## 故障排查
- 报 `query 不能为空`：检查工具参数是否传了 `query`
- `所有 provider 均不可用`：检查 API key、endpoint、网络连通性
- 结果为空：检查关键词是否过窄，或 provider 暂无匹配结果
