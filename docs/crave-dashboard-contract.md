# crave.z-jb.com 数据推送约束文档

> 版本 v1.0 · 2026-05-18 建立 · 随代码变更同步更新

## 1. 架构概览

```
数据源 → POST /api/crave/* → D1 (intake_reports + dashboard_cards + ad_daily)
                                    ↓
crave.z-jb.com 前端 ← GET /api/crave/* ← D1
```

- Worker 入口：`src/index.js` → `src/api/crave-dashboard.js`
- 前端：`view/crave.html`（94KB，数据从 API fetch）
- D1 数据库：`multisite-db`

## 2. API 端点规范

| 端点 | 方法 | 用途 | 认证 |
|------|------|------|------|
| `/api/crave/cards` | GET | 查询卡片（?type=&channel=&after=） | 无 |
| `/api/crave/cards` | POST | 写入/更新卡片（数组或单个） | 无 |
| `/api/crave/intake` | GET | 最新承接端报告（?date= 指定） | 无 |
| `/api/crave/intake` | POST | 写入承接端报告 | 无 |
| `/api/crave/ad-history` | GET | ad_daily 表数据（?days=30） | 无 |
| `/api/crave/sync` | POST | 批量同步（cards + intake） | 无 |

## 3. 数据结构约束（不可随意变更）

### 3.1 dashboard_cards 表

```sql
card_id TEXT PRIMARY KEY,      -- 如 "daily-2026-05-15"
card_type TEXT NOT NULL,       -- daily_dashboard / action_list / claim / dev_requirement / rule / breakpoint
channel TEXT,                  -- facebook / google / all
data_date TEXT,                -- YYYY-MM-DD
payload TEXT NOT NULL,         -- 完整 card JSON
last_updated TEXT
```

**card payload 必须包含 `meta` 字段**：
```json
{
  "meta": {
    "card_id": "必填，与表 PK 一致",
    "card_type": "必填",
    "channel": "选填",
    "title": "必填",
    "last_updated": "必填 YYYY-MM-DD",
    "target_role": ["至少1个"]
  },
  "signals": [{"label": "", "value": "", "source": ""}],
  ...
}
```

### 3.2 intake_reports 表

```sql
date TEXT NOT NULL UNIQUE,     -- "2026-05-18" 或 "2026-05-15/2026-05-17"
submitted_by TEXT,
overall_health TEXT,           -- red / yellow / green
health_note TEXT,
payload TEXT NOT NULL           -- 完整报告 JSON
```

**payload 必须包含**：`date`, `overall_health`, `modules[]`, `funnel{}`

### 3.3 ad_daily 表（已有，不新建）

```sql
owner TEXT,          -- 投手 code (CHJ/HNN/HZM)
site TEXT,           -- 站点
date TEXT,           -- YYYY-MM-DD
group_name TEXT,     -- 如 "组17 18 Sensual"
spend REAL,
hvu INTEGER,
cphq REAL,
impressions INTEGER,
clicks INTEGER
```

## 4. 前端渲染依赖

前端 `crave.html` 的 `loadData()` 依赖以下全局变量被填充：

| 变量 | 来源 API | 渲染函数 |
|------|---------|---------|
| `CARD_DATA` | `/api/crave/cards` | `renderDashboardView()`, `renderCard()` |
| `ACCEPT_INTAKE` | `/api/crave/intake` | `renderAcceptView()`, `renderFunnel()` |
| `AD_HISTORY` | `/api/crave/ad-history` | `renderAdTable()` |
| `WIKI_DATA` | 内联保留（静态） | `renderWikiView()` |
| `VIEW_FILTER` | 内联保留（配置） | 视图切换逻辑 |

**变更 card 结构时**：必须同步检查 `renderCard()` 是否兼容。

## 5. 日常数据推送流程

### 推送 FB 每日看板卡
```bash
curl -X POST https://crave.z-jb.com/api/crave/cards \
  -H 'Content-Type: application/json' \
  -d '[{"meta":{"card_id":"daily-2026-05-18","card_type":"daily_dashboard","channel":"facebook","title":"FB 5/18","last_updated":"2026-05-18","target_role":["投手"]},"signals":[...]}]'
```

### 推送承接端报告
```bash
curl -X POST https://crave.z-jb.com/api/crave/intake \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-05-18","submitted_by":"吴玲","overall_health":"red",...}'
```

### 推送广告组数据
通过现有 `/api/upload`（xlsx）或 `/api/ingest`（JSON）写入 `ad_daily` 表。

## 6. 与 crave-AI repo 的关系

| 项目 | 状态 | 说明 |
|------|------|------|
| `crave-AI/index.html` | 冻结 | GitHub Pages 保留作备份，不再更新数据 |
| `crave-AI/data/` | 继续维护 | 作为知识库 vault 的 repo 侧存储 |
| `crave.z-jb.com` | 主看板 | 数据从 D1 读取，不依赖 crave-AI repo |

## 7. 禁止事项

- ❌ 不直接操作 D1 SQL 修改 payload 结构（改结构走代码变更 + 部署）
- ❌ 不删除 dashboard_cards 记录（历史数据只追加不删除）
- ❌ 不在前端 crave.html 中硬编码数据（所有数据走 API）
- ❌ 不修改 card_id 命名规则（`{type}-{date}[-{channel}]`）

## 8. 触发链（模块间自动推送关系）

```
POST /api/crave/cards (card_type=daily_dashboard)
    → 自动生成 action-pitcher-{today} 卡片
    → 基于 ad_daily 最近7天数据，按 CPHQ 分层(S≤$3/A≤$5/B>$5/R=0HVU)
    → 按投手分组，输出 continue/stop 建议

POST /api/crave/intake
    → 自动更新 must_fix_today 中 linked_claim 对应的 claim 卡片
    → 追加最新证据到 signals 数组
```

触发逻辑：`src/api/crave-triggers.js`

**规则**：
- 触发链是同步执行的（在 POST 响应前完成）
- action 卡片每次覆盖（同一天只保留最新版）
- claim 卡片只追加不覆盖（增量证据）

## 9. 变更日志

| 日期 | 变更 | 操作人 |
|------|------|--------|
| 2026-05-18 | v1.0 建立，迁移完成 | ZJB + Claude |
