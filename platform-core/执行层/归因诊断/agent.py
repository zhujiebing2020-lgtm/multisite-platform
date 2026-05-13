"""platform-core/执行层/归因诊断/agent.py

归因诊断 agent · env_flag 5 种外因排查

职责(CLAUDE.md 环4.1 归因前置检查):
  ROI/CPA 异动时,先排外因再判命题。
  5 种外部信号任一成立 → 标 env_flag → 暂缓置信度变动

5 种外因(attribution_pre_check.json):
  1. 平台算法/政策调整(FB/TikTok 官方公告)
  2. 账号受限或封控(后台状态异常,展示量骤降但 CTR 不变)
  3. 节假日/大促流量异常(日期在已知波动窗口)
  4. 网站宕机或技术故障(session 骤降 > 50%)
  5. 竞品集中投放(CPHQ 下降但站内行为正常)

输出:
  · target_role=[ZJB排查, Claude](归因是 ZJB 排查域)
  · rule_source=platform-core/规则/attribution_pre_check.json
  · 如果检测到外因 → emit_events=[{type: env_flag_detected}]
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

name = "归因诊断"
RULES_DIR = PLATFORM_CORE / "规则"
RULE_SOURCE = "platform-core/规则/attribution_pre_check.json"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}

    # 读真规则
    try:
        rule = json.loads((RULES_DIR / "attribution_pre_check.json").read_text(encoding="utf-8"))
    except Exception as e:
        return AgentResult(
            status=AgentStatus.EXTERNAL_FAILURE,
            gap_reason=f"规则读取失败: {e}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 从 upstream 获取异常信号(由数据分析 agent 或事件层传入)
    anomaly_signals = upstream.get("anomaly_signals", [])
    data_date = upstream.get("data_date", "unknown")

    # 5 种外因逐条检查
    env_flags_detected = []
    checks = rule.get("checks", rule.get("external_signals", []))

    # MVP:基于 upstream 传入的信号做匹配
    # 真实场景 P1:接 AdClaw session 数据 / FB 后台状态 / 日历窗口
    for signal in anomaly_signals:
        signal_type = signal.get("type", "")
        if signal_type in ("平台算法调整", "platform_policy"):
            env_flags_detected.append({
                "type": "平台算法/政策调整",
                "evidence": signal.get("evidence", ""),
                "action": "暂缓所有命题置信度变动,等公告确认影响范围",
            })
        elif signal_type in ("账号受限", "account_restricted"):
            env_flags_detected.append({
                "type": "账号受限或封控",
                "evidence": signal.get("evidence", ""),
                "action": "检查后台状态,确认是限流还是封控",
            })
        elif signal_type in ("节假日", "holiday_traffic"):
            env_flags_detected.append({
                "type": "节假日/大促流量异常",
                "evidence": signal.get("evidence", ""),
                "action": "标记波动窗口,窗口内数据不参与置信度升降",
            })
        elif signal_type in ("网站宕机", "site_down"):
            env_flags_detected.append({
                "type": "网站宕机或技术故障",
                "evidence": signal.get("evidence", ""),
                "action": "确认 session 骤降幅度,>50% 标 env_flag",
            })
        elif signal_type in ("竞品集中投放", "competitor_surge"):
            env_flags_detected.append({
                "type": "竞品集中投放",
                "evidence": signal.get("evidence", ""),
                "action": "CPHQ 下降但站内行为正常 → 外因,不降命题",
            })

    # 也检查数据分析传来的异常组(CPHQ 突变 / spend=0 但有 HVU)
    anomaly_groups = upstream.get("anomaly_groups", [])
    data_anomalies = []
    for g in anomaly_groups:
        if g.get("spend") == 0 and g.get("hvu", 0) > 0:
            data_anomalies.append({
                "group": g.get("group", "?"),
                "issue": f"spend=0 但 HVU={g['hvu']}(归因延迟或数据错误)",
                "action": "需 ZJB 确认:是归因延迟还是数据源错误?",
            })
        elif g.get("cphq") and float(g.get("cphq", 0)) > 10:
            data_anomalies.append({
                "group": g.get("group", "?"),
                "issue": f"CPHQ=${g['cphq']}(极端值)",
                "action": "是否有外因?先排查再判止损",
            })

    has_env_flag = len(env_flags_detected) > 0

    # 输出
    data = {
        "诊断日期": data_date,
        "规则来源": RULE_SOURCE,
        "规则版本": rule.get("_meta", {}).get("version", "?"),
        "外因检查结果": {
            "检测到外因": has_env_flag,
            "外因数量": len(env_flags_detected),
            "详情": env_flags_detected if env_flags_detected else "未检测到 5 种外因",
        },
        "数据异常组": data_anomalies if data_anomalies else "无数据异常",
        "结论": (
            "检测到外因 → 建议标 env_flag,暂缓相关命题置信度变动"
            if has_env_flag
            else "未检测到外因 → 可正常进行命题置信度升降"
        ),
        "语气提示": "ZJB排查 · 必须提问句式:这些异常是否确认为外因?",
    }

    # 合约三 target_role
    roles = ["ZJB排查", "Claude"]
    role_check = validate_role(roles=roles, conclusion_type="data_insight")
    if not role_check.ok:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"合约三校验失败: {role_check.errors}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 合约二 rule_source
    rule_check = validate_rule(rule_source=RULE_SOURCE, repo_root=PLATFORM_CORE.parent)
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

    # emit_events:如果检测到外因,发 env_flag_detected 事件
    emit_events = []
    if has_env_flag:
        emit_events.append({
            "type": "env_flag_detected",
            "payload": {
                "flags": env_flags_detected,
                "data_date": data_date,
                "action": "暂缓命题置信度变动",
            },
        })

    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
        emit_events=emit_events,
    )
