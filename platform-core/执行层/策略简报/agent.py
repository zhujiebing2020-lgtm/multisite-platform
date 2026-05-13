"""platform-core/执行层/策略简报/agent.py

策略简报 agent · 命题(可信级)→ 投放策略

职责(CLAUDE.md 环3.2 + 环3.4):
  · 命题升「可信」自动触发(附录 E 规则 3.1,不等 ZJB 二次确认)
  · 输出策略简报:Hook 3 条 + 视觉方向 + 广告正文 + 标题 + CTA + KPI 目标
  · 输出飞书/微信交接消息(ZJB 确认后粘贴给投手)
  · 看板建议行追加

触发方式:
  · 知识沉淀 agent emit "命题升可信_自动" → 本 agent 接单
  · ZJB 主动指令

输出:
  · target_role=[投手](策略简报给投手执行)
  · rule_source=platform-core/规则/strategy_brief.json
  · 语气:陈述句+可执行判断(合约三 L126)

关键约束:
  · KPI 目标由命题本身推导,不设前置默认值(strategy_brief.json)
  · 策略简报在对话中输出,不写文件(环3.5 执行规则)
  · 广告上线后由 AI 创建广告组档案(环3.5 规则 5.1)
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
from target_role校验 import validate as validate_role, DOMAIN_TO_DEFAULT_ROLES  # noqa: E402
from 规则指针校验 import validate as validate_rule  # noqa: E402

name = "策略简报"
RULES_DIR = PLATFORM_CORE / "规则"
RULE_SOURCE = "platform-core/规则/strategy_brief.json"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}

    # 读规则
    try:
        rule = json.loads((RULES_DIR / "strategy_brief.json").read_text(encoding="utf-8"))
    except Exception as e:
        return AgentResult(
            status=AgentStatus.EXTERNAL_FAILURE,
            gap_reason=f"规则读取失败: {e}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 从上游获取命题信息(知识沉淀 emit 的 payload)
    claim = upstream.get("claim") or upstream.get("event_payload", {})
    statement = claim.get("statement", "")
    domain = claim.get("domain", "fb-ops")
    confidence = claim.get("confidence", "")

    if not statement:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason="上游未传入命题 statement(需要知识沉淀 agent 的 emit payload)",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    if confidence not in ("可信", "确认"):
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"命题置信度={confidence!r},未达「可信」门槛,不触发策略简报(环3 核心规则)",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 读 group_master 找推荐投手
    try:
        gm = json.loads((RULES_DIR / "group_master.json").read_text(encoding="utf-8"))
    except Exception:
        gm = {"groups": {}}

    # 推导推荐投手(从命题关联的组找 owner)
    related_group = claim.get("related_group")
    recommended_pitcher = "待定"
    landing_type = "待定"
    if related_group and related_group in gm.get("groups", {}):
        g = gm["groups"][related_group]
        recommended_pitcher = g.get("owner", "待定")
        landing_type = g.get("landing_type", "待定")

    # 生成策略简报(环3.2 格式)
    brief = {
        "来源命题": statement,
        "置信度": confidence,
        "投放逻辑": f"命题「{statement[:30]}...」已达{confidence},数据支持此方向",
        "推荐投手": recommended_pitcher,
        "落地页类型": landing_type,
        "优先级": "P1",  # MVP 默认 P1,ZJB 可调
        "Hook备选": [
            f"[Hook A] 基于命题核心洞察的开场 3 秒(待 ZJB/投手填写)",
            f"[Hook B] 备选角度(待填写)",
            f"[Hook C] 备选角度(待填写)",
        ],
        "视觉方向": "(待 ZJB/投手根据命题填写画面描述、色调、场景)",
        "广告正文": "(待填写,≤150 字)",
        "标题": "(待填写,≤40 字)",
        "CTA": "Shop Now",
        "KPI目标": {
            "CTR": "由命题推导(不设前置默认值)",
            "CPHQ": "由命题推导(阈值参考 规则-CPHQ阈值.md)",
            "观察窗口": "7 天",
        },
    }

    # 飞书消息和交接由 交接消息 agent 处理(单独 agent,职责分离)

    # 看板建议行(环3.3)
    dashboard_row = {
        "日期": upstream.get("data_date", "today"),
        "来源命题": statement[:40],
        "建议方向": f"命题达{confidence},建议按此方向出素材",
        "推荐投手": recommended_pitcher,
        "状态": "待跟进",
        "结果": "—",
    }

    data = {
        "策略简报": brief,
        "看板建议行": dashboard_row,
        "说明": [
            "策略简报在对话中输出,不写文件(环3.5 执行规则)",
            "Hook/视觉/正文 标'待填写' = 需要 ZJB 或投手补充具体创意",
            "KPI 目标由命题推导,不设前置默认值(strategy_brief.json)",
            "飞书/微信交接由 交接消息 agent 单独处理,本 agent 不管发送",
        ],
        "语气提示": "投手视角 · 陈述句+可执行判断",
    }

    # 合约三
    roles = ["投手"]
    role_check = validate_role(
        roles=roles,
        conclusion_type="命题升可信_自动执行桥",
        has_next_action=True,  # 这是业务内置流程,允许(合约三 L152)
    )
    if not role_check.ok:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"合约三校验失败: {role_check.errors}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # 合约二
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
        "is_system_flow": True,  # 附录 E 规则 3.1 业务内置流程
    }

    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
    )
