# Notion 各房间设置傻瓜版教程（与网关输出完全匹配）

网关会往 Notion 写三类东西：**小本本**、**卧室**、**核心缓存**。下面按「用表格还是页面」「字段怎么建」逐项说明，建好后把对应 ID 填到环境变量即可。

---

## 一、总览

| 房间/用途 | Notion 类型 | 网关写入方式 | 需要建的 |
|-----------|-------------|--------------|----------|
| 小本本 | **普通页面 (Page)** | 在页面下追加段落，每条 `[时间] 原文` | 1 个空页面 |
| 卧室 | **普通页面 (Page)** | 在页面下追加段落，每条 `[event_id] [时间]\n原文` | 1 个空页面 |
| 核心缓存 | **Database（表格）** | 创建/更新行，按列名匹配 | 1 个 Database，7 列（你已建可跳过） |

---

## 二、小本本（Notebook）

- **类型**：普通页面，**不要**用 Database。
- **作用**：网关检测到「📝 + 小本本更新」时，会把截取的原文 + 北京时间的 `[时间]` 追加到这个页面下面。

**操作步骤：**

1. 在 Notion 里新建一页 **Full page**（空白页面即可）。
2. 标题随便写，例如「小本本」。
3. 页面里可以什么都不写，网关会往**页面底部**一直追加段落。
4. 复制该页面的 ID：
   - 浏览器地址栏里打开这个页面，URL 形如：`https://www.notion.so/xxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - 最后那串 32 位（有时带 `-` 的）就是 **Page ID**。若带 `-`，去掉所有 `-` 再复制。
5. 环境变量里设置：`NOTION_NOTEBOOK_PAGE_ID=你复制的页面ID`

**网关写入格式示例：**

```
[2026-03-15T14:30:00+08:00] 小本本更新 今天终于把 R2 调通了……
```

每条都是一段 **Paragraph**，无需任何属性/字段。

---

## 三、卧室（Bedroom）

- **类型**：普通页面，**不要**用 Database。
- **作用**：当动态层 DS 返回 `tag === "卧室"` 时，网关会把当轮对话原文追加到这个页面（不写动态层/核心缓存）。

**操作步骤：**

1. 在 Notion 里再新建一页 **Full page**，标题例如「卧室」。
2. 页面内容可留空，网关会往**页面底部**追加段落。
3. 同样从浏览器 URL 里复制该页面的 **Page ID**（32 位，有 `-` 就去掉）。
4. 环境变量里设置：`NOTION_BEDROOM_PAGE_ID=你复制的页面ID`

**网关写入格式示例：**

```
[event_id:window-42] [2026-03-15T14:35:00+08:00]
老婆：xxx
assistant：xxx
```

每条都是一段 **Paragraph**，无需任何属性/字段。

---

## 四、核心缓存（Core cache）— 你已建可跳过

- **类型**：**Database（表格视图即可）**。
- **作用**：网关「同步到 Notion」时会把 R2 里的 pending 推到这张表（创建或按 id 更新行）；「从 Notion 同步」时会把表里所有行读回 R2。

**列名与类型必须和下面一致（列名一个字都不能差）：**

| 列名 (Name) | Notion 属性类型 | 说明 |
|-------------|-----------------|------|
| `id` | **Title** | 唯一标识（网关用这个判断是新建还是更新） |
| `content` | **Text**（Rich text） | 记忆内容正文 |
| `promoted_by` | **Select** | 选值：`importance`、`mention_count`（可只建这两个选项） |
| `importance` | **Number** | 1–4 |
| `mention_count` | **Number** | 整数 |
| `promoted_at` | **Date** | 北京时间 ISO 或日期时间均可 |
| `tag` | **Select** | 选值：`卧室`、`客厅`、`书房`、`图书馆`（与 DS tag 一致） |

**操作步骤：**

1. 新建 **Database - Inline** 或 **Full page database**。
2. 默认会有一列 **Title**，把这一列的**名字**改成 `id`（保留类型为 Title）。
3. 依次新建列，名字和类型按上表：
   - `content` → Text (Rich text)
   - `promoted_by` → Select，选项加 `importance`、`mention_count`
   - `importance` → Number
   - `mention_count` → Number
   - `promoted_at` → Date
   - `tag` → Select，选项加 `卧室`、`客厅`、`书房`、`图书馆`
4. 复制 Database 的 ID（在浏览器打开该 database 页面，URL 里 32 位那串，有 `-` 就去掉）。
5. 环境变量里设置：`NOTION_CORE_CACHE_DATABASE_ID=你复制的数据库ID`

**说明**：网关按「列名」匹配，你多建几列没关系，只要这 7 列名字一致即可；若某列不存在，网关会跳过该字段。

---

## 五、环境变量汇总

在服务器或 `.env` 里配置（Notion 集成需先创建 Integration 并拿到 API Key，把对应页面/数据库邀请该 Integration 进入）：

```bash
NOTION_API_KEY=secret_xxxx
NOTION_VERSION=2022-06-28

# 三个 ID：小本本页面、卧室页面、核心缓存数据库
NOTION_NOTEBOOK_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_BEDROOM_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_CORE_CACHE_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**如何拿 Page ID / Database ID：**

- 在 Notion 里用「Copy link」复制页面/数据库链接，格式一般为：  
  `https://www.notion.so/workspace/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`  
  或  
  `https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
- 其中 `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 即为 32 位 ID；若链接里是带连字符的 36 位，去掉全部 `-` 即可。

---

## 六、对照表（方便你自查）

| 房间 | 用表格？ | 用页面？ | 网关写的具体是什么 |
|------|----------|----------|----------------------|
| 小本本 | 否 | 是，1 个空页面 | 段落：`[时间] 小本本更新……` |
| 卧室 | 否 | 是，1 个空页面 | 段落：`[event_id:xxx] [时间]\n原文` |
| 核心缓存 | 是，Database | - | 每行一条记录，7 列：id, content, promoted_by, importance, mention_count, promoted_at, tag |

按上面建好后，字段和网关输出一一对应，直接配好 ID 即可用。
