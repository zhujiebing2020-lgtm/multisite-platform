"""platform-core/事件层/dispatcher.py
Event → Task Dispatcher

把 bus.publish 出的事件,按 event_to_task.yaml 翻译成 Engine.submit。
启动时 bind_dispatcher(bus, engine) 注册订阅。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "引擎层"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import TaskEngine  # noqa: E402
from bus import EventBus, Event  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPO_ROOT / "platform-core" / "引擎层" / "event_to_task.yaml"


def load_mappings() -> list[dict]:
    with MAP_PATH.open(encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("mappings", []) or []


def _make_handler(engine: TaskEngine, rule: dict):
    def handler(ev: Event):
        engine.submit(
            agent_name=rule["target_agent"],
            site_id=ev.site_id,
            priority=rule.get("priority", 5),
            event_id=ev.event_id,
            lookback_days=rule.get("lookback_days", 7),
            upstream_output={"event_payload": ev.payload, "event_type": ev.type},
        )
    return handler


def bind_dispatcher(bus: EventBus, engine: TaskEngine) -> int:
    """注册全部 event_to_task 映射到 bus,返回注册数量"""
    mappings = load_mappings()
    for rule in mappings:
        bus.subscribe(rule["event_type"], _make_handler(engine, rule))
    return len(mappings)
