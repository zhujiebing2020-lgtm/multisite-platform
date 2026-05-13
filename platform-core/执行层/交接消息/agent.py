"""platform-core/执行层/交接消息/agent.py

交接消息 agent · 策略简报 → 飞书/微信粘贴版 + 看板建议表追加

职责(CLAUDE.md 环3.3 + 环3.4):
  · 接策略简报 / 文案 / 故事脚本 agent 的输出
  · 格式化为飞书/微信可粘贴的"素材需求"消息
  · 追加看板建议行

输出:
  · target_role=[投手, 承接层]
  · rule_source=platform-core/规则/strategy_brief.json
  · 不发送(P1 接 飞书 webhook / n8n),只生成可粘贴文本
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

PLATFORM_CORE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM_CORE / "中间件"))
sys.path.insert(0, str(PLATFORM_CORE / "执行层"))

from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402
from target_role校验 import validate as validate_role  # noqa: E402
from 规则指针校验 import validate as validate_rule  # noqa: E402

name = "交接消息"
RULE_SOURCE = "platform-core/规则/strategy_brief.json"


def run(inp: AgentInput) -> AgentResult:
    t0 = time.time()
    upstream = inp.upstream_output or {}

    brief = upstream.get("brief", {})
    copy_pack = upstream.get("copy_pack", {})
    if not brief:
        return AgentResult(
            status=AgentStatus.NO_DATA,
            gap_reason="上游未传入 brief(策略简报输出)",
            duration_ms=int((time.time()-t0)*1000),
            agent_name=name, site_id=inp.site_id,
        )

    statement = brief.get("来源命题", "?")
    pitcher = brief.get("推荐投手", "?")
    landing = brief.get("落地页类型", "?")
    today = datetime.now().strftime("%Y-%m-%d")

    # 飞书/微信粘贴版(CLAUDE.md 环3.4 模板)
    hooks = copy_pack.get("hooks", brief.get("Hook备选", []))
    hook_a = hooks[0]["draft"] if hooks and isinstance(hooks[0], dict) else (hooks[0] if hooks else "(待生成)")

    feishu_text = f"""【素材需求 · {today}】
命题依据:{statement}

主题方向:基于命题「{statement[:30]}...」的投放
Hook(选一):
  A. {hook_a}
  B. {hooks[1]['draft'] if len(hooks) > 1 and isinstance(hooks[1], dict) else (hooks[1] if len(hooks) > 1 else '(待生成)')}
  C. {hooks[2]['draft'] if len(hooks) > 2 and isinstance(hooks[2], dict) else (hooks[2] if len(hooks) > 2 else '(待生成)')}

视觉方向:{brief.get('视觉方向', '(待生成)')}
落地页:{landing}
目标 CPHQ:{brief.get('KPI目标', {}).get('CPHQ', '由命题推导')}
推荐投手:{pitcher}

target_role: [投手, 承接层]
规则来源:{RULE_SOURCE}"""

    # 看板建议行(环3.3)
    dashboard_row = f"| {today} | [[{statement[:40]}]] | 命题升可信,建议出素材 | {pitcher} | 待跟进 | — |"

    data = {
        "飞书/微信粘贴版": feishu_text,
        "看板建议行": dashboard_row,
        "说明": [
            "本 agent 不实际发送消息,仅生成可粘贴文本(P1 接飞书 webhook/n8n)",
            "ZJB 确认后,文本可直接复制粘贴到飞书或微信群",
            "看板建议行需 ZJB 拍板后人工追加到当日看板",
        ],
        "语气提示": "投手+承接层 · 陈述句+可执行(不加 next_action)",
    }

    roles = ["投手", "承接层"]
    rc = validate_role(
        roles=roles,
        conclusion_type="命题升可信_自动执行桥",
        has_next_action=True,
    )
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
