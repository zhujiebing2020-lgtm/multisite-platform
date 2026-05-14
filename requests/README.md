# requests/ — 系统内部目录（投手不要直接动）

**这个目录是 ZJB 的后端管线。投手在浏览器工作台触发 agent，系统会自动写到这里。**

投手入口：`https://multisite-platform.pages.dev/upload.html`（不需要 GitHub）

---

## 这里是什么

- `requests/*.md` — 投手在工作台点 agent 按钮后，Cloudflare Function 写进来的请求文件
- `requests/uploads/` — 投手在工作台拖的 xlsx
- `requests/_done/` — 处理完归档（GitHub Actions 自动移动）

## 处理流程

```
投手浏览器(upload.html)
  → Cloudflare Pages Function (functions/api/request.js / upload.js)
  → GitHub Contents API 写文件到本目录
  → process-requests.yml Actions 触发
  → 跑 agent / ingest xlsx
  → 重建 view/ → Cloudflare Pages 自动重发布
  → 投手刷新看板看新数据
```

## 旧的"投手在 GitHub 网页 commit"流程已废弃

5/14 ZJB 决策：投手不接触 GitHub。任何"在 GitHub 网页编辑文件触发 agent"的旧文档忽略。
