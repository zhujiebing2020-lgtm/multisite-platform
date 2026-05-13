"""bin/export_dashboard.py
从 sqlite agent_history → 导出按投手聚合的 cards JSON

输出位置:
  data/cards/多站群-{date}-{owner}.json   每个投手一份
  data/cards/多站群-{date}-总览.json       ZJB 视角

用法:
  python3 bin/export_dashboard.py           导出今天
  python3 bin/export_dashboard.py 2026-05-13  导出指定日期
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "platform-core" / "数据层" / "runtime.db"
CARDS_DIR = REPO / "data" / "cards"


def export(date: str):
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    if not DB.is_file():
        print(f"⚠ db 不存在: {DB},先跑一次 agent 产数据")
        return

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # 读所有 agent_history(MVP 不按日期过滤,先看全部)
    rows = conn.execute(
        "SELECT * FROM agent_history ORDER BY ts DESC LIMIT 100"
    ).fetchall()

    by_owner: dict[str, list] = {}
    overview: dict = {"agents": {}, "events_recent": []}

    for r in rows:
        data = json.loads(r["data_json"]) if r["data_json"] else {}
        agent = r["agent_name"]
        entry = {
            "ts": r["ts"],
            "status": r["status"],
            "duration_ms": r["duration_ms"],
            "data": data,
        }
        overview["agents"].setdefault(agent, []).append(entry)

        # 数据分析 agent 的输出按 owner 拆
        if agent == "数据分析":
            view = data.get("视角", "")
            if "投手" in view:
                owner = view.replace("投手 ", "").replace(" 自看", "").strip()
                by_owner.setdefault(owner, []).append(entry)
            else:
                by_owner.setdefault("ZJB", []).append(entry)

    # 读 events
    events = conn.execute(
        "SELECT * FROM events ORDER BY ts DESC LIMIT 30"
    ).fetchall()
    overview["events_recent"] = [
        {"ts": e["ts"], "type": e["type"], "source": e["source"]}
        for e in events
    ]
    conn.close()

    # 写总览
    overview_path = CARDS_DIR / f"多站群-{date}-总览.json"
    overview_path.write_text(
        json.dumps({
            "_meta": {"date": date, "card_type": "dashboard_overview", "generated_at": datetime.now().isoformat()},
            **overview,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ 写入 {overview_path}")

    # 每个投手一份
    for owner, entries in by_owner.items():
        path = CARDS_DIR / f"多站群-{date}-{owner}.json"
        path.write_text(
            json.dumps({
                "_meta": {"date": date, "owner": owner, "card_type": "pitcher_view",
                          "generated_at": datetime.now().isoformat()},
                "agent_outputs": entries,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✓ 写入 {path}")


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    export(date)
