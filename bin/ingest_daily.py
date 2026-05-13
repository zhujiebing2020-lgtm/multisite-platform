"""bin/ingest_daily.py
multisite-platform 原生 ingest · 不改 fork 脚本

输入:   platform-core/数据底盘/ad_history/current_account_daily_long.csv(已 fork 只读)
        或 --from-xlsx 指定外部 xlsx
输出:   platform-core/数据层/runtime.db(agent_history / 本地库)
        +  trigger 一次 数据分析 agent 跑全链路

作用:
  · 不改 fork 的 ingest_from_daily_long.py(保持源只读)
  · 直接读 CSV → 当作 daily_rows 推给数据分析 agent
  · agent 跑完 → 落 sqlite → export_dashboard + build 重生成看板
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DAILY_CSV = REPO / "platform-core/数据底盘/ad_history/current_account_daily_long.csv"


def load_daily_rows(dates_filter: list = None, owner_filter: str = None) -> list:
    rows = []
    with DAILY_CSV.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if dates_filter and r.get("date") not in dates_filter:
                continue
            if owner_filter and r.get("advertiser") != owner_filter:
                continue
            rows.append({
                "group": r.get("group", ""),
                "group_id": r.get("group", ""),
                "owner": r.get("advertiser", ""),
                "date": r.get("date", ""),
                "spend": float(r["spend"]) if r.get("spend") else 0,
                "hvu": int(r["hvu"]) if r.get("hvu") else 0,
                "cphq": float(r["cphq"]) if r.get("cphq") else None,
            })
    return rows


def ingest_and_run(dates_filter: list = None, owners_to_run: list = None):
    sys.path.insert(0, str(REPO / "platform-core/执行层"))
    sys.path.insert(0, str(REPO / "platform-core/中间件"))
    sys.path.insert(0, str(REPO / "platform-core/数据层"))
    sys.path.insert(0, str(REPO / "platform-core/引擎层"))

    import importlib.util
    p = REPO / "platform-core/执行层/数据分析/agent.py"
    spec = importlib.util.spec_from_file_location("agent_数据分析", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from _base import AgentInput, TimeWindow
    from engine import get_engine

    # 读 CSV
    rows = load_daily_rows(dates_filter=dates_filter)
    print(f"✓ 读 CSV {len(rows)} 行" + (f"(日期筛 {dates_filter})" if dates_filter else ""))

    # 按 owner 分组,每个 owner 单独跑一次数据分析
    owners = owners_to_run or ["HZM", "CHJ", "HNN", None]  # None = ZJB 视角
    engine = get_engine()

    for owner in owners:
        owner_rows = [r for r in rows if owner is None or r["owner"] == owner]
        if not owner_rows:
            continue
        label = "ZJB 视角" if owner is None else f"投手 {owner}"

        upstream = {
            "daily_rows": owner_rows,
            "owner_filter": owner,
            "data_date": datetime.now().strftime("%Y-%m-%d"),
        }
        tid = engine.submit("数据分析", "elysianu", priority=3,
                           lookback_days=7, upstream_output=upstream)
        task = engine.next()
        inp = AgentInput(site_id="elysianu", time_window=TimeWindow.last_n_days(7),
                         overrides={"owner_filter": owner} if owner else {},
                         upstream_output=upstream)
        r = mod.run(inp)
        engine.complete(tid, r)
        print(f"  ✓ {label} · status={r.status.value} · {len(owner_rows)} 行数据")

    # 重生成看板
    print("\n━━━ 重生成 dashboard ━━━")
    subprocess.run([sys.executable, str(REPO / "bin/export_dashboard.py")], check=False)
    subprocess.run([sys.executable, str(REPO / "bin/build.py")], check=False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="多站群 native ingest")
    parser.add_argument("--dates", nargs="+", help="筛日期,e.g. 2026-05-12 2026-05-13")
    parser.add_argument("--owner", nargs="+", help="只跑指定投手,e.g. HZM CHJ")
    args = parser.parse_args()

    print(f"━━━ multisite-platform ingest ━━━")
    print(f"源 CSV: {DAILY_CSV}")
    print(f"日期: {args.dates or '(全部)'}")
    print(f"投手: {args.owner or '(全部)'}\n")
    ingest_and_run(dates_filter=args.dates, owners_to_run=args.owner)


if __name__ == "__main__":
    main()
