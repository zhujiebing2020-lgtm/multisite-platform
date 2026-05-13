"""platform-core/事件层/sources/heuristic.py
启发式事件源 · MVP

真事件源(P1):AdClaw MCP 实时数据 / Meta webhook / 站内埋点流。
MVP:CLI 手动触发产事件,验证整条链路通。

用法:
  python heuristic.py elysianu HVU下降
  python heuristic.py elysianu 素材老化 --payload '{"ctr_drop_pct": 35}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bus import get_bus, Event  # noqa: E402


def emit(event_type: str, site_id: str, payload: dict | None = None) -> Event:
    bus = get_bus()
    return bus.publish(
        type=event_type,
        site_id=site_id,
        payload=payload or {},
        source="heuristic-cli",
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python heuristic.py <site_id> <event_type> [--payload JSON]")
        print("示例: python heuristic.py elysianu HVU下降")
        sys.exit(1)
    site_id, event_type = sys.argv[1], sys.argv[2]
    payload = {}
    if "--payload" in sys.argv:
        i = sys.argv.index("--payload")
        payload = json.loads(sys.argv[i + 1])
    ev = emit(event_type, site_id, payload)
    print(f"✓ 已发布事件 {ev.event_id} type={ev.type} site={ev.site_id}")
