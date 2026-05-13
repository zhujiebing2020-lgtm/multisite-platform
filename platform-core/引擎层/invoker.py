"""platform-core/引擎层/invoker.py
任务执行器 + Engine 驱动器

两种入口:
  · execute_task(task):单任务执行(被 drain 调用,也可直接调用绕过 Engine)
  · drain_engine(engine):顺序消费 Engine 队列直到空
  · invoke_agent(...)(legacy CLI):直调单 agent,等价"提交一个 priority=5 任务后立刻 drain"

历史继承:execute_task 在调 agent 前会从 engine.history 读上次结果注入 upstream_output。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_CORE = REPO_ROOT / "platform-core"

sys.path.insert(0, str(PLATFORM_CORE / "上下文层"))
from loader import load_site_config  # noqa: E402
from context import LoadedConfig  # noqa: E402

sys.path.insert(0, str(PLATFORM_CORE / "执行层"))
from _base import AgentInput, AgentResult, AgentStatus, TimeWindow  # noqa: E402

sys.path.insert(0, str(PLATFORM_CORE / "引擎层"))
from engine import Task, TaskEngine, TaskStatus, get_engine  # noqa: E402

sys.path.insert(0, str(PLATFORM_CORE / "事件层"))
from bus import get_bus  # noqa: E402

sys.path.insert(0, str(PLATFORM_CORE / "数据层"))
try:
    from runtime import get_data_runtime  # noqa: E402
    _HAS_DR = True
except Exception:
    _HAS_DR = False

import yaml  # noqa: E402


class AgentNotFoundError(Exception): ...


def _load_agent_module(agent_name: str):
    agent_file = PLATFORM_CORE / "执行层" / agent_name / "agent.py"
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
    if not content_ref:
        return None
    pack_id = content_ref.split("@")[0]
    path = PLATFORM_CORE / "能力包" / "内容包-调性话术" / f"{pack_id}.yaml"
    if not path.is_file():
        return {"_warning": f"内容包文件不存在: {path}"}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def execute_task(task: Task, engine: TaskEngine) -> AgentResult:
    """执行单个任务,落历史"""
    cfg = load_site_config(task.site_id)

    # 白名单校验
    if task.agent_name not in cfg.enabled_agents:
        result = AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=(
                f"agent {task.agent_name!r} 未在打法包 {cfg.playbook_ref} 的 "
                f"enabled_agents={cfg.enabled_agents} 中"
            ),
            agent_name=task.agent_name,
            site_id=task.site_id,
        )
        engine.complete(task.task_id, result)
        return result

    # 加载 agent
    try:
        mod = _load_agent_module(task.agent_name)
    except AgentNotFoundError as e:
        result = AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=str(e),
            agent_name=task.agent_name,
            site_id=task.site_id,
        )
        engine.complete(task.task_id, result)
        return result

    # 注入阈值 + 内容包 + 历史(同站同 agent 的上次结果)
    overrides_flat = {k: v.value for k, v in cfg.resolved_thresholds.items()}
    content_pack_data = (
        _load_content_pack(cfg.content_pack)
        if task.agent_name == "创意-素材" else None
    )

    # 历史继承:优先内存,fallback 落库(重启后内存为空也能拿到上次)
    last = engine.last_result(task.site_id, task.agent_name)
    previous_summary = None
    if last is not None:
        previous_summary = {
            "source": "memory",
            "status": last.status.value,
            "data_keys": list(last.data.keys()),
        }
    elif _HAS_DR:
        try:
            row = get_data_runtime().last_agent_result(task.site_id, task.agent_name)
            if row is not None:
                import json as _j
                data_keys = list((_j.loads(row.get("data_json") or "{}") or {}).keys())
                previous_summary = {
                    "source": "data-runtime",
                    "status": row["status"],
                    "data_keys": data_keys,
                    "ts": row["ts"],
                }
        except Exception:
            pass

    upstream = task.upstream_output or {}
    if previous_summary is not None:
        upstream = {**upstream, "previous_result": previous_summary}

    inp = AgentInput(
        site_id=task.site_id,
        time_window=TimeWindow.last_n_days(task.lookback_days),
        upstream_output=upstream or None,
        overrides=overrides_flat,
        content_pack=content_pack_data,
    )

    # 调用 + 落历史
    try:
        result = mod.run(inp)
    except Exception as e:
        engine.fail(task.task_id, f"agent.run 异常: {e}")
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"agent.run raised: {e}",
            agent_name=task.agent_name,
            site_id=task.site_id,
        )
    engine.complete(task.task_id, result)

    # 跨 agent 影响(§15.4):转发 agent 声明的 emit_events 到 bus
    # 自然规避循环:event_to_task.yaml 的 mapping 决定订阅,自调用映射不会被写进表
    if result.emit_events:
        bus = get_bus()
        for ev in result.emit_events:
            bus.publish(
                type=ev["type"],
                site_id=task.site_id,
                payload=ev.get("payload", {}),
                source=task.agent_name,
            )

    return result


def drain_engine(engine: TaskEngine, max_iter: int = 1000) -> list[AgentResult]:
    """顺序消费 Engine 队列直到空,返回所有 AgentResult"""
    results = []
    i = 0
    while True:
        task = engine.next()
        if task is None:
            break
        results.append(execute_task(task, engine))
        i += 1
        if i >= max_iter:
            raise RuntimeError(f"drain_engine 超过 {max_iter} 次,可能死循环")
    return results


def invoke_agent(
    agent_name: str,
    site_id: str,
    lookback_days: int = 7,
    upstream_output: dict | None = None,
) -> tuple[LoadedConfig, AgentResult]:
    """Legacy 单 agent 直调:提交一个任务 + drain"""
    engine = get_engine()
    task_id = engine.submit(
        agent_name=agent_name,
        site_id=site_id,
        priority=5,
        lookback_days=lookback_days,
        upstream_output=upstream_output,
    )
    drain_engine(engine)
    cfg = load_site_config(site_id)
    task = engine.get_task(task_id)
    return cfg, task.result


# ─── CLI ─────────────────────────────────────────
if __name__ == "__main__":
    import json

    if len(sys.argv) < 3:
        print("用法: python invoker.py <site_id> <agent_name>")
        sys.exit(1)
    cfg, result = invoke_agent(sys.argv[2], sys.argv[1])

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
    if result.gap_reason:
        print(f"  gap_reason     : {result.gap_reason}")
    print()
    print(f"━━━ Agent.data ━━━")
    print(json.dumps(result.data, ensure_ascii=False, indent=2))
