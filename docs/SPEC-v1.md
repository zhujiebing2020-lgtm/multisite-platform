# z-jb.com 平台重构规格书 v1.0

> ZJB 确认于 2026-05-15。Claude Code 实施时逐章对照，不自行发明。

---

## 一、核心原则

1. **Agent 建议永远不自动执行** — 所有 Agent 输出"建议卡片"，投手人工确认后自己去 FB/Google 后台操作。平台只记录状态，不直接调用广告 API。
2. **站是数据的标签，不是导航的层级** — 投手登录后看到自己负责的所有数据，站点是顶部筛选器。
3. **视觉风格沿用现有橙色系** — CSS 变量保留（--accent:#E8603A，--bg:#F6F3EE）。借鉴 crave-AI 交互模式，不照搬视觉。
4. **删除旧页面入口** — upload/agents/results.html 功能全部内嵌到主 app 对应视图。
5. **为多租户预留接口，但现在不实现** — 表加 tenant_id，路由预留 /api/tenant/:id/，当前单租户运行。

---

## 二、角色体系

| 角色 | 代码 | 谁用 | 能看 | 能做 |
|------|------|------|------|------|
| 平台管理员 | admin | ZJB | 全部 | 一切+用户管理+规则编辑 |
| 投手 | pitcher | HZM等 | 分配站点数据 | 上传xlsx/确认拒绝建议/触发Agent |
| 技术 | tech | 技术同学 | 承接诊断视图 | 查看断点/标记修复状态 |

viewer 角色预留字段，当前不实现。

---

## 三、视图结构

```js
const VIEWS = {
  invest:    { label: '📊 投放',     roles: ['admin','pitcher'] },
  accept:    { label: '🛠 承接诊断', roles: ['admin','tech'] },
  strategy:  { label: '⚙️ 策略',     roles: ['admin','pitcher'] },
  creative:  { label: '🎨 素材',     roles: ['admin','pitcher'] },
  control:   { label: '🏠 总控',     roles: ['admin'] },
  knowledge: { label: '📚 知识库',   roles: ['admin'] },
};
```

顶部布局：`[品牌] ── [视图tabs] ── [用户名·退出]` + `[站点筛选] [日期范围]`

---

## 四、各视图规格

### 4.1 投放视图（invest）

左右两栏（60%/40%）。

**左栏：广告组表现**
- KPI行：今日花费 / 全局CPHQ / 活跃S类组数 / 今日HVU
- 表格字段：广告组名称/站点/分层(S/A/B/O)/花费7日/HVU7日/CPHQ/趋势/Agent建议
- 点击行→右侧抽屉展开详情

**右栏：操作区（Accordion）**
- 面板1：上传数据（拖拽+字段预览+确认）
- 面板2：Agent建议队列（待确认卡片，按风险排序）
- 面板3：手动触发Agent（评论/视频/策略刷新）

### 4.2 承接诊断视图（accept）

KPI行：HQ1命中率 / HQ2命中率 / 结算页流失率 / 支付成功率

断点列表卡片：优先级/位置/流失率/诊断/修复建议/负责人/状态下拉

### 4.3 策略视图（strategy）

左右两栏：左=运营规则表（admin可编辑），右=命题库（从crave-AI同步）

### 4.4 素材视图（creative）

输入表单→Agent5生成Creative Brief（Hook文案×3/标题/受众/合规状态）

### 4.5 总控视图（control）

三端汇总卡片（广告端/独立站端/用户端）+ 用户管理 + Agent运行日志

### 4.6 知识库视图（knowledge）

三Tab：已验证命题 / 拒绝记录分析 / 规则库版本历史

---

## 五、数据库表结构

### 现有表扩展

```sql
ALTER TABLE users ADD COLUMN tenant_id TEXT DEFAULT 'internal';
ALTER TABLE users ADD COLUMN assigned_sites TEXT DEFAULT '[]';

ALTER TABLE operation_log ADD COLUMN agent_id TEXT;
ALTER TABLE operation_log ADD COLUMN trigger_type TEXT;
ALTER TABLE operation_log ADD COLUMN outcome_30d TEXT;
ALTER TABLE operation_log ADD COLUMN contribute_to_global INTEGER DEFAULT 1;
```

### 新增表

```sql
CREATE TABLE ad_spend (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_name TEXT NOT NULL,
  site TEXT NOT NULL,
  spend_usd REAL NOT NULL,
  date_start TEXT NOT NULL,
  date_end TEXT NOT NULL,
  uploaded_by TEXT NOT NULL,
  uploaded_at TEXT NOT NULL,
  tenant_id TEXT DEFAULT 'internal'
);

CREATE TABLE agent_recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT NOT NULL,
  group_name TEXT,
  site TEXT,
  recommendation TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  pitcher_action TEXT,
  rejection_reason TEXT,
  confirmed_by TEXT,
  confirmed_at TEXT,
  executed_at TEXT,
  outcome_30d TEXT,
  contribute_to_global INTEGER DEFAULT 1,
  created_at TEXT NOT NULL,
  tenant_id TEXT DEFAULT 'internal'
);

CREATE TABLE knowledge_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL,
  source TEXT,
  validated_at TEXT,
  created_at TEXT NOT NULL
);
```

---

## 六、Agent 注册表

7个Agent：data_sync / spend_parser / strategy / accept / creative / knowledge / orchestrator

详见 agent_registry.json（项目根目录）。

---

## 七、建议卡片状态机

```
pending → confirmed → executed → reviewing → verified_correct / verified_wrong
pending → rejected → (30天后) → pitcher_correct / agent_correct
```

拒绝时必填原因。30天后 knowledge_agent 自动回看。

---

## 八、xlsx 上传规范

必填列：广告组名称 / 花费
可选列：日期/CPM/CPC/曝光/点击/购买

上传后：解析→预览→确认→写入ad_spend→触发strategy_agent

---

## 九、API 路由

新增：
```
POST /api/upload/spend
GET  /api/recommendations?site=&status=&agent=
PUT  /api/recommendations/:id
GET  /api/knowledge
POST /api/knowledge/:id/to-rule
GET  /api/agents/status
POST /api/agents/:id/trigger
GET  /api/cross-site/summary
```

多租户预留：`/api/tenant/:tenant_id/...`

---

## 十、CSS 变量扩展

```css
:root {
  --risk-low:#18A057; --risk-medium:#D29922; --risk-high:#D94030;
  --status-pending:#3A9FE8; --status-confirmed:#D29922; --status-executed:#18A057;
  --status-rejected:#9A8F85; --status-verified:#E8603A;
  --tier-s:#18A057; --tier-a:#3A9FE8; --tier-b:#D29922; --tier-o:#9A8F85;
  --drawer-bg:#FFFFFF; --drawer-shadow:0 4px 24px rgba(0,0,0,0.10);
}
```

---

## 十一、删除清单

- upload.html / agents.html / results.html
- 导航栏指向旧页面的链接
- 投放视图独立"我的结果"区块（改为广告组详情抽屉内展示）

---

## 十二、不在范围内

- Agent 实际执行逻辑（Python/Docker）
- AdClaw MCP 实际调用
- 可灵 API 图片生成
- 多租户登录系统
- 客户报告页
- 自动执行广告操作
