"""platform-core/执行层/文案/agent.py

文案 agent · Hook / 标题 / 正文 / CTA / 评论区生成

职责:
  · 接策略简报 agent 输出 → 生成具体文案
  · 评论区生成(memory feedback_comment_gen_anti_repetition v1.2)
    - 反短语撞车 / 反特征罗列 / 反 AI 腔
    - 情绪锚点 + 节奏散化 + 真实性反馈
  · 投手内容调性(限时紧迫/划算等)从上游 content_pack 注入

输出:
  · target_role=[投手, 承接层](文案给投手投放 + 承接层视觉对齐)
  · rule_source=platform-core/规则/strategy_brief.json + memory:feedback_comment_gen_anti_repetition

MVP 局限:
  · 真实生成需要调 Claude/LLM,本 stub 只搭框架,产出"待生成"占位
  · 反重复/反 AI 腔规则在 stub 内列清单,真实生成时按 prompt 注入
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

name = "文案"
RULE_SOURCE = "platform-core/规则/strategy_brief.json"

# 反重复/反 AI 腔规则(memory v1.2 沉淀)
COPY_QUALITY_RULES = [
    "禁短语撞车:Hook A/B/C 三条不许用同一关键短语",
    "反特征罗列:不堆砌'美丽/性感/激情'等形容词清单",
    "情绪锚点:每条文案必须有一个具体情绪触发点(场景/冲突/欲望)",
    "节奏散化:句长不均,长短句交错,避免 AI 模板感",
    "真实性反馈:用人称代词、自然口语、不完美收尾",
]


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}
    brief = upstream.get("brief") or upstream.get("event_payload", {})
    content_pack = inp.content_pack or {}

    if not brief.get("来源命题") and not brief.get("statement"):
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason="上游未传入策略简报 brief(需要 策略简报 agent 的输出)",
            duration_ms=int((time.time()-t0)*1000),
            agent_name=name, site_id=inp.site_id,
        )

    claim_statement = brief.get("来源命题") or brief.get("statement", "")
    tone = content_pack.get("tone", {}).get("primary", "中性")
    brand_phrases = content_pack.get("brand_phrases", {})

    # MVP:生成框架,真实文案待 LLM 接入
    copy_pack = {
        "hooks": [
            {"slot": "A", "draft": "(待生成)开场 3 秒文案", "情绪锚点": "(待填)"},
            {"slot": "B", "draft": "(待生成)备选角度", "情绪锚点": "(待填)"},
            {"slot": "C", "draft": "(待生成)反向切入", "情绪锚点": "(待填)"},
        ],
        "title": "(待生成,≤40 字)",
        "body": "(待生成,≤150 字)",
        "cta": brand_phrases.get("cta", ["Shop Now"])[0] if brand_phrases else "Shop Now",
        "comments": [
            "(待生成)第一条评论 · 必须有具体情绪/场景",
            "(待生成)第二条 · 与第一条不同情绪锚点",
            "(待生成)第三条 · 节奏散化,不同句长",
        ],
    }

    data = {
        "来源命题": claim_statement[:60],
        "调性": tone,
        "文案产物": copy_pack,
        "文案质量规则(memory v1.2)": COPY_QUALITY_RULES,
        "生成说明": [
            "本 agent MVP 阶段只搭框架,真实文案需 LLM 调用(P1)",
            "评论区生成必须遵守 memory feedback_comment_gen_anti_repetition v1.2",
            "下游:素材审核 agent 检查禁用词/调性后才能发投手",
        ],
        "语气提示": "投手+承接层 · 陈述句+可执行(不加 next_action)",
    }

    roles = ["投手", "承接层"]
    rc = validate_role(roles=roles, conclusion_type="suggestion")
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
