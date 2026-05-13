"""platform-core/执行层/知识沉淀/agent.py

知识沉淀 agent · 命题提炼 + 置信度管理

职责(CLAUDE.md 环2 全流程):
  · 从数据分析/归因诊断的输出中提取可被证伪的陈述句
  · 三要素校验:可量化 / 有条件 / 有对比
  · 置信度 4 态:存疑 → 可信 → 确认 / 证伪
  · 30 天换壳复现检查(合约四B)
  · 命题升「可信」时自动触发执行桥(附录 E 规则 3.1)

输出:
  · target_role=[ZJB排查, Claude](命题判断归 ZJB 排查)
  · rule_source=本文件 环2.2 置信度体系
  · emit_events=[{type: 命题升可信_自动}] 当置信度升级时
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

PLATFORM_CORE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM_CORE / "中间件"))
sys.path.insert(0, str(PLATFORM_CORE / "执行层"))

from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402
from target_role校验 import validate as validate_role  # noqa: E402
from 规则指针校验 import validate as validate_rule  # noqa: E402

name = "知识沉淀"
RULE_SOURCE = "CLAUDE.md#环2.2 置信度体系 + 附录 E 规则 3.1/4.1/7.1/7.2"
DATA_DIR = PLATFORM_CORE / "数据底盘"


# ─── 三要素校验(环2.1 Step 1)─────────────
def _check_three_elements(observation: dict) -> tuple[bool, list[str]]:
    """
    命题三要素:可量化 / 有条件 / 有对比
    返回 (通过, 缺失要素列表)
    """
    missing = []
    if not observation.get("quantifiable"):
        missing.append("可量化(需有具体指标或数字)")
    if not observation.get("conditional"):
        missing.append("有条件(需明确人群/场景/平台限定)")
    if not observation.get("comparative"):
        missing.append("有对比(需 A vs B 或前后对比,有样本量)")
    return len(missing) == 0, missing


# ─── 置信度判定(环2.2)─────────────────
CONFIDENCE_LEVELS = ["存疑", "可信", "确认", "证伪"]

def _assess_confidence(
    evidence_for: int,
    evidence_against: int,
    sample_size: int,
    cross_validated: bool,
    has_roi_positive: bool,
) -> tuple[str, str]:
    """
    返回 (置信度, 判定理由)
    规则:
      单一来源 + 样本<5 → 存疑
      多次重复或样本量大 → 可信
      跨投手/跨时段验证 + ROI>0 → 确认
      持续被否定 → 证伪
    """
    if evidence_against >= 3:
        return "证伪", f"反例 {evidence_against} 条,持续被后续数据否定"
    if cross_validated and has_roi_positive:
        return "确认", "跨投手/跨时段验证 + ROI 稳定为正"
    if sample_size >= 10 or evidence_for >= 3:
        return "可信", f"样本量 {sample_size} / 支持证据 {evidence_for} 条"
    return "存疑", f"单一来源,样本 {sample_size} < 10"


# ─── 主 agent 入口 ────────────────────────
def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}

    # 从上游(数据分析/归因诊断)获取观察列表
    observations = upstream.get("observations", [])
    existing_claims = upstream.get("existing_claims", [])
    env_flag_active = upstream.get("env_flag_active", False)

    if not observations:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason="上游未传入 observations(数据分析/归因诊断的输出)",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 处理每条观察
    new_claims = []
    upgraded_claims = []
    rejected_observations = []
    emit_events = []

    for obs in observations:
        # Step 1 · 三要素校验
        passed, missing = _check_three_elements(obs)
        if not passed:
            rejected_observations.append({
                "observation": obs.get("statement", "?"),
                "reason": f"三要素不满足: {missing}",
                "action": "标注「待数据支撑」,记入资料摘要,不新建命题",
            })
            continue

        # Step 2 · 匹配现有命题(MVP:简单字符串匹配)
        matched_claim = None
        for c in existing_claims:
            if c.get("domain") == obs.get("domain") and c.get("slug") == obs.get("slug"):
                matched_claim = c
                break

        # Step 3 · 置信度判定
        evidence_for = obs.get("evidence_for_count", 1)
        evidence_against = obs.get("evidence_against_count", 0)
        sample_size = obs.get("sample_size", 1)
        cross_validated = obs.get("cross_validated", False)
        has_roi = obs.get("has_roi_positive", False)

        # env_flag 活跃时暂缓升降(环4.1 + 附录 E 规则 7.1)
        if env_flag_active:
            new_claims.append({
                "statement": obs.get("statement"),
                "confidence": "暂缓(env_flag 活跃)",
                "reason": "环境外因活跃期,置信度变动暂缓(附录 E 规则 7.1)",
                "action": "等 env_flag 消除后重新评估",
            })
            continue

        confidence, reason = _assess_confidence(
            evidence_for, evidence_against, sample_size, cross_validated, has_roi
        )

        claim_entry = {
            "statement": obs.get("statement"),
            "domain": obs.get("domain", "unknown"),
            "confidence": confidence,
            "reason": reason,
            "evidence_for": evidence_for,
            "evidence_against": evidence_against,
            "sample_size": sample_size,
        }

        if matched_claim:
            old_conf = matched_claim.get("confidence", "存疑")
            if confidence != old_conf:
                claim_entry["升降"] = f"{old_conf} → {confidence}"
                upgraded_claims.append(claim_entry)
            else:
                claim_entry["升降"] = "无变化(证据增强)"
                new_claims.append(claim_entry)
        else:
            claim_entry["升降"] = "新建命题"
            new_claims.append(claim_entry)

        # 附录 E 规则 3.1:命题升「可信」自动触发执行桥
        if confidence == "可信" and (not matched_claim or matched_claim.get("confidence") == "存疑"):
            emit_events.append({
                "type": "命题升可信_自动",
                "payload": {
                    "statement": obs.get("statement"),
                    "domain": obs.get("domain"),
                    "confidence": "可信",
                    "action": "自动触发执行桥 → 策略简报 agent(附录 E 规则 3.1)",
                },
            })

    # 输出
    data = {
        "处理观察数": len(observations),
        "新建/更新命题": new_claims,
        "置信度升降": upgraded_claims,
        "三要素不满足(拒绝入库)": rejected_observations,
        "env_flag_active": env_flag_active,
        "规则来源": RULE_SOURCE,
        "语气提示": "ZJB排查 · 提问句式:这些命题的置信度判定是否合理?",
    }

    # 合约三
    roles = ["ZJB排查", "Claude"]
    role_check = validate_role(roles=roles, conclusion_type="命题变化")
    if not role_check.ok:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"合约三校验失败: {role_check.errors}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 合约二
    rule_check = validate_rule(rule_source=RULE_SOURCE)
    if not rule_check.ok:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"合约二校验失败: {rule_check.errors}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    data["_io_contract"] = {
        "target_role": roles,
        "rule_source": RULE_SOURCE,
    }

    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
        emit_events=emit_events,
    )
