"""platform-core/执行层/意志继承/agent.py

意志继承 agent · auto_strategy_rules.json 编码 ZJB 业务判断为自动规则

职责(memory feedback_will_inheritance_principle):
  · 投手不可控,排查题 = 自动规则触发条件
  · 投手拒绝建议 ≠ 系统停,30 天后回看
  · S 类杠杆归因三拆(组17 18 Sensual 样板)
  · B 类零 HVU 诊断(组54 樱花样板)
  · 30 天数据回看(组1 Library 拒绝建议样板)

输出:
  · target_role=[ZJB排查, Claude](自动规则的执行属于 Claude 自跑,结论待 ZJB 审)
  · rule_source=platform-core/规则/auto_strategy_rules.json
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

name = "意志继承"
RULES_DIR = PLATFORM_CORE / "规则"
RULE_SOURCE = "platform-core/规则/auto_strategy_rules.json"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}

    try:
        rules = json.loads((RULES_DIR / "auto_strategy_rules.json").read_text(encoding="utf-8"))
    except Exception as e:
        return AgentResult(
            status=AgentStatus.EXTERNAL_FAILURE,
            gap_reason=f"规则读取失败: {e}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 从上游接收"分层数据"(SABRO)
    tiered_groups = upstream.get("tiered_groups", [])
    triggered_actions = []
    skipped_with_reason = []

    for g in tiered_groups:
        tier = g.get("tier", "")
        gid = g.get("group", "?")
        owner = g.get("advertiser", "?")

        # ── S 类杠杆三拆 ──
        if tier == "S":
            rule = rules.get("S_class_scaling_test", {})
            tc = rule.get("trigger_conditions", {})
            green_days = g.get("consecutive_green_days", 0)
            total_hvu = g.get("total_hvu", 0)

            # 触发条件校验
            condition_met = (
                green_days >= 14 and
                total_hvu >= 100
            )
            skeptic_active = g.get("env_flag_active", False) or g.get("cphq_over_2", False)

            if condition_met and not skeptic_active:
                triggered_actions.append({
                    "rule": "S_class_scaling_test",
                    "group": gid,
                    "owner": owner,
                    "action": "杠杆归因三拆 A/B",
                    "steps": [
                        "同素材×同定向×换落地页(3 天≥$30)",
                        "同素材×同落地页×换定向(3 天≥$30)",
                        "同定向×同落地页×换素材(3 天≥$30)",
                    ],
                    "rule_source": "auto_strategy_rules.json#S_class_scaling_test",
                })
            elif skeptic_active:
                skipped_with_reason.append({
                    "group": gid, "tier": "S",
                    "reason": "skeptic_conditions 活跃(env_flag 或 CPHQ>$2),暂停 auto_action",
                })

        # ── B 类零 HVU 诊断 ──
        elif tier == "B":
            rule = rules.get("B_class_zero_hvu_diagnosis", {})
            zero_hvu_days = g.get("consecutive_zero_hvu_days", 0)
            total_spend = g.get("total_spend", 0)

            if zero_hvu_days >= 7 and total_spend >= 30:
                triggered_actions.append({
                    "rule": "B_class_zero_hvu_diagnosis",
                    "group": gid,
                    "owner": owner,
                    "action": "立即暂停 + 标 frozen + 根因定位三问",
                    "rule_source": "auto_strategy_rules.json#B_class_zero_hvu_diagnosis",
                    "note": "标 frozen 不是 paused,保留复投评估资格(意志继承样板:组1 Library)",
                })

    # 30 天回看(组1 样板)— 投手拒绝建议的追踪
    rejected_suggestions = upstream.get("rejected_suggestions", [])
    review_due = []
    for r in rejected_suggestions:
        days_since = r.get("days_since_rejection", 0)
        if days_since >= 30:
            review_due.append({
                "rule": "30 天数据回看",
                "rejection_date": r.get("rejection_date"),
                "投手": r.get("pitcher"),
                "原建议": r.get("original_suggestion"),
                "action": "自动拉投手其它新组 CPHQ 对比 → 如不成立则计入 ZJB 建议被证明对 N/3",
                "rule_source": "auto_strategy_rules.json#investor_rejection_tracking",
            })

    data = {
        "处理分层组数": len(tiered_groups),
        "触发的自动 action": triggered_actions,
        "跳过(skeptic 活跃)": skipped_with_reason,
        "30 天回看到期": review_due,
        "意志继承原则": "投手不可控,规则自动跑;投手拒绝 ≠ 停,30 天后看谁对",
        "语气提示": "ZJB排查 · 提问句式:这些自动 action 是否需要 ZJB 加 skeptic 条件?",
    }

    roles = ["ZJB排查", "Claude"]
    rc = validate_role(roles=roles, conclusion_type="data_insight")
    if not rc.ok:
        return AgentResult(status=AgentStatus.FAILED, gap_reason=f"合约三:{rc.errors}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    rs_check = validate_rule(rule_source=RULE_SOURCE, repo_root=PLATFORM_CORE.parent)
    if not rs_check.ok:
        return AgentResult(status=AgentStatus.FAILED, gap_reason=f"合约二:{rs_check.errors}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    data["_io_contract"] = {"target_role": roles, "rule_source": RULE_SOURCE}

    # emit 触发的 action 给下游(策略简报 / 交接消息)
    emit_events = []
    for action in triggered_actions:
        emit_events.append({
            "type": "意志继承_action_triggered",
            "payload": action,
        })

    return AgentResult(
        status=AgentStatus.SUCCESS, data=data, cost=0.0,
        duration_ms=int((time.time()-t0)*1000),
        agent_name=name, site_id=inp.site_id, emit_events=emit_events,
    )
