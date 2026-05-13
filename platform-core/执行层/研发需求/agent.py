"""platform-core/执行层/研发需求/agent.py

研发需求 agent · 承接端 UX 缺口 → P0/P1/P2 技术需求

职责(CLAUDE.md 环4.2 需求检查三问):
  · 接知识沉淀 / 承接端分析 agent 的输出
  · 三问:是否产生新需求 / 是否提升存量优先级 / 是否取消调整存量
  · 优先级判定 tech_priority.json:P0 阻塞 / P1 影响体验 / P2 锦上添花

输出:
  · target_role=[技术, ZJB排查]
  · rule_source=platform-core/规则/tech_priority.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PLATFORM_CORE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM_CORE / "中间件"))
sys.path.insert(0, str(PLATFORM_CORE / "执行层"))

from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402
from target_role校验 import validate as validate_role  # noqa: E402
from 规则指针校验 import validate as validate_rule  # noqa: E402

name = "研发需求"
RULES_DIR = PLATFORM_CORE / "规则"
RULE_SOURCE = "platform-core/规则/tech_priority.json"


def _assess_priority(gap: dict) -> tuple[str, str]:
    """根据 gap 性质判定 P0/P1/P2"""
    impact = gap.get("impact", "")
    blocks_conversion = gap.get("blocks_conversion", False)
    affected_pct = gap.get("affected_user_pct", 0)
    blocks_other = gap.get("blocks_other_requirements", False)

    if blocks_conversion or impact == "高" or blocks_other:
        return "P0", "阻塞转化 / 影响核心漏斗 / 阻塞其他需求"
    if affected_pct >= 0.3 or impact == "中":
        return "P1", "影响体验但不阻塞"
    return "P2", "锦上添花"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}

    try:
        rule = json.loads((RULES_DIR / "tech_priority.json").read_text(encoding="utf-8"))
    except Exception as e:
        return AgentResult(status=AgentStatus.EXTERNAL_FAILURE, gap_reason=f"规则读取失败: {e}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    ux_gaps = upstream.get("ux_gaps", [])
    existing_reqs = upstream.get("existing_requirements", [])
    claim_changes = upstream.get("claim_changes", [])

    new_requirements = []
    priority_changes = []
    cancellation_recommendations = []

    # 三问 1:新需求
    for gap in ux_gaps:
        priority, reason = _assess_priority(gap)
        new_requirements.append({
            "需求": gap.get("description", "?"),
            "优先级": priority,
            "理由": reason,
            "负责人": gap.get("owner", "郭刚"),
            "影响用户占比": gap.get("affected_user_pct"),
            "关联命题": gap.get("related_claim"),
        })

    # 三问 2:存量优先级调整(命题升级 → 关联需求升 P)
    for change in claim_changes:
        if change.get("升降", "").startswith("可信"):
            related_req = change.get("related_requirement")
            if related_req:
                priority_changes.append({
                    "需求": related_req,
                    "调整": "P1 → P0(命题升可信,建议升级优先级)",
                    "理由": f"关联命题{change.get('statement', '?')[:40]}",
                })

    # 三问 3:取消/调整存量
    for req in existing_reqs:
        # 关联命题被证伪 → 建议取消
        if req.get("related_claim_confidence") == "证伪":
            cancellation_recommendations.append({
                "需求": req.get("description", "?"),
                "建议": "取消(关联命题已证伪)",
                "理由": "命题被推翻,需求失去依据",
            })

    data = {
        "三问结果": {
            "新需求": new_requirements if new_requirements else "无",
            "优先级调整": priority_changes if priority_changes else "无",
            "需求重评": cancellation_recommendations if cancellation_recommendations else "无",
        },
        "优先级规则": "P0=阻塞转化 / P1=影响体验 / P2=锦上添花(tech_priority.json)",
        "下一步": "ZJB 拍板后,新需求/调整 写入 vault/3_执行层/24_任务与跟进/个人工作台.md",
        "语气提示": "技术+ZJB排查 · 技术陈述句 + ZJB 提问句",
    }

    roles = ["技术", "ZJB排查"]
    rc = validate_role(roles=roles, conclusion_type="tech_need")
    if not rc.ok:
        return AgentResult(status=AgentStatus.FAILED, gap_reason=f"合约三:{rc.errors}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    rs_check = validate_rule(rule_source=RULE_SOURCE, repo_root=PLATFORM_CORE.parent)
    if not rs_check.ok:
        return AgentResult(status=AgentStatus.FAILED, gap_reason=f"合约二:{rs_check.errors}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    data["_io_contract"] = {"target_role": roles, "rule_source": RULE_SOURCE}

    return AgentResult(
        status=AgentStatus.SUCCESS, data=data, cost=0.0,
        duration_ms=int((time.time()-t0)*1000),
        agent_name=name, site_id=inp.site_id,
    )
