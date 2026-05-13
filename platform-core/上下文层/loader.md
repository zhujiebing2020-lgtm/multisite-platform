# platform-core/runtime/loader.md

> 站 config → agent 运行参数 的稳定接口定义
> 归属:`platform-core/runtime/loader.md`(repo init 前暂存 iCloud 多站群 多agent/)
> 版本:0.1-draft(2026-05-13)
> 对齐:v3 §3.2 / §3.4 / §12 / §13.3
> 作用:在写第一个打法包 yaml 之前,先把"打法包引用如何被运行时消费"定死

---

## 0. 为什么需要这篇文档

v3 §13.3 立了硬约束:**platform-core 自洽 / sites 只走稳定接口**。但"稳定接口"长什么样没写。
本文档定义第一层稳定接口:**config 加载 + 参数解析 + 覆盖优先级**。

没有这一层,投手写 `打法包: 投手A-成人付费-激进@v2.5` 的时候,没人知道 runtime 怎么把这串引用翻译成 agent 能用的参数。

---

## 1. 运行时从哪里读取站的 config

### 1.1 发现机制

runtime 启动 + 每次 agent 调用前,扫描 `sites/*/config.yaml`(glob 模式)。
发现一个目录有 `config.yaml` = 发现一个站。没有 `config.yaml` = 不是站,跳过。

```
sites/
  ├─ elysianu/
  │   ├─ config.yaml        ← runtime 读这里
  │   ├─ assets/
  │   └─ data-inbox/
  └─ 下一个站/
      └─ config.yaml
```

### 1.2 依赖方向(§13.3 硬约束)

```
platform-core/runtime/loader.py
  ├─ 读取:sites/{site_id}/config.yaml        ✅ 允许
  ├─ 读取:platform-core/packages/打法包-投手能力/*.yaml  ✅ 允许
  ├─ 读取:platform-core/agents/*/defaults.yaml          ✅ 允许
  └─ 从 sites/ 下 import Python 代码                    ❌ 禁止

sites/{site_id}/
  └─ 向 platform-core 反向依赖 Python 代码              ❌ 禁止
```

**这条是 §13.3 客户剥离的生命线:** 客户剥走 sites/{他的站} + platform-core 子集后,他 repo 里不能存在"platform-core 代码 import 了别的 site 目录"这种反向引用,否则升级必炸。

### 1.3 加载触发点

三个时机触发 `load_site_config(site_id)`:

1. **runtime 冷启动** — 扫全部 site,建内存索引
2. **agent 调用前** — `invoke_agent(agent_name, site_id, ...)` 第一件事就是 load(确保用的是最新 config)
3. **站级配置热更新** — 投手改 config.yaml 存盘,runtime 监听到变动 → 重新 load(实现细节 P1,不阻塞本文档)

### 1.4 输入与输出

```python
# 平台对外稳定接口
def load_site_config(site_id: str) -> LoadedConfig: ...
```

**输入:** `site_id`(对应 `sites/{site_id}/` 目录名)
**输出:** `LoadedConfig` 结构化对象,字段见 §2.3

**错误情况:**
| 情况 | 行为 |
|---|---|
| 站目录不存在 | raise `SiteNotFoundError(site_id)` |
| config.yaml 缺失 | raise `ConfigMissingError(site_id)` |
| config.yaml 语法错 | raise `ConfigParseError(site_id, yaml_error)` |
| 引用的打法包不存在 | raise `PlaybookNotFoundError(ref)` |
| 打法包 category 与站 category 不匹配 | raise `CategoryMismatchError(site.category, playbook.category)`(§3.4) |

错误一律向上冒,不 silent fallback。loader 里 silent fallback = 投手以为挂了打法包其实没挂 = 空跑烧钱,绝不允许。

---

## 2. 打法包引用如何解析成 agent 参数

### 2.1 引用语法

站 config.yaml 里的引用:

```yaml
# sites/elysianu/config.yaml
_meta:
  site_id: elysianu
  owner: HZM
  category: 成人付费

打法包: 投手HZM-成人付费-激进@v2.5   # ← 这条引用
产出包:
  - ad-video-广告视频
```

**引用格式:** `{author}-{category}-{stage}@{version}`
- 四段全部强制(§3.2 命名规范)
- 缺一段 loader 拒绝加载(`PlaybookRefSyntaxError`)
- `@version` 可省略 → 默认拿 latest(但 production 站强烈建议 pin 版本)

### 2.2 解析流程(五步)

```
Step 1 · 读站 config
  sites/elysianu/config.yaml → 拿到引用字符串 "投手HZM-成人付费-激进@v2.5"

Step 2 · 定位打法包文件
  packages/打法包-投手能力/投手HZM-成人付费-激进.yaml
  版本在 yaml 内 _meta.version 字段,不在文件名里

Step 3 · 版本匹配
  读 _meta.version,若和引用的 @v2.5 不符 → PlaybookVersionMismatchError
  (将来如果一个 yaml 支持多版本,这里改逻辑;MVP 一个文件一版本)

Step 4 · category 校验(§3.4)
  assert playbook._meta.category == site._meta.category
  不等 → CategoryMismatchError

Step 5 · 合并参数
  按 §2.4 的四层优先级,合并出 resolved_thresholds
```

### 2.3 LoadedConfig 结构

```python
@dataclass
class LoadedConfig:
    # === 站级信息 ===
    site_id: str
    owner: str
    category: str
    
    # === 打法包解析结果 ===
    playbook_ref: str              # 原始引用字符串,审计用
    playbook_author: str
    playbook_version: str
    playbook_stage: str            # 起步/稳健/激进/收割
    playbook_lineage: list[str]    # 传承链,审计用
    
    # === agent 运行参数 ===
    enabled_roles: list[str]       # [通用-common, 投放-ads, ...]
    active_flow: str               # paid-ads-付费流量
    resolved_thresholds: dict      # 四层合并后,agent 实际用的阈值
    
    # === 产出包 ===
    production_packages: list[PackageConfig]
    
    # === 预算与闸门 ===
    budget_limits: BudgetConfig    # daily_cap / monthly_cap / breach_action
    creative_refresh: RefreshConfig # monthly_cap / approval_window_h / on_timeout
```

**稳定接口版本标记:** `LoadedConfig` 结构变动走 SemVer。字段只加不删,删字段或改类型 = major 版本 = 客户剥离 repo 必须同步升级 platform-core(§13.3 sync 脚本处理)。

### 2.4 runtime 调用 agent 时的入参注入

这是 §12.1 agent 入参 `overrides` 字段的**真实来源**:

```python
def invoke_agent(agent_name: str, site_id: str, 
                 time_window: TimeWindow,
                 upstream_output: dict | None = None,
                 runtime_overrides: dict | None = None) -> AgentResult:
    # 1. 加载站配置
    cfg = load_site_config(site_id)
    
    # 2. 取出该 agent 需要的 thresholds 子集
    agent_thresholds = cfg.resolved_thresholds[agent_name]
    
    # 3. 构造 §12.1 规定的 agent 入参
    input = AgentInput(
        site_id=site_id,
        time_window=time_window,
        upstream_output=upstream_output,
        overrides={**agent_thresholds, **(runtime_overrides or {})},
    )
    
    # 4. 调用 agent
    return agents[agent_name].run(input)
```

`runtime_overrides` 是最顶层,用于投手手动重跑某次调用时的临时参数(比如"这次我想用 cphq_green_max=15 试一把"),不落盘,一次性。

---

## 3. 参数覆盖优先级(四层,不是三层)

从低到高(上层覆盖下层):

```
L1 · 平台默认
     platform-core/agents/{role}/defaults.yaml
     作用:保底,每个 agent 自带一套出厂参数
     示例:analyst_agent 的 lookback_days=7

L2 · 打法包覆盖
     packages/打法包-投手能力/{投手}-{品类}-{风格}.yaml 里的 thresholds_overrides
     作用:投手的打法偏好
     示例:激进打法把 pause_on_hvu_zero_days 从 3 调到 1

L3 · 站级覆盖
     sites/{site_id}/config.yaml 里的 thresholds_overrides(可选字段)
     作用:站特定异常 / 临时应对
     示例:折扣站对 CTR 衰减更敏感,这里把 ctr_decay_pct 从 30 调到 20
     白名单:§12.6 提过,只有特定字段允许站级覆盖,防止投手把 agent 搞崩

L4 · 运行时临时覆盖
     runtime.invoke_agent(..., runtime_overrides={...})
     作用:一次性调用参数调整,不落盘
     示例:投手在控制台点"用这个参数重跑一次",调完不影响 config
```

### 3.1 为什么是四层不是三层

ZJB 原问题写"平台默认 → 打法包覆盖 → 站级覆盖",三层。
补第四层是因为 §12.1 已经规定了 agent 入参有 `overrides` 字段,这是**运行时临时**的,和三层落盘参数是不同东西。不补会出现"§12 接口有入口但 loader 没人注入"的矛盾。

### 3.2 合并语义

每一层是**字段级覆盖**,不是整体替换:

```yaml
# L1 defaults.yaml
thresholds:
  ctr_decay_pct: 30
  lookback_days: 7
  pause_on_hvu_zero_days: 3

# L2 打法包.yaml
thresholds_overrides:
  pause_on_hvu_zero_days: 1       # 只改这一个

# L3 站 config.yaml
thresholds_overrides:
  ctr_decay_pct: 20               # 只改这一个

# 合并后 agent 看到的
{
  ctr_decay_pct: 20,              # L3 覆盖
  lookback_days: 7,               # L1 原值
  pause_on_hvu_zero_days: 1,      # L2 覆盖
}
```

### 3.3 审计与溯源

agent 调用日志(§11.6 的 agent_calls 表)必须记:
- 每个字段的**最终值**是来自 L1 / L2 / L3 / L4 哪一层
- 这样出问题时能回答"为什么这次调用用的是 20 不是 30"

实现上:`resolved_thresholds` 结构里每个字段带一个 `source` 标记。

---

## 4. 对外稳定接口清单(SemVer v0.1)

对 sites/ 和客户剥离的 repo 来说,下面这组是"稳定"的,platform-core 内部实现可以重构但这些签名不变:

```python
# runtime/loader.py
load_site_config(site_id: str) -> LoadedConfig

# runtime/invoker.py
invoke_agent(agent_name, site_id, time_window, 
             upstream_output=None, runtime_overrides=None) -> AgentResult

# 结构体
LoadedConfig (§2.3 字段)
AgentInput   (§12.1 字段)
AgentResult  (§12.2 字段)

# 异常类
SiteNotFoundError, ConfigMissingError, ConfigParseError,
PlaybookNotFoundError, PlaybookRefSyntaxError, PlaybookVersionMismatchError,
CategoryMismatchError
```

**破坏性变更规则:** 签名、字段、异常类的任何 rename/删除/类型变 = major 版本 bump,客户 sync 脚本必须触发迁移提示。

---

## 5. 未决(小,不阻塞 P0-3)

- 热更新(§1.3 第 3 种触发点)实现方式:文件系统 watcher vs 定时扫描,P1 再定
- L3 站级覆盖的白名单具体字段清单,等第一个打法包写完回头填
- `@latest` 语义是"文件里最新 version"还是"所有同名打法包里 version 最大",MVP 默认前者,后者留 P1
- 打法包 fork 链的 lineage 长度上限(防止 fork 链过长拖慢解析),P1 定

---

## 6. 下一步

本文档(0.1-draft)定了 loader 形态后,P0-3 立刻可以动:

1. 写 `packages/打法包-投手能力/投手HZM-成人付费-激进.yaml`(从 crave-ai 主站打法 fork,forked_from 填主站打法引用)
2. 写 `sites/elysianu/config.yaml`(owner: HZM,category: 成人付费,打法包引用,产出包 ad-video)
3. 本文档落到 `platform-core/runtime/loader.md` 与代码同目录(repo init 后)
