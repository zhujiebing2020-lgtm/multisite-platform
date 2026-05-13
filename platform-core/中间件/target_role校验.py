"""platform-core/中间件/target_role校验.py

CLAUDE.md 合约三 · 输出端 target_role 校验

所有结论性数据必须带 target_role 数组。5 枚举封闭,至少 1 个最多 3 个。

5 枚举(L135-146):
  投手      CHJ/HNN/HZM/ZXR/LZL/PLZ · 调素材/账户/定向/预算
  承接层    吴玲/田棒棒/吴慧妍/陆佳炜/柴碧如 · 改页面/客服/内容/视觉
  技术      郭刚/曾凡立 · 埋点/API/站点改动/工具自动化
  ZJB排查   ZJB 反驳+排查(对 Claude 数据结论;业务规则定义权仍在 ZJB)
  Claude    Claude 下一轮自用任务,不对外派发

演进标记(L156-159):
  "跑正周"首次出现 → ZJB排查 升级为 ZJB决策
  本模块默认停在 ZJB排查,升级由 ZJB 确认后切换 MODE

domain × 默认 target_role 映射(附录 A.10 L874-885):
  fb-ops          → [投手]
  landing-page    → [承接层, 技术]
  audience        → [投手, 承接层]
  risk            → [ZJB排查]
  metrics         → [ZJB排查, Claude]
  product         → [ZJB排查, 承接层]
  channel-collab  → [投手, ZJB排查]

输出语气规则(L126-130):
  投手/承接层/技术    陈述句 + 可执行判断(不加 next_action)
  ZJB排查             提问句式(不坚信对错)
  Claude              陈述句,面向自身下一轮

next_action 规则(L150-153):
  软结论(persona/gap/insight)不加 next_action
  业务规则触发的自动链路(命题升可信自动执行桥等)保留

依赖反向硬约束:不 import 上下文层/事件层/引擎层/执行层/其它中间件。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── 合约三 L135 五枚举(封闭)────────────────
class TargetRole(str, Enum):
    PITCHER = "投手"
    ACCEPT = "承接层"
    TECH = "技术"
    ZJB_REVIEW = "ZJB排查"    # 当前默认模式
    ZJB_DECIDE = "ZJB决策"    # 跑正周后演进(L156)
    CLAUDE = "Claude"

    @classmethod
    def valid_set(cls, mode: str = "pre_running_positive") -> set[str]:
        """
        按模式返回合法枚举值集合。
        pre_running_positive (默认) — 跑正周前,用 ZJB排查
        post_running_positive        — 跑正周后,ZJB排查 升级为 ZJB决策
        """
        if mode == "post_running_positive":
            return {cls.PITCHER, cls.ACCEPT, cls.TECH, cls.ZJB_DECIDE, cls.CLAUDE}
        return {cls.PITCHER, cls.ACCEPT, cls.TECH, cls.ZJB_REVIEW, cls.CLAUDE}


# ─── 附录 A.10 L874 domain × 默认 target_role 映射 ───
DOMAIN_TO_DEFAULT_ROLES: dict[str, list[TargetRole]] = {
    "fb-ops":          [TargetRole.PITCHER],
    "landing-page":    [TargetRole.ACCEPT, TargetRole.TECH],
    "audience":        [TargetRole.PITCHER, TargetRole.ACCEPT],
    "risk":            [TargetRole.ZJB_REVIEW],
    "metrics":         [TargetRole.ZJB_REVIEW, TargetRole.CLAUDE],
    "product":         [TargetRole.ZJB_REVIEW, TargetRole.ACCEPT],
    "channel-collab":  [TargetRole.PITCHER, TargetRole.ZJB_REVIEW],
}


# ─── 输出语气(L126-130)─────────────────────
TONE_RULE = {
    TargetRole.PITCHER:    "陈述句+可执行判断,不加 next_action",
    TargetRole.ACCEPT:     "陈述句+可执行判断,不加 next_action",
    TargetRole.TECH:       "陈述句+可执行判断,不加 next_action",
    TargetRole.ZJB_REVIEW: "必须提问句式(例:'这里是否有 X 可能?')不用命令句,不坚信自己对",
    TargetRole.ZJB_DECIDE: "陈述句+可执行判断(跑正周后演进态)",
    TargetRole.CLAUDE:     "陈述句,面向自身下一轮处理",
}


# ─── 结论类型 → 是否允许 next_action(L150-153)─
SOFT_CONCLUSION_TYPES = {
    "persona", "gap", "tech_need", "insight", "suggestion",
    "命题变化", "data_insight",
}  # 软结论 → 禁止 next_action

SYSTEM_FLOW_TYPES = {
    "命题升可信_自动执行桥",
    "ROI负_自动降置信度",
    "看板越线_自动提示",
}  # 业务内置流程 → 允许自动后续,不算 next_action 预设


# ─── 校验结果 ──────────────────────────────
@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    roles: list[TargetRole] = field(default_factory=list)
    tone_hints: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = []
        if self.ok:
            lines.append(f"✓ target_role 校验通过: {[r.value for r in self.roles]}")
        else:
            lines.append("✗ target_role 校验失败:")
            for e in self.errors:
                lines.append(f"  · {e}")
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        if self.tone_hints:
            lines.append("语气提示:")
            for t in self.tone_hints:
                lines.append(f"  · {t}")
        return "\n".join(lines)


# ─── 主校验入口 ────────────────────────────
def validate(
    roles: list,
    mode: str = "pre_running_positive",
    conclusion_type: Optional[str] = None,
    has_next_action: bool = False,
) -> ValidationResult:
    """
    合约三主校验。

    roles: 可接受 str 列表(如 ["投手", "承接层"])或 TargetRole 列表
    mode:  pre_running_positive(默认,用 ZJB排查)/ post_running_positive(用 ZJB决策)
    conclusion_type: 用于 next_action 白名单判断
    has_next_action: 输出里是否有 next_action 字段
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 存在性
    if not roles:
        errors.append("target_role 必填,不许为空(合约三 L149)")
        return ValidationResult(ok=False, errors=errors)

    # 2. size 1-3
    if len(roles) > 3:
        errors.append(f"target_role 最多 3 个,当前 {len(roles)} 个——超过 3 = 没想清楚,回去重聚(L149)")
    if len(roles) < 1:
        errors.append("target_role 至少 1 个")

    # 3. 枚举合法 + 归一
    valid = TargetRole.valid_set(mode)
    normalized: list[TargetRole] = []
    for r in roles:
        if isinstance(r, TargetRole):
            target = r
        else:
            s = str(r).strip()
            try:
                target = TargetRole(s)
            except ValueError:
                errors.append(
                    f"target_role={s!r} 不在 5 枚举封闭集合内(合法值: {sorted(v.value for v in valid)})"
                )
                continue
        if target not in valid:
            errors.append(
                f"target_role={target.value!r} 在当前模式({mode})下不合法。"
                f"ZJB排查/ZJB决策 二选一,取决于是否已跑正周(L156)"
            )
            continue
        normalized.append(target)

    # 4. 去重
    seen = set()
    dedup: list[TargetRole] = []
    for r in normalized:
        if r in seen:
            warnings.append(f"target_role={r.value!r} 重复出现,已去重")
        else:
            seen.add(r)
            dedup.append(r)

    # 5. next_action 规则(L150-153)
    if has_next_action:
        ctype = conclusion_type or ""
        if ctype in SOFT_CONCLUSION_TYPES:
            errors.append(
                f"软结论 {ctype!r} 禁止带 next_action(合约三 L151)。"
                f"这类结论指向岗位,不预设行动,由 ZJB 拍板再分发"
            )
        elif ctype in SYSTEM_FLOW_TYPES:
            pass  # 业务内置流程,允许
        else:
            warnings.append(
                f"conclusion_type={ctype!r} 未分类,has_next_action=True 请确认是否业务内置流程(L152)"
            )

    # 6. 语气提示(提醒 Claude 生成对应 target_role 输出时的行文)
    tone_hints = [f"{r.value}: {TONE_RULE.get(r, '')}" for r in dedup]

    return ValidationResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        roles=dedup,
        tone_hints=tone_hints,
    )


def default_roles_for_domain(domain: str) -> list[TargetRole]:
    """按 domain 查默认 target_role(新建命题时用,附录 A.10)"""
    return DOMAIN_TO_DEFAULT_ROLES.get(domain, [])


# ─── CLI 自测 ──────────────────────────────
if __name__ == "__main__":
    scenarios = [
        ("场景 1 · 合法投放结论", {
            "roles": ["投手"],
            "conclusion_type": "ad_group_suggestion",
            "has_next_action": False,
        }),

        ("场景 2 · 合法跨岗位(3 个上限)", {
            "roles": ["ZJB排查", "投手", "承接层"],
            "conclusion_type": "需求检查",
            "has_next_action": False,
        }),

        ("场景 3 · 超过 3 个(没想清楚)", {
            "roles": ["投手", "承接层", "技术", "ZJB排查"],
            "conclusion_type": "",
        }),

        ("场景 4 · 非法枚举值(运营 不是合法角色)", {
            "roles": ["运营", "投手"],
            "conclusion_type": "",
        }),

        ("场景 5 · 软结论带 next_action(违反 L151)", {
            "roles": ["投手"],
            "conclusion_type": "insight",
            "has_next_action": True,
        }),

        ("场景 6 · 业务内置流程允许 next_action", {
            "roles": ["投手"],
            "conclusion_type": "命题升可信_自动执行桥",
            "has_next_action": True,
        }),

        ("场景 7 · 空 roles(必填缺失)", {
            "roles": [],
            "conclusion_type": "",
        }),

        ("场景 8 · ZJB排查(当前模式)+ 语气提示", {
            "roles": ["ZJB排查", "Claude"],
            "conclusion_type": "metrics",
        }),

        ("场景 9 · ZJB决策(post_running_positive 模式)", {
            "roles": ["ZJB决策"],
            "conclusion_type": "metrics",
            "mode": "post_running_positive",
        }),

        ("场景 10 · 当前模式下用 ZJB决策(尚未跑正周,非法)", {
            "roles": ["ZJB决策"],
            "conclusion_type": "metrics",
            "mode": "pre_running_positive",
        }),
    ]

    for title, kwargs in scenarios:
        print(f"\n━━━ {title} ━━━")
        mode = kwargs.pop("mode", "pre_running_positive")
        print(f"输入: roles={kwargs.get('roles')} type={kwargs.get('conclusion_type')!r} "
              f"has_next_action={kwargs.get('has_next_action', False)} mode={mode}")
        vr = validate(**kwargs, mode=mode)
        print(vr.report())

    print("\n━━━ 附:domain 默认 target_role 查询 ━━━")
    for d in ("fb-ops", "landing-page", "risk", "metrics"):
        roles = default_roles_for_domain(d)
        print(f"  domain={d:15s} → {[r.value for r in roles]}")
