"""platform-core/执行层/数据-归因/agent.py
数据-归因 Agent · stub

职责(SVG L5):归因·异常检测·跨 agent 信号发布
MVP dry-run:读阈值 mock 归因风险/异常信号
§15.4 跨 agent 影响:本 agent 发布 attribution_risk → 流量-投放 订阅 → 降权建议
真集成 P1:AdClaw / Site Analytics / 归因模型
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402

name = "数据-归因"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    o = inp.overrides

    required = ["utm_coverage_min", "hvu_drop_pct_alert", "lookback_days"]
    missing = [k for k in required if o.get(k) is None]
    if missing:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason=f"数据-归因 缺关键阈值: {missing}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name,
            site_id=inp.site_id,
        )

    data = {
        "summary": "dry-run 读阈值成功,未实际查询 AdClaw / 站内分析",
        "lookback_days": o["lookback_days"],
        "attribution_check": {
            "rule": f"UTM 覆盖率低于 {o['utm_coverage_min']*100:.0f}% → 标 attribution_risk",
            "min_sessions": o.get("min_sessions_for_confidence"),
            "would_publish_event": "attribution_risk(→ 流量-投放 收到降权建议)",
        },
        "anomaly_detection": {
            "hvu_drop_alert_pct": o["hvu_drop_pct_alert"],
            "cost_spike_alert_pct": o.get("cost_spike_pct_alert"),
            "bounce_alert": o.get("bounce_rate_alert"),
            "would_publish_event": "hvu_drop_detected / data_quality_low",
        },
        "would_query_when_real": ["adclaw_mcp", "ga4", "meta_attribution_api"],
    }

    # MVP mock:本 stub 假设检测到 UTM 覆盖偏低 → 发 attribution_risk
    # 真实场景下,这里应该根据查询结果决定是否 emit
    mock_utm_coverage = 0.72   # mock 值,真实场景从 AdClaw 查
    emit_events = []
    if mock_utm_coverage < o["utm_coverage_min"]:
        emit_events.append({
            "type": "attribution_risk",
            "payload": {
                "utm_coverage": mock_utm_coverage,
                "threshold": o["utm_coverage_min"],
                "reason": f"UTM 覆盖率 {mock_utm_coverage:.0%} < 阈值 {o['utm_coverage_min']:.0%}",
                "suggested_action": "降权或重审最近 lookback 内的归因",
                "lookback_days": o["lookback_days"],
            },
        })
        data["emitted"] = f"已声明发布 attribution_risk(覆盖率 {mock_utm_coverage:.0%})"

    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
        emit_events=emit_events,
    )
