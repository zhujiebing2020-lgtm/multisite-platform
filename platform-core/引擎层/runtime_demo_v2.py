"""platform-core/引擎层/runtime_demo_v2.py

P0-9.3 demo — 数据分析 agent 端到端

mock 数据来源:crave-AI cards 5/12 真实快照(action-pitcher-2026-05-12.json)
  · HZM 共管组65 沈星回 CPHQ $2.68 / 10HVU
  · HZM 产品线组48 弯棒 CPHQ $0.95 / 26HVU(首个进 S 的产品线组)
  · CHJ 组17 18 Sensual CPHQ $0.94 / 727HVU(全盘第一)
  · CHJ 组5 30 Positions CPHQ $2.29 / 417HVU

跑两个视角:
  1. HZM 投手自看 — 只见自己的组
  2. ZJB 统筹 — 全部组,by_owner 拆解
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "事件层"))
sys.path.insert(0, str(HERE.parent / "事件层" / "sources"))

from engine import get_engine, reset_engine  # noqa: E402
from bus import get_bus, reset_bus  # noqa: E402
from dispatcher import bind_dispatcher  # noqa: E402
from invoker import drain_engine  # noqa: E402


# crave-AI cards 5/12 抽出的真实 mock(只算几个示例组)
DAILY_ROWS_0512 = [
    # CHJ 投手
    {"group_id": "17", "owner": "CHJ", "cphq": 0.94, "hvu": 26},  # 18 Sensual 全盘第一
    {"group_id": "5",  "owner": "CHJ", "cphq": 2.29, "hvu": 8},
    {"group_id": "7",  "owner": "CHJ", "cphq": 2.04, "hvu": 4},
    {"group_id": "4",  "owner": "CHJ", "cphq": 4.50, "hvu": 1},   # 进黄灯候选
    # HZM 投手
    {"group_id": "48", "owner": "HZM", "cphq": 0.95, "hvu": 26},  # 弯棒 首个 S 类产品线
    {"group_id": "65", "owner": "HZM", "cphq": 2.68, "hvu": 10},  # 沈星回 HZM 共管
    {"group_id": "49", "owner": "HZM", "cphq": 6.20, "hvu": 1},   # 玩具落地页疑似断裂
    {"group_id": "60", "owner": "HZM", "cphq": 0.00, "hvu": 8},   # spend=0 异常,归因延迟疑
    # HNN 投手
    {"group_id": "54", "owner": "HNN", "cphq": 7.90, "hvu": 0},   # 樱花 12 天 0HVU 立即停候选
    {"group_id": "58", "owner": "HNN", "cphq": 2.16, "hvu": 2},
]


def run_perspective(label: str, owner_filter: str | None):
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  视角:{label}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    reset_engine(); reset_bus()
    bus = get_bus(); engine = get_engine()
    bind_dispatcher(bus, engine)

    # 直接 submit 任务(模拟事件触发,真实场景 dispatcher 会 emit)
    upstream = {
        "daily_rows": DAILY_ROWS_0512,
        "owner_filter": owner_filter,
        "data_date": "2026-05-12",
    }
    engine.submit(agent_name="数据分析", site_id="elysianu", priority=3,
                  lookback_days=1, upstream_output=upstream)
    drain_engine(engine)

    task = engine.all_tasks()[-1]
    if not task.result:
        print("✗ 无结果")
        return
    r = task.result
    print(f"status: {r.status.value} · duration={r.duration_ms}ms")
    if r.gap_reason:
        print(f"gap_reason: {r.gap_reason}")
        return

    d = r.data
    print(f"\n视角: {d['视角']}")
    print(f"视角说明: {d['视角说明']}")
    print(f"在册组: {d['在册组数']} · 本次有日报数据的组: {d['本次有日报数据的组']}")

    print(f"\nCPHQ 灯色阈值(读自 {d['CPHQ 灯色阈值来源']['rule_file']}):")
    src = d["CPHQ 灯色阈值来源"]
    print(f"  绿 {src['绿']} · 黄 {src['黄']} · 橙 {src['橙']} · 红 {src['红']}")
    print(f"  规则 version {src['version']} · updated {src['updated']}")

    print(f"\n按灯色分类:")
    for color, entries in d["按灯色分类"].items():
        print(f"  【{color}】{len(entries)} 组")
        for e in entries:
            print(f"    · {e['group']:30s} owner={e['owner']:4s} CPHQ=${e['cphq']:.2f} HVU={e['hvu']}")

    if "按投手拆解" in d:
        print(f"\n按投手拆解(ZJB 视角):")
        for owner, stats in d["按投手拆解"].items():
            print(f"  {owner}: {stats['组数']} 组 · 绿灯 {stats['绿灯数']} · CPHQ 均 ${stats['CPHQ均值']}")

    print(f"\n合约标识:")
    io = d["_io_contract"]
    print(f"  target_role : {io['target_role']}")
    print(f"  rule_source : {io['rule_source']}")
    print(f"  语气提示    : {d['语气提示']}")


def main():
    print("━━━ P0-9.3 数据分析 agent · 端到端 demo ━━━")
    print(f"mock 数据来源:crave-AI cards 5/12 真实数据(10 个示例组)")

    run_perspective("HZM 投手自看", "HZM")
    run_perspective("ZJB 统筹(跨投手聚合)", None)


if __name__ == "__main__":
    main()
