"""platform-core/中间件/规则指针校验.py

CLAUDE.md 合约二 · 中间处理白盒约束

每个关键转换必须有规则指针——指向规则文件的地址。没有规则文件 = 不能执行。
改规则 = 改规则文件,不准对话中口头改完就走(L104-105)。

合约二 7 个处理动作 → 默认规则文件映射(L107-114):
  数据聚类(persona)        data/rules/persona_clustering.json
  UX 缺口提炼               data/rules/ux_gap_extraction.json
  技术需求优先级判定         data/rules/tech_priority.json
  命题置信度升降             本文件 环2.2 + 附录 E 3.1/4.1/7.1/7.2(已有)
  策略简报生成               data/rules/strategy_brief.json
  归因前置检查               data/rules/attribution_pre_check.json
  看板更新                   data/rules/dashboard_update.json

校验目标(L118-124):
  · 每条结论必须带 rule_source 字段
  · 不许空字符串(L116 "改规则 = 改规则文件")
  · rule_source 应该是真实可访问的文件路径
  · vault 侧 SOP-规则-*.md 双向指针建议(选填校验)

合约零(L52-58)分流:
  · 业务规则(HQ 阈值/CPHQ 灯色/CPA 门槛/命题升降条件):走 vault/2_知识库-AI维护/业务规则/
  · 处理规则(7 个动作):走 data/rules/*.json
  两个容器,本模块支持两种 rule_source 形式

不主动:本模块只校验路径字符串和文件存在,不读规则内容(L67-69 不主动触发外部)。
依赖反向:不 import 上下文层/事件层/引擎层/执行层/其它中间件。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─── 合约二 7 个处理动作 → 默认规则文件 ────────
# 路径相对于 repo_root,本仓库实际位置:platform-core/规则/(P0-9.2 从 crave-AI fork)
PROCESSING_ACTION_TO_RULE: dict[str, str] = {
    "persona_clustering":  "platform-core/规则/persona_clustering.json",
    "ux_gap_extraction":   "platform-core/规则/ux_gap_extraction.json",
    "tech_priority":       "platform-core/规则/tech_priority.json",
    "命题置信度升降":      "CLAUDE.md#环2.2 + 附录 E 规则 3.1/4.1/7.1/7.2",
    "strategy_brief":      "platform-core/规则/strategy_brief.json",
    "attribution_pre_check": "platform-core/规则/attribution_pre_check.json",
    "dashboard_update":    "platform-core/规则/dashboard_update.json",
}

# 兼容 crave-AI 原路径(L107-114 文档里用 data/rules/),做归一化
LEGACY_PATH_PREFIX = "data/rules/"
PLATFORM_PATH_PREFIX = "platform-core/规则/"


# ─── 合约零业务规则容器(L71)──────────────
BUSINESS_RULE_CONTAINER_VAULT = "vault/2_知识库-AI维护/业务规则/"
PROCESSING_RULE_CONTAINER_REPO = "data/rules/"


# ─── 校验结果 ──────────────────────────────
@dataclass
class RuleSourceResult:
    ok: bool
    rule_source: str
    rule_kind: str  # "processing" | "business" | "claude_md" | "unknown"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_vault_pointer: Optional[str] = None

    def report(self) -> str:
        if self.ok:
            head = f"✓ rule_source 校验通过: {self.rule_source!r} ({self.rule_kind})"
        else:
            head = f"✗ rule_source 校验失败: {self.rule_source!r}"
        lines = [head]
        for e in self.errors:
            lines.append(f"  · {e}")
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        if self.suggested_vault_pointer:
            lines.append(f"  💡 建议双向指针: vault 侧创建 {self.suggested_vault_pointer}")
        return "\n".join(lines)


# ─── 主校验入口 ────────────────────────────
def validate(
    rule_source: Optional[str],
    processing_action: Optional[str] = None,
    repo_root: Optional[Path] = None,
    check_file_exists: bool = True,
) -> RuleSourceResult:
    """
    合约二主校验。

    rule_source: 结论里挂的规则指针,如 'data/rules/strategy_brief.json'
    processing_action: 可选,若提供则与 PROCESSING_ACTION_TO_RULE 表交叉校验
    repo_root: 校验文件存在时的 repo 根;None 则不查存在性
    check_file_exists: 是否对 data/rules/*.json 类指针做文件存在性检查
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 必填
    if rule_source is None:
        errors.append("rule_source 必填,不许 None(合约二 L118)")
        return RuleSourceResult(ok=False, rule_source="", rule_kind="unknown", errors=errors)

    rs = str(rule_source).strip()

    # 2. 空字符串阻断(L116)
    if rs == "" or rs == "null" or rs == "None":
        errors.append(
            "rule_source 不许空字符串(合约二 L116:'改规则=改规则文件,"
            "不准对话中口头改完就走')。"
            "确实无规则时,合约零业务规则改用 vault/2_知识库-AI维护/业务规则/ 路径"
        )
        return RuleSourceResult(ok=False, rule_source=rs, rule_kind="unknown", errors=errors)

    # 3. 识别 rule_kind
    rule_kind = _classify(rs)

    # 4. 与 processing_action 交叉校验
    suggested_vault = None
    if processing_action:
        expected = PROCESSING_ACTION_TO_RULE.get(processing_action)
        if expected and expected not in rs:
            warnings.append(
                f"processing_action={processing_action!r} 默认规则文件应为 {expected!r},"
                f"当前 rule_source={rs!r} 不匹配——请确认是否合约二之外的新动作"
            )

    # 5. 文件存在性(仅对 processing JSON 检查)
    if check_file_exists and rule_kind == "processing" and repo_root is not None:
        path_to_check = rs
        # crave-AI legacy 路径先归一(同 6.5 但提前)
        if path_to_check.startswith(LEGACY_PATH_PREFIX):
            path_to_check = path_to_check.replace(LEGACY_PATH_PREFIX, PLATFORM_PATH_PREFIX, 1)
        rs_path = Path(path_to_check) if Path(path_to_check).is_absolute() else Path(repo_root) / path_to_check
        if not rs_path.is_file():
            warnings.append(
                f"规则文件不存在: {rs_path}(合约二要求 rule_source 是真实可读文件;"
                f"未存在 = 该规则尚未沉淀,Claude 输出时应停下来追问 ZJB)"
            )

    # 6. 业务规则建议双向指针(L124)
    if rule_kind == "business":
        suggested_vault = rs if rs.startswith(BUSINESS_RULE_CONTAINER_VAULT) else None
    elif rule_kind == "processing":
        rule_name = Path(rs).stem
        suggested_vault = f"vault/2_知识库-AI维护/操作规范/SOP-规则-{rule_name}.md"

    # 6.5. crave-AI legacy 路径自动归一(P0-9.2 后)
    if rule_kind == "processing" and rs.startswith(LEGACY_PATH_PREFIX):
        normalized = rs.replace(LEGACY_PATH_PREFIX, PLATFORM_PATH_PREFIX, 1)
        warnings.append(
            f"rule_source 用了 crave-AI legacy 路径 {rs!r},"
            f"本仓库实际位置已迁移到 {normalized!r}(P0-9.2 fork 后)。已归一化做校验"
        )
        rs = normalized

    # 7. ZJB 口头/会议 是合法 fallback(附录 C operation_log 格式 L951)
    if rs in ("ZJB 口头", "ZJB 会议", "ZJB 口头/会议"):
        rule_kind = "zjb_oral"
        warnings.append(
            "rule_source='ZJB 口头/会议' — 合法 fallback(附录 C operation_log 格式 L951),"
            "但建议尽快沉淀为 vault/2_知识库-AI维护/业务规则/ 下规则文件"
        )

    # 8. unknown 阻断
    if rule_kind == "unknown":
        errors.append(
            f"rule_source={rs!r} 形态无法识别——必须满足以下任一:\n"
            f"     · data/rules/*.json(处理规则)\n"
            f"     · vault/2_知识库-AI维护/业务规则/规则-*.md(业务规则)\n"
            f"     · CLAUDE.md#... 或 附录 E 规则 X.X(本文件锚点)\n"
            f"     · 'ZJB 口头/会议'(临时 fallback)"
        )

    return RuleSourceResult(
        ok=len(errors) == 0,
        rule_source=rs,
        rule_kind=rule_kind,
        errors=errors,
        warnings=warnings,
        suggested_vault_pointer=suggested_vault,
    )


def _classify(rs: str) -> str:
    if (rs.startswith("data/rules/") or rs.startswith("platform-core/规则/")) and rs.endswith(".json"):
        return "processing"
    if rs.startswith(BUSINESS_RULE_CONTAINER_VAULT):
        return "business"
    if "CLAUDE.md" in rs or "附录 E" in rs or "本文件" in rs or "环" in rs:
        return "claude_md"
    if rs in ("ZJB 口头", "ZJB 会议", "ZJB 口头/会议"):
        return "zjb_oral"
    return "unknown"


def default_rule_for(processing_action: str) -> Optional[str]:
    """合约二查表 - 7 个已知处理动作的默认规则文件"""
    return PROCESSING_ACTION_TO_RULE.get(processing_action)


# ─── CLI 自测 ──────────────────────────────
if __name__ == "__main__":
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]

    # 模拟 crave-AI repo 已有的规则文件(本 repo 没有,所以会触发"文件不存在"warning)
    scenarios = [
        ("场景 1 · 合法处理规则(strategy_brief)", {
            "rule_source": "data/rules/strategy_brief.json",
            "processing_action": "strategy_brief",
        }),

        ("场景 2 · 合法业务规则(vault 容器)", {
            "rule_source": "vault/2_知识库-AI维护/业务规则/规则-CPHQ阈值.md",
        }),

        ("场景 3 · 合法 CLAUDE.md 锚点", {
            "rule_source": "本文件 环2.2 置信度体系",
        }),

        ("场景 4 · 空字符串(L116 阻断)", {
            "rule_source": "",
        }),

        ("场景 5 · None 必填(L118 阻断)", {
            "rule_source": None,
        }),

        ("场景 6 · 不规范路径(unknown 阻断)", {
            "rule_source": "我自己拍的规则",
        }),

        ("场景 7 · processing_action 与文件不匹配(warning)", {
            "rule_source": "data/rules/strategy_brief.json",
            "processing_action": "persona_clustering",  # 应该是 persona_clustering.json
        }),

        ("场景 8 · ZJB 口头(合法 fallback)", {
            "rule_source": "ZJB 口头/会议",
        }),

        ("场景 9 · null 字面值(等价空字符串,阻断)", {
            "rule_source": "null",
        }),

        ("场景 10 · 处理规则文件不存在(warning,不阻断)", {
            "rule_source": "data/rules/strategy_brief.json",
        }),
    ]

    for title, kwargs in scenarios:
        print(f"\n━━━ {title} ━━━")
        print(f"输入: {kwargs}")
        vr = validate(**kwargs, repo_root=repo_root)
        print(vr.report())

    print("\n━━━ 附:7 个已知处理动作的默认规则查询 ━━━")
    for action in PROCESSING_ACTION_TO_RULE:
        print(f"  {action:30s} → {default_rule_for(action)}")
