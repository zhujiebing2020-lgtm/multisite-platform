"""platform-core/执行层/故事脚本/agent.py

故事脚本 agent · 故事 → 视频脚本(逐帧 + t2i + i2v prompt)

职责:
  · 接策略简报 + 文案 agent 输出 → 生成视频脚本
  · 每镜头含:shot(画面)/ t2i_prompt(文生图)/ i2v_prompt(图生视频)
  · 调性来自 content_pack(限时紧迫等)
  · 真实生成参考 crave-AI/data/video_briefs/scripts/*.json

输出:
  · target_role=[承接层](故事脚本归承接层 - 内容团队执行)
  · rule_source=ZJB 口头/会议(暂无规则文件,P1 沉淀)

MVP 局限:
  · 真实生成需要 LLM,本 stub 搭框架
  · 镜头数默认 4-6 个(参考 crave-AI 现有脚本)
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

name = "故事脚本"
RULE_SOURCE = "ZJB 口头/会议"  # 暂无规则文件,合法 fallback


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}
    brief = upstream.get("brief", {})
    copy_pack = upstream.get("copy_pack", {})
    content_pack = inp.content_pack or {}

    claim = brief.get("来源命题") or brief.get("statement", "")
    if not claim:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason="上游未传入命题 + 文案(需要策略简报和文案 agent 的输出)",
            duration_ms=int((time.time()-t0)*1000),
            agent_name=name, site_id=inp.site_id,
        )

    style_hints = content_pack.get("style_hints", {})
    visual_motif = style_hints.get("visual_motif", [])

    # 4 镜头默认结构(参考 crave-AI video-script 模板)
    script = {
        "duration_total_sec": 12,
        "镜头数": 4,
        "节奏": style_hints.get("script_pace", "medium"),
        "shots": [
            {
                "shot_id": 1,
                "duration_sec": 3,
                "shot_description": "(待生成)开场镜头 · 应映射文案 Hook A",
                "t2i_prompt": "(待生成)文生图 prompt",
                "i2v_prompt": "(待生成)图生视频 prompt",
                "voiceover": copy_pack.get("hooks", [{}])[0].get("draft", "(待文案)"),
            },
            {
                "shot_id": 2, "duration_sec": 3,
                "shot_description": "(待生成)冲突/转折镜头",
                "t2i_prompt": "(待生成)",
                "i2v_prompt": "(待生成)",
                "voiceover": "(待文案)",
            },
            {
                "shot_id": 3, "duration_sec": 3,
                "shot_description": "(待生成)产品/价值展示",
                "t2i_prompt": "(待生成)",
                "i2v_prompt": "(待生成)",
                "voiceover": "(待文案)",
            },
            {
                "shot_id": 4, "duration_sec": 3,
                "shot_description": "(待生成)CTA 收尾",
                "t2i_prompt": "(待生成)",
                "i2v_prompt": "(待生成)",
                "voiceover": copy_pack.get("cta", "Shop Now"),
            },
        ],
        "visual_motif_注入": visual_motif if visual_motif else ["(无 content_pack 引用)"],
    }

    data = {
        "来源命题": claim[:60],
        "脚本": script,
        "memory 沉淀": [
            "镜头不一致问题(memory project_video_consistency_issue):4 分镜角色/场景不一致不可用",
            "解决方向:参考图锚点 / 单镜头 10s / character reference(2026-05-12 与投放组讨论)",
        ],
        "生成说明": [
            "本 stub 只搭框架,真实 t2i/i2v prompt 需 LLM 调用 + 参考图锚点",
            "下游:素材审核 agent 检查合规后才能进入生产",
        ],
        "语气提示": "承接层 · 陈述句+可执行(不加 next_action)",
    }

    roles = ["承接层"]
    rc = validate_role(roles=roles, conclusion_type="suggestion")
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
        agent_name=name, site_id=inp.site_id,
    )
