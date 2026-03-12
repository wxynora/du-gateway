# 推送到 GitHub（傻瓜版）

## 1. 本地已准备好

- 已建好 `.gitignore`（不提交 `.env`、`__pycache__`、`data/`、`.cursor/`）
- 已提交：`git commit -m "Initial commit: du-gateway 网关与记忆管道"`

## 2. 在 GitHub 建仓库

1. 打开 https://github.com/new
2. Repository name 填：`du-gateway`（或你喜欢的名字）
3. 选 **Private** 或 **Public**
4. **不要**勾选 "Add a README"（本地已有）
5. 点 **Create repository**

## 3. 连上 GitHub 并推送

在项目目录执行（把 `你的用户名` 和 `du-gateway` 换成你的）：

```bash
git remote add origin https://github.com/你的用户名/du-gateway.git
git branch -M main
git push -u origin main
```

如果用 SSH：

```bash
git remote add origin git@github.com:你的用户名/du-gateway.git
git branch -M main
git push -u origin main
```

## 4. 以后改完代码再推

```bash
git add .
git commit -m "简短说明"
git push
```

---

**注意**：`.env` 不会上传，部署到服务器后要自己复制 `.env.example` 为 `.env` 并填好密钥。
