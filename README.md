# multisite-platform · 多站群多 agent

**平台是发动机,站是车壳。一套 crave-AI 主站经验 → N 个站投手用。**

---

## 现状(2026-05-14 · 投手前端转 Cloudflare Pages)

| 层 | 状态 |
|---|---|
| L1 监管层 | 搬运 agent 代理(ZJB 拍板:子站→总站自动,总站→子站人工) |
| L2 上下文层 | loader + 四层覆盖 + LoadedConfig 强类型 |
| L3 事件层 | EventBus + dispatcher + heuristic 源 |
| L4 引擎层 | Task Engine + 优先级队列 + event_to_task.yaml |
| L5 执行层 | **11 agent 全实现** · I/O 合约严格遵守 |
| L6 数据层 | sqlite 持久化 · 4 张表 · 跨进程恢复 |
| 中间件 | **CLAUDE.md 合约一二三全实现**(七槽位+rule_source+target_role) |
| 规则底盘 | fork crave-AI@51c9bdc 13 个规则文件(chmod 444 只读)|
| 数据底盘 | fork crave-AI · 714 行日级 CSV + 45 个 cards · 真数据跑 |
| 投手前端 | **Cloudflare Pages + Pages Function · 不需 GitHub 账号** |
| 后端管线 | GitHub Actions 全自动(process-requests.yml + pages.yml) |

## 11 个 agent

```
看清钱       数据分析
找原因       归因诊断 · 知识沉淀
变动作       策略简报 · 研发需求
生成策略     意志继承 · 文案 · 故事脚本 · 素材审核 · 搬运
交付         交接消息
```

每个 agent 强制走中间件三件套(七槽位输入校验 / rule_source 规则指针 / target_role 5 枚举封闭)。

## 上线（ZJB 一次性）

按 `docs/deploy_cloudflare.md` 5 步：GitHub PAT → Cloudflare Pages 连 repo → 配 3 个环境变量 → 验证 → 发投手 URL。

之后 git push 自动重部署。

## 投手协作循环

```
投手浏览器: https://multisite-platform.pages.dev/
    ↓ 选 owner + 填口令(首次)
    ↓ 拖 xlsx / 点 agent 按钮
[Cloudflare Pages Function]
    ↓ GitHub Contents API 写文件到 requests/
[GitHub Actions process-requests.yml 触发]
    ↓ ingest_from_xlsx / 跑 agent → 归档 → 重建 view/
    ↓ Cloudflare Pages 自动重部署 view/
[5-10 分钟]
投手刷新看板 → 看到新数据
```

**投手不接触 GitHub。**

## 目录结构

```
platform-core/
  监管层/          L1(搬运 agent 代理)
  上下文层/        L2 · loader.py · defaults.yaml
  事件层/          L3 · bus.py · dispatcher.py
  引擎层/          L4 · engine.py · event_to_task.yaml · invoker.py
  执行层/          L5 · 11 agent 目录 + _base.py
  数据层/          L6 · schema.sql · runtime.py · runtime.db (gitignore)
  中间件/          合约一二三 · 七槽位 / target_role / 规则指针
  规则/            fork crave-AI 13 JSON(只读,_FORK_MANIFEST 锁 sha)
  数据底盘/        fork crave-AI Q1 全量 CSV + cards(只读)
  数据接入-ingest/ fork crave-AI 8 脚本(参考用)
  能力包/          打法包 / 产出包 / 内容包

sites/elysianu/    车壳 · config.yaml + assets + data-inbox

requests/          投手前端写入的请求(系统内部 · 投手不直达)
requests/uploads/  投手前端上传的 xlsx 归档
requests/_done/    处理完归档

functions/api/     Cloudflare Pages Function
  upload.js          接收 xlsx → 写 requests/uploads/
  request.js         接收 agent 触发 → 写 requests/

data/cards/        agent 输出的 JSON cards
view/              静态看板 + upload.html(Cloudflare Pages serve)

bin/
  ingest_daily.py    原生 ingest
  ingest_from_xlsx.py 投手 xlsx → JSON + 触发 agent(Actions 调)
  export_dashboard.py sqlite → cards
  build.py           cards → HTML
  build_widget.py    精简嵌入版
  request_monitor.py 请求文件处理(本地+Actions 双兼容)

.github/workflows/
  pages.yml          (备用 · 实际由 Cloudflare 部署)
  process-requests.yml requests/ 改动自动触发处理

docs/
  架构思路-v3.md
  协作手册-投手必看.md   给 HZM / CHJ / HNN 看
  runtime-os-视图.svg
  外部评议-v3-20260513.md
```

## 三条硬约束

1. **crave-AI 源仓库零修改** — 一切复刻只读,_FORK_MANIFEST.json 锁 sha256 可校验
2. **IO 合约三件套强校验** — 每个 agent 输出必走 target_role 封闭枚举 + rule_source 非空 + 七槽位入
3. **ZJB 业务规则定义权** — Claude 可质疑不可修改业务阈值

## 入口文档

- `docs/协作手册-投手必看.md` — HZM / CHJ / HNN 必读
- `docs/架构思路-v3.md` — §1-§15 架构细节
- `platform-core/规则/_FORK_MANIFEST.json` — fork 版本锁
- 仓库源规则:`~/Documents/GitHub/crave-AI/` @ `51c9bdc`(只读)
