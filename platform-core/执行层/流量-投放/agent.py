"""platform-core/执行层/流量-投放/agent.py
流量-投放 Agent · 第一个 stub

职责(SVG L5):流量·渠道·投放·扩量·止损
当前 MVP:dry-run mock,只读 ctx 输出"我看到了什么阈值",不真调 Meta/Google API
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# 让 import _base 工作:执行层根目录入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402


name = "流量-投放"


def run(inp: AgentInput) -> AgentResult:
    """
    MVP dry-run:从 overrides 读关键阈值,mock 一个"健康检查"输出。
    真实接 Meta API 是 P1。
    """
    t0 = time.time()

    # 必读阈值(从 LoadedConfig.resolved_thresholds 注入)
    cphq_green = inp.overrides.get("cphq_green_max")
    pause_days = inp.overrides.get("pause_on_hvu_zero_days")
    scale_min_spend = inp.overrides.get("scale_up_min_spend")

    if cphq_green is None or pause_days is None:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason=(
                f"流量-投放 缺关键阈值: cphq_green_max={cphq_green}, "
                f"pause_on_hvu_zero_days={pause_days}"
            ),
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name,
            site_id=inp.site_id,
        )

    # mock 输出
    data = {
        "summary": "dry-run 读阈值成功,未实际调 Meta/Google API",
        "active_thresholds": {
            "cphq_green_max": cphq_green,
            "pause_on_hvu_zero_days": pause_days,
            "scale_up_min_spend": scale_min_spend,
        },
        "decisions_mock": [
            f"如 CPHQ > {cphq_green} 持续 → 进入黄灯",
            f"如 HVU 连续 {pause_days} 天为 0 → 暂停",
            f"如累计花费 ≥ {scale_min_spend} 且达放量条件 → 加预算",
        ],
        "would_call_apis_when_real": ["meta_marketing_api", "google_ads_api"],
    }

    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
    )
