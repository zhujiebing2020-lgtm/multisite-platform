"""platform-core/引擎层/runtime_demo.py
端到端演示:事件发布 → 事件→任务映射 → Task Engine 调度 → Agent 执行 → 历史落库

用法:
  python runtime_demo.py elysianu 单事件 HVU下降
  python runtime_demo.py elysianu 多事件 HVU下降 素材老化 预算触顶
  python runtime_demo.py elysianu 历史继承   # 连发两次同事件,验证 previous_result 注入
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# sys.path 必须先设置完,再 import
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                            # 引擎层
sys.path.insert(0, str(HERE.parent / "事件层"))          # 事件层
sys.path.insert(0, str(HERE.parent / "事件层" / "sources"))  # 事件层/sources

from engine import get_engine, reset_engine, TaskStatus  # noqa: E402
from bus import get_bus, reset_bus  # noqa: E402
from dispatcher import bind_dispatcher  # noqa: E402
from invoker import drain_engine  # noqa: E402
from heuristic import emit  # noqa: E402


def setup():
    reset_engine()
    reset_bus()
    bus = get_bus()
    engine = get_engine()
    n = bind_dispatcher(bus, engine)
    return bus, engine, n


def print_engine_state(engine, label: str):
    print(f"\n━━━ {label} ━━━")
    for t in engine.all_tasks():
        print(
            f"  task {t.task_id} · agent={t.agent_name:8s} · priority={t.priority} "
            f"· status={t.status.value:10s} · seq={t.seq}"
        )
        if t.result:
            print(f"      ↳ agent_status={t.result.status.value}")
            if t.result.gap_reason:
                print(f"      ↳ gap_reason={t.result.gap_reason}")


def mode_single(site_id: str, event_type: str):
    bus, engine, n = setup()
    print(f"已注册 {n} 条 event_to_task 映射")
    ev = bus.publish(type=event_type, site_id=site_id, source="demo")
    print(f"发布事件 {ev.event_id} type={event_type}")
    print_engine_state(engine, "队列(事件发布后,执行前)")
    drain_engine(engine)
    print_engine_state(engine, "队列(drain 完成后)")


def mode_multi(site_id: str, event_types: list[str]):
    bus, engine, n = setup()
    print(f"已注册 {n} 条 event_to_task 映射")
    for et in event_types:
        bus.publish(type=et, site_id=site_id, source="demo")
        print(f"发布事件 type={et}")
    print_engine_state(engine, "队列(执行前 — 按发布顺序展示)")

    # 用 drain 时打印真实消费顺序(按 priority,小=优先)
    from invoker import execute_task
    print(f"\n━━━ 真实消费顺序(按 priority 0→9)━━━")
    i = 0
    while True:
        t = engine.next()
        if t is None: break
        i += 1
        print(f"  第 {i} 个取出: priority={t.priority} · agent={t.agent_name} · task={t.task_id}")
        execute_task(t, engine)
    print_engine_state(engine, "队列(drain 完成后)")


def mode_history(site_id: str):
    """验证历史继承:同事件发两次,第二次 agent 应能看到 previous_result"""
    bus, engine, n = setup()
    print(f"已注册 {n} 条 event_to_task 映射")

    print("\n>>> 第 1 次:发 HVU下降")
    bus.publish(type="HVU下降", site_id=site_id, source="demo")
    drain_engine(engine)

    print("\n>>> 第 2 次:再发 HVU下降")
    bus.publish(type="HVU下降", site_id=site_id, source="demo")
    drain_engine(engine)

    print(f"\n━━━ 历史继承断言 ━━━")
    count = engine.history_count(site_id, "数据-归因")
    last = engine.last_result(site_id, "数据-归因")
    print(f"  engine.history[(elysianu, 数据-归因)] 长度 = {count}")
    print(f"  last_result.status = {last.status.value}")

    # 第二个任务的 upstream_output 里应该有 previous_result
    second_task = engine.all_tasks()[1]
    upstream_in_second = second_task.upstream_output
    print(f"\n  第 2 个任务 upstream_output keys = {list((upstream_in_second or {}).keys())}")
    # 但 upstream 是事件 payload + previous_result(在 execute_task 内合并)
    # 这里只能从 task 本身看 event_payload;previous_result 是 execute_task 注入到 AgentInput
    # 验证:第 2 个 task 的 result.data 应该和第 1 个相似(同 stub)
    print(f"  第 2 个任务 result 存在? {second_task.result is not None}")


def mode_cascade(site_id: str):
    """级联:HVU下降 → 数据-归因 → emit attribution_risk → 流量-投放 → 降权建议"""
    import json
    bus, engine, n = setup()
    print(f"已注册 {n} 条 event_to_task 映射\n")

    print(">>> 发布 HVU下降")
    bus.publish(type="HVU下降", site_id=site_id, source="demo")
    print(f"  队列 pending: {engine.pending_count()}(应=1,数据-归因)")

    print("\n>>> drain Engine(数据-归因 跑完后会自动发 attribution_risk → 触发 流量-投放)")
    results = drain_engine(engine)

    print(f"\n━━━ 总共消费 {len(results)} 个任务 ━━━")
    for i, t in enumerate(engine.all_tasks(), 1):
        print(f"  [{i}] task={t.task_id} agent={t.agent_name} priority={t.priority} "
              f"event_id={t.event_id} status={t.status.value}")

    print(f"\n━━━ 事件流水(bus.log)━━━")
    for ev in bus.log():
        print(f"  · {ev.event_id} type={ev.type} source={ev.source} "
              f"payload_keys={list(ev.payload.keys())}")

    # 找到 流量-投放 那一次,验证它拿到了 attribution_risk 上下文
    traffic_result = engine.last_result(site_id, "流量-投放")
    print(f"\n━━━ 流量-投放 拿到 attribution_risk 后的输出 ━━━")
    if traffic_result and "attribution_response" in traffic_result.data:
        print(json.dumps(traffic_result.data["attribution_response"], ensure_ascii=False, indent=2))
    else:
        print("  (未触发 attribution_response,可能 utm_coverage 未低于阈值)")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    site_id, mode = sys.argv[1], sys.argv[2]
    if mode == "单事件":
        mode_single(site_id, sys.argv[3])
    elif mode == "多事件":
        mode_multi(site_id, sys.argv[3:])
    elif mode == "历史继承":
        mode_history(site_id)
    elif mode == "级联":
        mode_cascade(site_id)
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
