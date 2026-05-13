"""platform-core/执行层/搬运/agent.py

搬运 agent · 子站数据 → 总站(自动)/ 总站 → 子站(人工决定)

职责(ZJB 5/13 拍板的监管层语义):
  · 子站数据回灌总站:自动,定时(默认每天 14:00 跟 daily_close)
  · 总站数据回流子站:人工 ZJB 拍板,Claude 不自动
  · 跨站规则同步:平台规则升级时通知子站
  · 卖站打包:tools/customer-export 是 P1 工程项

输出:
  · target_role=[ZJB排查, Claude](搬运决策归 ZJB 排查)
  · rule_source=ZJB 口头/会议(待沉淀规则文件)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PLATFORM_CORE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM_CORE / "中间件"))
sys.path.insert(0, str(PLATFORM_CORE / "执行层"))

from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402
from target_role校验 import validate as validate_role  # noqa: E402
from 规则指针校验 import validate as validate_rule  # noqa: E402

name = "搬运"
RULE_SOURCE = "ZJB 口头/会议"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}
    direction = upstream.get("direction", "子站→总站")  # 默认子站回灌
    payload = upstream.get("payload", {})
    site_id = inp.site_id

    if direction == "子站→总站":
        # 自动:把子站本期数据快照推到总站
        action = {
            "类型": "自动回灌",
            "from": site_id,
            "to": "总站 platform-core/数据底盘/",
            "payload_keys": list(payload.keys()),
            "说明": "子站数据自动回灌总站,无需 ZJB 确认",
            "频率": "默认跟 daily_close.py 每天 14:00",
        }
        emit = [{
            "type": "数据回灌_完成",
            "payload": {"site_id": site_id, "direction": direction, "keys": list(payload.keys())},
        }]
    elif direction == "总站→子站":
        # 人工:必须 ZJB 拍板
        if not payload.get("zjb_approval"):
            return AgentResult(
                status=AgentStatus.FAILED,
                gap_reason="总站→子站 搬运必须 ZJB 拍板(payload.zjb_approval=True),当前未授权",
                duration_ms=int((time.time()-t0)*1000),
                agent_name=name, site_id=inp.site_id,
            )
        action = {
            "类型": "人工搬运",
            "from": "总站",
            "to": site_id,
            "授权": payload.get("zjb_approval"),
            "说明": "总站规则/数据同步到子站,ZJB 已拍板",
        }
        emit = []
    else:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"未知 direction={direction!r},应为 子站→总站 或 总站→子站",
            duration_ms=int((time.time()-t0)*1000),
            agent_name=name, site_id=inp.site_id,
        )

    data = {
        "搬运动作": action,
        "ZJB 5/13 拍板": "子站回灌自动,总站下发人工",
        "语气提示": "ZJB排查 · 提问句式",
    }

    roles = ["ZJB排查", "Claude"]
    rc = validate_role(roles=roles, conclusion_type="data_insight")
    if not rc.ok:
        return AgentResult(status=AgentStatus.FAILED, gap_reason=f"合约三:{rc.errors}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    rs_check = validate_rule(rule_source=RULE_SOURCE)
    if not rs_check.ok:
        return AgentResult(status=AgentStatus.FAILED, gap_reason=f"合约二:{rs_check.errors}",
                          duration_ms=int((time.time()-t0)*1000), agent_name=name, site_id=inp.site_id)

    data["_io_contract"] = {"target_role": roles, "rule_source": RULE_SOURCE}

    return AgentResult(
        status=AgentStatus.SUCCESS, data=data, cost=0.0,
        duration_ms=int((time.time()-t0)*1000),
        agent_name=name, site_id=inp.site_id, emit_events=emit,
    )
