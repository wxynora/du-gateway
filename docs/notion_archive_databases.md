# 归档四表：图书馆 / 卧室 / 客厅 / 书房（Notion Database）

字段与动态层存 Notion 的「核心缓存」一致，方便筛选和 Notion 自带关键词检索。

---

## 1. 在 Notion 里建 4 个 Database

1. 打开 Notion，**新建页面** → 选择 **Table – Full page**（或 Inline table）。
2. 把表名改成：**图书馆**（或 归档-图书馆，随你）。
3. **列（属性）** 按下面建，名字必须一致（网关按列名匹配）：

| 列名 | Notion 属性类型 | 说明 |
|------|-----------------|------|
| **id** | Title | 唯一标识（记忆 id 或 round 标识） |
| **content** | Text（Rich text） | 记忆正文或原文；**可被 Notion 搜索** |
| **importance** | Number | 1–4 |
| **mention_count** | Number | 提及次数 |
| **promoted_at** | Date | 时间（原始记录时间，ISO 或日期） |
| **tag** | Select | 选单里保留：书房 / 客厅 / 图书馆 / 卧室（可选，因已分表） |

4. **复制这个 Database 的 ID**：  
   打开该 Database 页面，浏览器地址栏类似  
   `https://www.notion.so/xxx?v=yyy`  
   若在页面内嵌的表格，点表格名 → 「Open as full page」→ 再看地址栏。  
   **Database ID** = URL 里 32 位的那段（去掉 `-` 共 32 字符），例如：  
   `https://www.notion.so/workspace/322043f2b839808c8a26d664e4e6e6a9?v=...`  
   → ID 为 `322043f2b839808c8a26d664e4e6e6a9`。

5. **同样方式再建 3 个表**：**卧室**、**客厅**、**书房**，列名和类型与上表完全一致。

6. 把 4 个 Database ID 填到环境变量（见下）。

---

## 2. 关键词检索（用 Notion 自带能力）

- 每个 Database 打开后，**表格上方有搜索框**，直接输入关键词即可搜 **content** 等文本列。
- 也可用 **Filter**：按 `importance`、`promoted_at`、`tag` 筛选。
- **Sort**：按时间、importance 排序。
- Notion 顶栏 **Search** 会搜全工作区，也能搜到这些 Database 里的页面（每条归档是一行 = 一个 page）。

---

## 3. 环境变量（网关 / 归档脚本）

在 `.env` 或环境里配置 4 个 ID（建好表后替换为你的 ID）：

```env
NOTION_ARCHIVE_DATABASE_ID_书房=你的书房表 database_id
NOTION_ARCHIVE_DATABASE_ID_客厅=你的客厅表 database_id
NOTION_ARCHIVE_DATABASE_ID_图书馆=你的图书馆表 database_id
NOTION_ARCHIVE_DATABASE_ID_卧室=你的卧室表 database_id
```

留空则该项不写 Notion，只写 R2/本地逻辑。

---

## 4. 小结

- **四个表**：图书馆、卧室、客厅、书房，各一个 Database，**列名和类型一致**。
- **字段**：id, content, importance, mention_count, promoted_at, tag（与动态层/核心缓存一致）。
- **检索**：用 Notion 表格搜索 + Filter + Sort 即可，无需额外配置。
