"""platform-core/执行层/技术-埋点/agent.py
技术-埋点 Agent · stub

职责(SVG L5):埋点·速度·API 健康·上线前关卡(acceptance_check)
MVP dry-run:只读阈值 mock 输出,不调真 PageSpeed/埋点验证服务
真集成 P1:Google PageSpeed Insights API + 埋点回放工具
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402

name = "技术-埋点"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    o = inp.overrides

    # 必读阈值
    required = ["lcp_ms_max", "lcp_ms_alert", "http_status_ok", "tracking_loss_ratio_alert"]
    missing = [k for k in required if o.get(k) is None]
    if missing:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason=f"技术-埋点 缺关键阈值: {missing}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name,
            site_id=inp.site_id,
        )

    data = {
        "summary": "dry-run 读阈值成功,未实际调 PageSpeed/埋点回放",
        "lookback_window": inp.time_window.describe(),
        "launch_gate": {
            "rules": [
                f"页面 HTTP 状态码 = {o['http_status_ok']}",
                f"LCP < {o['lcp_ms_max']}ms",
                f"UTM 必填 = {o.get('utm_required')}",
                f"年龄验证弹窗 = {o.get('age_gate_required')}",
            ],
            "would_check": "上线前每个站需通过 5 项 acceptance_check(crave-AI flows.json)",
        },
        "runtime_health": {
            "lcp_alert_threshold_ms": o["lcp_ms_alert"],
            "tracking_loss_alert_ratio": o["tracking_loss_ratio_alert"],
            "api_error_alert_ratio": o.get("api_error_rate_alert"),
        },
        "would_publish_events_when_real": [
            "tracking_loss_detected",
            "landing_page_slow",
            "age_gate_broken",
        ],
        "would_call_apis_when_real": ["google_pagespeed_api", "埋点回放工具"],
    }
    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
    )
