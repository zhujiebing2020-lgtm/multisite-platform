#!/usr/bin/env python3
"""
Step 4.3 + 4.4 的 csv-based 注入脚本。
从 data/ad_history/current_account_daily_long.csv 读取 5/9-5/10(或 --dates 指定)
→ 喂 crave_metrics.db(append)+ 重写 renderer/dashboard_data.json(全量)

用法:
    python3 ingest_from_daily_long.py                          # 喂所有 DB 里没有的新日期
    python3 ingest_from_daily_long.py --dates 2026-05-09 2026-05-10
"""
from __future__ import annotations
import sys, csv, json, sqlite3, argparse, re
from pathlib import Path

REPO = Path.home() / "Documents/GitHub/crave-AI"
ENGINE = Path.home() / "Documents/GitHub/crave-ai-2"
DB = REPO / "crave_metrics.db"
DAILY = REPO / "data/ad_history/current_account_daily_long.csv"
TIER = REPO / "data/ad_history/current_account_group_summary_tiered.csv"
URL_MAP = REPO / "renderer/url_map.json"
OUT = REPO / "renderer/dashboard_data.json"
GROUP_MASTER = REPO / "data/rules/group_master.json"


def load_group_master() -> dict:
    """读 group_master.json · 返回 {组号(int): {...}} · 数据主权权威源."""
    if not GROUP_MASTER.exists():
        print(f"⚠ {GROUP_MASTER} 不存在 · advertiser/landing 将从 daily_long 反推(不推荐)")
        return {}
    d = json.loads(GROUP_MASTER.read_text())
    return {int(k): v for k, v in d.get("groups", {}).items()}


def rebuild_tiered(rows: list[dict], master: dict):
    """重算 tiered.csv · advertiser/landing 强制从 group_master 取."""
    from collections import defaultdict
    from datetime import date as _date

    by_group = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r)

    def tier_of(ts, th, dl):
        if dl < 7: return "O"
        if th == 0: return "R"
        c = ts / th if th else 999
        if c <= 3: return "S"
        if c <= 5: return "A"
        return "B"

    def group_num(name):
        m = re.match(r"^组(\d+)", str(name))
        return int(m.group(1)) if m else None

    new_rows = []
    for g, items in by_group.items():
        items.sort(key=lambda x: x["date"])
        first, last = items[0]["date"], items[-1]["date"]
        fd, ld = _date.fromisoformat(first), _date.fromisoformat(last)
        dl = (ld - fd).days + 1
        ts = round(sum(float(x["spend"] or 0) for x in items), 2)
        th = sum(int(float(x["hvu"] or 0)) for x in items)
        t = tier_of(ts, th, dl)
        n = group_num(g)
        m_rec = master.get(n, {})
        new_rows.append({
            "group": g,
            "advertiser": m_rec.get("owner") or "?",
            "landing": m_rec.get("landing") or "",
            "first_day": first, "last_day": last, "days_live": dl,
            "total_spend": ts, "total_hvu": th,
            "total_cphq": f"{ts/th:.2f}" if th else "",
            "tier": t,
        })

    new_rows.sort(key=lambda x: group_num(x["group"]) or 9999)
    with TIER.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group","advertiser","landing","first_day","last_day","days_live","total_spend","total_hvu","total_cphq","tier"])
        w.writeheader()
        for r in new_rows:
            w.writerow(r)

    from collections import Counter
    cnt = Counter(r["tier"] for r in new_rows)
    miss = sum(1 for r in new_rows if r["advertiser"] == "?" or not r["landing"])
    print(f"tiered.csv 重算: {len(new_rows)} 组 · 分层 {dict(cnt)} · 缺 master {miss}")


def classify(lp: str) -> str:
    lp = (lp or "").strip()
    if "scene" in lp or "exp-app" in lp: return "scene"
    if "ai-sex-toys" in lp: return "product"
    return "article"


def load_daily() -> list[dict]:
    rows = []
    with DAILY.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not (r.get("group") or "").strip(): continue
            rows.append({
                "group": r["group"].strip(),
                "advertiser": (r.get("advertiser") or "?").strip(),
                "landing": (r.get("landing") or "").strip(),
                "date": (r.get("date") or "").strip(),
                "spend": float(r.get("spend") or 0),
                "hvu": int(float(r.get("hvu") or 0)),
            })
    return rows


def short_of(name: str) -> str:
    m = re.match(r"^(组\d+)", name)
    return m.group(1) if m else name


def inject_to_db(rows: list[dict], target_dates: set[str]) -> int:
    """喂 crave_metrics.db,只注入 target_dates 里的日期。"""
    sys.path.insert(0, str(ENGINE))
    from core.metric_graph.dag import MetricDAG
    from core.propagation.engine import PropagationEngine
    from core.state_store.sqlite import SQLiteStateStore

    dag = MetricDAG.load_from_yaml(str(ENGINE / "schemas/metrics.yaml"))
    store = SQLiteStateStore(str(DB))
    engine = PropagationEngine(dag, store)

    count = 0
    for r in rows:
        if r["date"] not in target_dates: continue
        short = short_of(r["group"])
        if r["spend"] > 0:
            engine.handle_event({
                "event_type": "ad_spend_report",
                "amount": r["spend"],
                "ad_group": short,
                "advertiser": r["advertiser"],
                "date": r["date"],
            })
        for i in range(r["hvu"]):
            engine.handle_event({
                "event_type": "hvu_session",
                "session_id": f'{short}_{r["date"]}_{i}',
                "ad_group": short,
                "advertiser": r["advertiser"],
                "date": r["date"],
            })
        count += 1
    store.close()
    return count


def existing_db_dates() -> set[str]:
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT SUBSTR(dim_key, INSTR(dim_key, '2026-'), 10) FROM metric_state WHERE dim_key LIKE '%2026-%'")
    d = set(r[0] for r in cur.fetchall() if r[0])
    conn.close()
    return d


def rebuild_dashboard_json(rows: list[dict]):
    """全量重建 renderer/dashboard_data.json(与 run_dashboard.sh Step2 口径一致)。"""
    url_map = json.loads(URL_MAP.read_text()) if URL_MAP.exists() else {}

    # 聚合
    from collections import defaultdict
    history_per_group = defaultdict(dict)          # short -> date_mmdd -> {spend,hvu}
    meta_per_group = {}                             # short -> {full_name,advertiser,landing_type}
    all_iso_dates = set()

    for r in rows:
        short = short_of(r["group"])
        iso = r["date"]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", iso): continue
        all_iso_dates.add(iso)
        y, mo, d = iso.split("-")
        mmdd = f"{int(mo)}/{int(d)}"
        history_per_group[short][mmdd] = {"spend": r["spend"], "hvu": r["hvu"]}
        if short not in meta_per_group:
            meta_per_group[short] = {
                "full_name": r["group"],
                "advertiser": r["advertiser"],
                "landing_type": classify(r["landing"]),
            }

    dates_sorted = sorted(all_iso_dates)
    dates_mmdd = [f"{int(x.split('-')[1])}/{int(x.split('-')[2])}" for x in dates_sorted]
    latest = dates_mmdd[-1] if dates_mmdd else None

    groups_meta = {}
    for short, history in history_per_group.items():
        total_s = sum(v["spend"] for v in history.values())
        total_h = sum(v["hvu"] for v in history.values())
        recent = sorted(history.keys(), key=lambda x: (int(x.split("/")[0]), int(x.split("/")[1])))
        latest_h = history.get(latest, {}) if latest else {}
        day_s, day_h = latest_h.get("spend", 0), latest_h.get("hvu", 0)

        zero_streak = 0
        for dt in reversed(recent):
            if history[dt]["hvu"] == 0 and history[dt]["spend"] > 0: zero_streak += 1
            else: break
        green_streak = 0
        for dt in reversed(recent):
            if history[dt]["hvu"] > 0 and history[dt]["spend"] / history[dt]["hvu"] <= 3: green_streak += 1
            else: break

        m = meta_per_group[short]
        groups_meta[short] = {
            "full_name": m["full_name"],
            "advertiser": m["advertiser"],
            "landing_type": m["landing_type"],
            "url": url_map.get(short, ""),
            "total_spend": total_s,
            "total_hvu": total_h,
            "active_days": len(history),
            "zero_hvu_streak": zero_streak,
            "green_streak": green_streak,
            "lifetime_cphq": total_s / total_h if total_h > 0 else None,
            "is_stopped": not any(d in history for d in dates_mmdd[-3:]),
            "day_spend": day_s,
            "day_hvu": day_h,
            "day_cphq": round(day_s / day_h, 2) if day_h > 0 else None,
            "all_history": history,
        }

    # daily_totals(全部组合计,排除合计行)
    daily_totals = {}
    for mmdd in dates_mmdd:
        ts = th = 0
        for short, h in history_per_group.items():
            v = h.get(mmdd, {})
            ts += v.get("spend", 0); th += v.get("hvu", 0)
        daily_totals[mmdd] = {"spend": ts, "hvu": th, "cphq": ts / th if th > 0 else None}

    # type_cphq
    type_daily = {"article": {}, "scene": {}, "product": {}}
    for mmdd in dates_mmdd:
        for tp in type_daily: type_daily[tp][mmdd] = {"spend": 0, "hvu": 0}
        for short, h in history_per_group.items():
            tp = groups_meta[short]["landing_type"]
            v = h.get(mmdd, {})
            type_daily[tp][mmdd]["spend"] += v.get("spend", 0)
            type_daily[tp][mmdd]["hvu"] += v.get("hvu", 0)
    type_cphq = {tp: [type_daily[tp][d]["spend"] / type_daily[tp][d]["hvu"] if type_daily[tp][d]["hvu"] > 0 else None for d in dates_mmdd] for tp in type_daily}

    # advertiser_M_D
    adv_latest = {}
    if latest:
        for short, m in groups_meta.items():
            adv = m["advertiser"]
            h = m["all_history"].get(latest, {})
            s, hv = h.get("spend", 0), h.get("hvu", 0)
            if adv not in adv_latest: adv_latest[adv] = {"spend": 0, "hvu": 0, "groups": 0}
            if s > 0 or hv > 0:
                adv_latest[adv]["spend"] += s
                adv_latest[adv]["hvu"] += hv
                adv_latest[adv]["groups"] += 1
    adv_key = None
    if latest:
        parts = latest.split("/")
        adv_key = f"advertiser_{parts[0]}_{parts[1]}"

    out = {"dates": dates_mmdd, "daily_totals": daily_totals, "type_cphq": type_cphq, "groups_meta": groups_meta}
    if adv_key: out[adv_key] = adv_latest

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return dates_mmdd, latest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dates", nargs="+", help="ISO YYYY-MM-DD list")
    p.add_argument("--no-db", action="store_true", help="skip DB inject")
    p.add_argument("--no-json", action="store_true", help="skip dashboard_data.json rebuild")
    args = p.parse_args()

    rows = load_daily()
    print(f"daily_long.csv 行数: {len(rows)}")

    if not args.no_db:
        existing = existing_db_dates()
        if args.dates:
            target = set(args.dates)
        else:
            all_in_csv = set(r["date"] for r in rows)
            target = all_in_csv - existing
        print(f"DB 现有 {len(existing)} 日期 · 本次注入 {len(target)} 日期: {sorted(target)}")
        if target:
            n = inject_to_db(rows, target)
            print(f"  注入 {n} group-days")

    if not args.no_json:
        dates_mmdd, latest = rebuild_dashboard_json(rows)
        print(f"dashboard_data.json 重写: {len(dates_mmdd)} 日期 · latest={latest}")

    master = load_group_master()
    if master:
        rebuild_tiered(rows, master)
    else:
        print("跳过 tiered 重算(无 group_master)")


if __name__ == "__main__":
    main()
