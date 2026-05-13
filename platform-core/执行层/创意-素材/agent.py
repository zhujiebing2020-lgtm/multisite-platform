"""platform-core/执行层/创意-素材/agent.py
创意-素材 Agent · stub

职责(SVG L5):素材·脚本·生产触发
MVP dry-run:读阈值 + 内容包,mock 输出"按调性会生成什么"
§15.3 关键验证:内容包注入 AgentInput.content_pack 是否工作
真集成 P1:产出包流水线(脚本→分镜→视觉→旁白→合成)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402

name = "创意-素材"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    o = inp.overrides
    cp = inp.content_pack  # ← 内容包链路的关键

    required = ["creative_fatigue_ctr_drop_pct", "creative_fatigue_window_days"]
    missing = [k for k in required if o.get(k) is None]
    if missing:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason=f"创意-素材 缺关键阈值: {missing}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name,
            site_id=inp.site_id,
        )

    # 内容包是否注入(§15.3 验证点)
    if cp is None:
        content_status = "未注入内容包,会用平台默认中性话术(P1 实现)"
        sample_script = None
    else:
        tone = cp.get("tone", {})
        phrases = cp.get("brand_phrases", {})
        style = cp.get("style_hints", {})
        # mock 一段脚本片段,证明内容包被消费
        cta_list = phrases.get("cta", []) or []
        urgency_list = phrases.get("urgency", []) or []
        sample_script = {
            "镜头 1 (0-2s)": urgency_list[0] if urgency_list else "(无)",
            "镜头 2 (2-4s)": (phrases.get("value", []) or ["(无)"])[0],
            "镜头 3 (4-6s)": cta_list[0] if cta_list else "(无)",
            "节奏": style.get("script_pace"),
            "旁白情绪": style.get("voiceover_emotion"),
            "禁用词": cp.get("forbidden_phrases", []),
        }
        content_status = (
            f"内容包注入成功 tone={tone.get('primary')}/{tone.get('secondary')}"
        )

    data = {
        "summary": "dry-run 读阈值 + 内容包成功,未实际跑产出包流水线",
        "lookback_window": inp.time_window.describe(),
        "fatigue_rule": (
            f"CTR 连续 {o['creative_fatigue_window_days']} 天下降 ≥ "
            f"{o['creative_fatigue_ctr_drop_pct']}% → 触发 creative-refresh"
        ),
        "monthly_cost_cap_usd": o.get("creative_monthly_cost_cap_usd"),
        "content_pack_status": content_status,
        "sample_script_when_real": sample_script,
        "would_trigger_pipeline_when_real": [
            "script-脚本", "storyboard-分镜", "visual-视觉",
            "voiceover-旁白", "composite-合成",
        ],
        "would_publish_event": "creative_fatigue_detected",
        "subscribed_events": ["attribution_risk(收到 → 暂停生产)"],
    }
    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
    )
