"""platform-core/事件层/bus.py
EventBus · MVP

SVG L3 职责:持续监听 4 类事件(HVU下降/埋点失效/预算触顶/素材老化)+ 跨 agent 信号广播(§15.4)

MVP 形态:
  - 内存订阅表,进程内同步发布
  - dispatch 触发 Engine.submit,不直接调 agent
  - 不持久化(P1 加事件日志落 data-runtime)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Event:
    event_id: str
    type: str                       # 与 event_to_task.yaml#event_type 字符串对齐
    site_id: str
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    source: str = ""                # 谁发的(heuristic/技术-埋点/数据-归因/...)


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self):
        # type → [subscriber, ...];特殊 key "*" = 所有事件
        self._subs: dict[str, list[Subscriber]] = {}
        self._log: list[Event] = []         # 简单内存日志,P1 落 data-runtime

    def subscribe(self, event_type: str, fn: Subscriber) -> None:
        self._subs.setdefault(event_type, []).append(fn)

    def publish(
        self,
        type: str,
        site_id: str,
        payload: Optional[dict] = None,
        source: str = "",
    ) -> Event:
        ev = Event(
            event_id=str(uuid.uuid4())[:8],
            type=type,
            site_id=site_id,
            payload=payload or {},
            source=source,
        )
        self._log.append(ev)

        for fn in self._subs.get(type, []):
            fn(ev)
        for fn in self._subs.get("*", []):
            fn(ev)
        return ev

    def log(self) -> list[Event]:
        return list(self._log)


# 进程单例
_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    global _bus
    _bus = None
