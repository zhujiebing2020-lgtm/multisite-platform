"""platform-core/引擎层/invoker.py
invoke_agent(agent_name, site_id, ...) — 唯一对外的 agent 执行入口

MVP 形态(本文件不做):
  - 任务队列(留 P1,本文件直接调)
  - 状态机(留 P1)
  - 优先级(留 P1)
  - 回滚(留 P1)
  - 历史继承(留 P1)

MVP 形态(本文件做):
  - 收到 (agent_name, site_id) → load_site_config → 动态 import agent → run → 返回 AgentResult
  - 把 resolved_thresholds 注入 AgentInput.overrides
  - 把 content_pack 内容注入 AgentInput.content_pack(如果是 创意-素材 agent)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_CORE = REPO_ROOT / "platform-core"

# 上下文层 import
sys.path.insert(0, str(PLATFORM_CORE / "上下文层"))
from loader import load_site_config  # noqa: E402
from context import LoadedConfig  # noqa: E402

# 执行层 import
sys.path.insert(0, str(PLATFORM_CORE / "执行层"))
from _base import AgentInput, AgentResult, AgentStatus, TimeWindow  # noqa: E402

import yaml  # noqa: E402


class AgentNotFoundError(Exception): ...


def _load_agent_module(agent_name: str):
    """动态加载 platform-core/执行层/{agent_name}/agent.py"""
    agent_dir = PLATFORM_CORE / "执行层" / agent_name
    agent_file = agent_dir / "agent.py"
    if not agent_file.is_file():
        raise AgentNotFoundError(
            f"找不到 agent: {agent_name} (期望 {agent_file})"
        )
    spec = importlib.util.spec_from_file_location(
        f"agent_{agent_name}", agent_file
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_content_pack(content_ref: str | None) -> dict | None:
    """content_ref 形如 '限时紧迫-折扣站@v0.1.0'。MVP 简单读 yaml,版本不强校验。"""
    if not content_ref:
        return None
    pack_id = content_ref.split("@")[0]
    path = PLATFORM_CORE / "能力包" / "内容包-调性话术" / f"{pack_id}.yaml"
    if not path.is_file():
        return {"_warning": f"内容包文件不存在: {path}"}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def invoke_agent(
    agent_name: str,
    site_id: str,
    lookback_days: int = 7,
    upstream_output: dict | None = None,
    runtime_overrides: dict | None = None,
) -> tuple[LoadedConfig, AgentResult]:
    """
    端到端:加载站上下文 → 动态加载 agent → 调 run → 返回 (cfg, result)

    返回 cfg 也是为了让调用方能拿到溯源信息(playbook_ref / thresholds 来源)。
    """
    # Step 1 · 加载站上下文(loader.md §1)
    cfg = load_site_config(site_id, runtime_overrides=runtime_overrides)

    # Step 2 · 校验 agent 是否被启用
    if agent_name not in cfg.enabled_agents:
        return cfg, AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=(
                f"agent {agent_name!r} 未在打法包 {cfg.playbook_ref} 的 "
                f"enabled_agents 中,拒绝执行。当前启用: {cfg.enabled_agents}"
            ),
            agent_name=agent_name,
            site_id=site_id,
        )

    # Step 3 · 注入阈值 + 内容包
    overrides_flat = {k: v.value for k, v in cfg.resolved_thresholds.items()}
    content_pack_data = (
        _load_content_pack(cfg.content_pack) if agent_name == "创意-素材" else None
    )

    inp = AgentInput(
        site_id=site_id,
        time_window=TimeWindow.last_n_days(lookback_days),
        upstream_output=upstream_output,
        overrides=overrides_flat,
        content_pack=content_pack_data,
    )

    # Step 4 · 动态加载并调 agent
    try:
        mod = _load_agent_module(agent_name)
    except AgentNotFoundError as e:
        return cfg, AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=str(e),
            agent_name=agent_name,
            site_id=site_id,
        )

    result = mod.run(inp)
    return cfg, result


# ─── CLI ─────────────────────────────────────────
if __name__ == "__main__":
    import json

    if len(sys.argv) < 3:
        print("用法: python invoker.py <site_id> <agent_name>")
        print("示例: python invoker.py elysianu 流量-投放")
        sys.exit(1)

    site_id = sys.argv[1]
    agent_name = sys.argv[2]

    cfg, result = invoke_agent(agent_name, site_id)

    print(f"━━━ 站上下文 ━━━")
    print(f"  site_id        : {cfg.site_id}")
    print(f"  playbook_ref   : {cfg.playbook_ref}")
    print(f"  enabled_agents : {cfg.enabled_agents}")
    print(f"  content_pack   : {cfg.content_pack}")
    print()
    print(f"━━━ Agent 调用 ━━━")
    print(f"  agent          : {result.agent_name}")
    print(f"  status         : {result.status.value}")
    print(f"  duration_ms    : {result.duration_ms}")
    print(f"  cost_usd       : {result.cost}")
    if result.gap_reason:
        print(f"  gap_reason     : {result.gap_reason}")
    print()
    print(f"━━━ Agent.data ━━━")
    print(json.dumps(result.data, ensure_ascii=False, indent=2))
