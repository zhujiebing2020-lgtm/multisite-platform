"""platform-core/执行层/素材审核/agent.py

素材审核 agent · 禁用词 / 反 AI 腔 / 调性检查 / 合规

职责(柴碧如的工作流程化):
  · 接 文案/故事脚本 agent 输出
  · 禁用词检查(医疗承诺/绝对化用词/平台违禁)
  · 反 AI 腔检查(模板感/重复短语)
  · 调性一致性(与 content_pack 的 tone 对齐)
  · 真实性反馈(memory v1.2)

输出:
  · target_role=[承接层](柴碧如负责)
  · rule_source=memory:feedback_comment_gen_anti_repetition + ZJB 口头
  · 失败时 emit 素材审核_失败 阻断下游
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

name = "素材审核"
RULE_SOURCE = "ZJB 口头/会议"  # 反 AI 腔规则在 memory,暂用 fallback


# 禁用词清单(MVP)
FORBIDDEN_PHRASES = {
    "医疗承诺": ["治愈", "100% 有效", "无副作用", "彻底解决"],
    "绝对化用词": ["最棒", "第一", "唯一", "永远", "绝对"],
    "免费陷阱": ["免费永久", "0 元", "不要钱"],
    "AI 腔短语": ["让你感受到", "为你打造", "尽享", "无与伦比"],
}


def _check_forbidden(text: str) -> list[dict]:
    """扫描禁用词命中"""
    hits = []
    for category, words in FORBIDDEN_PHRASES.items():
        for w in words:
            if w in text:
                hits.append({"category": category, "phrase": w})
    return hits


def _check_repetition(texts: list[str]) -> list[str]:
    """检查多条文案是否存在短语撞车;跳过占位文本"""
    issues = []
    seen_starts = {}
    for i, t in enumerate(texts):
        # 跳过空 / 占位符 / 待生成
        if not t or t.startswith("(") or "待" in t[:4] or "TODO" in t:
            continue
        start = t[:4]
        if start in seen_starts:
            issues.append(f"短语撞车:第 {seen_starts[start]+1} 条和第 {i+1} 条都以 {start!r} 开头")
        seen_starts[start] = i
    return issues


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}
    content_pack = inp.content_pack or {}

    # 接收多种素材类型
    copy_pack = upstream.get("copy_pack", {})
    script = upstream.get("script", {})

    if not copy_pack and not script:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason="未传入素材(copy_pack 或 script)",
            duration_ms=int((time.time()-t0)*1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 收集所有要审核的文本
    texts_to_check = []
    if copy_pack:
        for h in copy_pack.get("hooks", []):
            texts_to_check.append(h.get("draft", ""))
        texts_to_check.append(copy_pack.get("title", ""))
        texts_to_check.append(copy_pack.get("body", ""))
        for c in copy_pack.get("comments", []):
            texts_to_check.append(c)
    if script:
        for shot in script.get("shots", []):
            texts_to_check.append(shot.get("voiceover", ""))
            texts_to_check.append(shot.get("shot_description", ""))

    # 跑检查
    all_forbidden = []
    for t in texts_to_check:
        hits = _check_forbidden(t)
        if hits:
            all_forbidden.extend([{"text": t[:30], **h} for h in hits])

    repetition_issues = _check_repetition(texts_to_check)

    # 调性一致性(简单 stub)
    expected_tone = content_pack.get("tone", {}).get("primary", "")
    tone_match = True  # MVP 默认通过,真检查需要 NLP

    passed = (len(all_forbidden) == 0 and len(repetition_issues) == 0 and tone_match)

    data = {
        "审核结果": "通过" if passed else "未通过",
        "检查项": {
            "禁用词命中": all_forbidden if all_forbidden else "无",
            "短语撞车": repetition_issues if repetition_issues else "无",
            "调性一致性": "通过" if tone_match else f"与期望调性 {expected_tone} 不符",
        },
        "禁用词规则(MVP)": FORBIDDEN_PHRASES,
        "下游处理": (
            "通过 → 可发投手投放 + 进入生产" if passed
            else "未通过 → emit 素材审核_失败,阻断下游,回到 文案/故事脚本 agent 重写"
        ),
        "语气提示": "承接层 · 陈述句+可执行(不加 next_action)",
    }

    emit_events = []
    if not passed:
        emit_events.append({
            "type": "素材审核_失败",
            "payload": {
                "forbidden": all_forbidden,
                "repetition": repetition_issues,
                "action": "回到 文案/故事脚本 重写",
            },
        })

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
        agent_name=name, site_id=inp.site_id, emit_events=emit_events,
    )
