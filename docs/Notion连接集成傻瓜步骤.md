# Notion 连接集成 — 傻瓜步骤

网关用 Notion API 写小本本、记忆库、核心缓存等，需要先在 Notion 里**创建集成**，再把**每个要用到的页面/数据库**都「邀请」这个集成，否则会报 404（Could not find database/page）。

---

## 第一步：创建集成（只做一次）

1. 浏览器打开：**https://www.notion.so/my-integrations**
2. 点击 **「+ 新建集成」**（New integration）
3. 填：
   - **名称**：随便，例如 `du-gateway`
   - **关联的 workspace**：选你放小本本/记忆库的那个空间
   - **能力**：保持默认即可（需要读内容、更新内容）
4. 提交后，在集成详情页里找到 **「内部集成密钥」**（Internal Integration Secret），形如 `secret_xxxxxxxxxxxx`。
5. 复制这个密钥，填到你的环境变量：**`NOTION_API_KEY=secret_xxxx`**（网关代码里会读这个）

---

## 第二步：把页面/数据库分享给集成（每个都要做）

创建集成后，**每个**你要让网关写的**页面**或**数据库**，都要单独「邀请」这个集成进来：

1. 在 Notion 里打开**该页面**或**该数据库**（点进去到能编辑的状态）
2. 右上角点 **「…」**（三个点）或 **「Share」**
3. 在分享弹窗里点 **「邀请」** 或 **「Add people, emails, groups」** 那一块
4. 下面会有一个 **「连接」** / **「Connections」** 或 **「邀请更多」**
5. 在列表里找到你刚建的集成（例如 `du-gateway`），点一下**邀请/连接**
6. 确认后，该页面/数据库就对集成可见了

**需要分享的（按你实际用的）：**

| 用途           | 类型     | 环境变量 / 说明 |
|----------------|----------|-----------------|
| 小本本         | 页面或 Database | 若用 Database：`NOTION_NOTEBOOK_DATABASE_ID` 对应的那个数据库要分享 |
| 小本本         | 页面     | 若用页面：`NOTION_NOTEBOOK_PAGE_ID` 对应的页面要分享 |
| 卧室           | 页面     | `NOTION_BEDROOM_PAGE_ID` 对应的页面要分享 |
| 记忆库（归档） | Database | `NOTION_ARCHIVE_DATABASE_ID` 或四张表的 ID 要分享 |
| 核心缓存待审   | Database | `NOTION_CORE_CACHE_DATABASE_ID` 对应的数据库要分享 |

**每一个**你在环境变量里填了 ID 的页面/数据库，都要按上面步骤分享给集成，否则网关写的时候会 404。

---

## 第三步：确认环境变量

确保 `.env` 或运行环境里有：

- `NOTION_API_KEY=secret_xxxx`（第一步拿到的密钥）
- `NOTION_VERSION=2022-06-28`（一般不用改）
- 各 `NOTION_xxx_ID` 填的是**已分享给集成的**页面/数据库的 ID（32 位，带 `-` 的去掉即可）

---

## 常见报错

- **404 / Could not find database with ID**  
  → 这个 ID 对应的数据库或页面**没有**在 Notion 里「邀请」你的集成。回到第二步，打开该数据库/页面，用「…」→ 连接 → 选你的集成。

- **401 / Unauthorized**  
  → `NOTION_API_KEY` 填错或过期，回第一步重新复制密钥。

做完以上，再重新跑归档脚本即可；脚本里已支持「同 id 则更新」，重复的会覆盖。
