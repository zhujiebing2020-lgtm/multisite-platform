# multisite-platform

多站群多 agent 平台。**平台是发动机,站是车壳。**

## 一句话

**Site 不是模块,是参数空间。Agent 不属于站,带着站的上下文运行。**

> 注:此句源自 §15 SVG 隐含含义(同 agent 不同上下文 → 不同行为)。等 ZJB 拍板后可升 memory 永久约束。

## 目录映射 SVG 6 层

```
platform-core/                  发动机(对外稳定接口,客户剥站后可独立跑)
  监管层/                       SVG L1 · Master Runtime · 跨站仲裁/资源调度/复制
  上下文层/                     SVG L2 · Site Runtime Context · 站身份与四层覆盖加载
    loader.md                   稳定接口文档
    loader.py                   load_site_config 实现
    context.py                  LoadedConfig dataclass
    defaults.yaml               L1 平台默认阈值(全平台 1 份扁平,不分 agent)
  事件层/                       SVG L3 · 持续监听 4 类事件
                                HVU下降 / 埋点失效 / 预算触顶 / 素材老化
  引擎层/                       SVG L4 · Runtime Task Engine · 状态机/优先级/队列/回滚/历史继承
                                事件→任务映射表存这(loader.md §15.6 未决项之一)
  执行层/                       SVG L5 · 4 Domain Agents
    流量-投放/
    技术-埋点/
    数据-归因/
    创意-素材/
  数据层/                       SVG L6 · Data Runtime · 状态写回/执行日志/事件源

  能力包/                       三层能力包(数据/配置,挂在 6 层上)
    打法包-投手能力/             → 挂上下文层(§15.3)
    产出包-自动化生产/           → 挂引擎层(任务类型)
    内容包-调性话术/             → 挂执行层(Agent 入参)

sites/                          车壳(每站独立,严格隔离)
  elysianu/
    config.yaml                 L3 站级覆盖 + 打法包引用
    assets/                     素材
    data-inbox/                 只丢不处理,等数据层扫

tools/customer-export/          P1 卖站剥离脚本
docs/                           架构文档 + SVG
```

## 参数四层覆盖(loader.md §3)

```
L1 platform-core/上下文层/defaults.yaml
L2 platform-core/能力包/打法包-投手能力/{打法包}.yaml#thresholds_overrides
L3 sites/{site_id}/config.yaml#thresholds_overrides
L4 runtime 临时(不持久化)
```

最右侧有值的层赢。

## 硬约束

1. **依赖方向单向:** `platform-core/` 不许 import `sites/`。客户剥站后必须能独立跑。
2. **crave-AI 只读复刻:** 不得在 `~/Documents/GitHub/crave-AI/` 下做任何写操作。
3. **稳定接口 SemVer:** `LoadedConfig` 字段只加不删。

## 入口文档

- `platform-core/上下文层/loader.md` — 稳定接口第一层(config 加载 + 四层覆盖)
- `docs/架构思路-v3.md` — 完整架构 §1-§15
- `docs/runtime-os-视图.svg` — §15 配图

## 当前状态(2026-05-13 EOD)

- 骨架 init 完成(本 commit)
- L1 defaults + 打法包 + 站 config + loader.py 入库
- 待跑通:`python3 platform-core/上下文层/loader.py elysianu`
- 待 ZJB 拍:E3 打法包激进阈值具体数值(目前 TBD)
