# 部署到 Cloudflare Pages（替代 github.io）

**为什么换：** GitHub Pages 国内不稳；投手申请不到 GitHub 账号也没法 commit。Cloudflare Pages 国内可达，前端拖拽 → Cloudflare Function → 后端 GitHub repo（投手不可见）。

**ZJB 一次性 5 步，之后 git push 自动部署。**

---

## Step 1 · 生成 GitHub PAT（fine-grained）

1. 打开 https://github.com/settings/personal-access-tokens/new
2. Token name: `multisite-cloudflare-upload`
3. Expiration: 90 days（到期再换）
4. Repository access: **Only select repositories** → 勾 `zhujiebing2020-lgtm/multisite-platform`
5. Permissions → Repository permissions:
   - **Contents**: `Read and write`
   - **Metadata**: `Read-only`（自动勾）
6. 生成 → **复制 token**（只显示一次，丢了重来）

---

## Step 2 · 创建 Cloudflare Pages 项目

1. 注册 / 登录 https://dash.cloudflare.com（用邮箱即可，国内能注册）
2. 左侧菜单：**Workers & Pages** → **Create** → **Pages** → **Connect to Git**
3. 授权 GitHub → 选 `zhujiebing2020-lgtm/multisite-platform`
4. 配置构建：
   - **Project name**: `multisite-platform`（决定后续域名 `multisite-platform.pages.dev`）
   - **Production branch**: `main`
   - **Framework preset**: `None`
   - **Build command**: 留空
   - **Build output directory**: `view`
5. **Save and Deploy**（第一次部署会跑 ~30s）

---

## Step 3 · 配置环境变量（关键）

部署完成后：**Settings** → **Environment variables** → **Production** → 加 3 条：

| 变量名 | 值 | 说明 |
|---|---|---|
| `GITHUB_TOKEN` | Step 1 复制的 token | 推 xlsx / md 到 repo 用 |
| `GITHUB_REPO` | `zhujiebing2020-lgtm/multisite-platform` | 目标 repo |
| `ACCESS_PASSCODE` | 自定义口令（如 `crave-2026`） | 投手访问口令 |

**Type 都选 `Encrypted`** → Save。

加完后点 **Deployments** → 最新一次 → **Retry deployment**（环境变量要重部署才生效）。

---

## Step 4 · 验证

1. 浏览器开 `https://multisite-platform.pages.dev/`
2. 看到总览页 → 点 "→ 投手工作台" → 进 `upload.html`
3. 选 owner = HZM，填 ACCESS_PASSCODE
4. 点 "数据分析" 按钮 → 应提示 "✓ 数据分析 已提交"
5. 去 GitHub repo `requests/` 目录看，应有新文件 `HZM-数据分析-xxx.md`
6. GitHub Actions 自动跑 `process-requests.yml` → 5-10 分钟后看板更新

---

## Step 5 · 发投手 URL

只发：
- URL：`https://multisite-platform.pages.dev/`
- 口令：你设的 `ACCESS_PASSCODE`
- 备注：选自己（HZM/CHJ/...），上传当日 xlsx，看自己看板

**不发**：GitHub 任何东西。

---

## 后续维护

- 改前端（`view/*.html`、`functions/api/*.js`）→ git push → Cloudflare 自动部署 ~30s
- 90 天 PAT 到期 → 重新生成 → 替换 Cloudflare 环境变量 `GITHUB_TOKEN`
- 想换口令 → 改 `ACCESS_PASSCODE` → 投手浏览器 localStorage 旧口令会失效，重发新的

## 备注

- **Cloudflare 不收费**：免费版 Pages 100k 请求/天 + Functions 10万次/天，投手用完全够
- **GitHub Pages 关掉**：保留也行，但**不要给投手**；实际起作用的是 Cloudflare 这条线
- **域名**：将来可绑 `*.creviatech.com` 子域，更专业；先用 `pages.dev` 跑通再说
