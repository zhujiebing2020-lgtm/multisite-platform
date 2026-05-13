#!/usr/bin/env python3
"""
Google 日卡自动生成 · 从 goole-HVU-YYYY-MM-DD.json + 广告系列 csv 自动建 daily-YYYY-MM-DD-google.json

用法:
  python3 scripts/gen_google_daily_cards.py
  python3 scripts/gen_google_daily_cards.py --date 2026-05-11
  python3 scripts/gen_google_daily_cards.py --overwrite
"""
from __future__ import annotations
import json, re, argparse, collections, csv
from pathlib import Path
from datetime import datetime, timezone

REPO = Path.home() / "Documents/GitHub/crave-AI"
CARDS = REPO / "data/cards"
GG_VAULT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/crave ai/3_执行层-人工维护/单平台分析/Google"


def find_hvu_files() -> dict[str, Path]:
    files = {}
    for f in GG_VAULT.glob("*HVU*2026*.json"):
        if "_cleaned" in f.name: continue
        m = re.search(r"(2026-\d{2}-\d{2})", f.name)
        if m:
            date = m.group(1)
            if date not in files:
                files[date] = f
    return files


def find_csv_for_date(date: str):
    date_dot = date.replace("-", ".")
    for f in GG_VAULT.rglob(f"广告系列({date_dot}).csv"):
        try:
            with f.open(encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    return {"spend": row.get("费用","").replace("US$","").strip(), "clicks": row.get("点击次数","").strip(), "ctr": row.get("点击率","").strip()}, f.name
        except: continue
    return None, None


def analyze_hvu(path: Path) -> dict:
    d = json.loads(path.read_text())
    sessions = d.get("sessions", [])
    total = len(sessions)
    hq1 = sum(1 for s in sessions if s.get("hq",{}).get("hq1_matched"))
    hq2 = sum(1 for s in sessions if s.get("hq",{}).get("hq2_matched"))
    linked = sum(1 for s in sessions if (s.get("linkedTask") or {}).get("name"))
    countries = collections.Counter(s.get("geo",{}).get("country","?") for s in sessions)
    durations = [s.get("today_duration_sec") or 0 for s in sessions]
    pages = [s.get("today_page_count") or 0 for s in sessions]
    stages = collections.Counter(s.get("today_max_conv_stage") or "?" for s in sessions)
    return {"total": total, "hq1": hq1, "hq2": hq2, "linked": linked, "unlinked": total-linked,
            "countries": dict(countries), "avg_duration": round(sum(durations)/total,1) if total else 0,
            "avg_pages": round(sum(pages)/total,1) if total else 0, "stages": dict(stages)}


def build_card(date, hvu_path, csv_data, csv_file):
    m = analyze_hvu(hvu_path)
    mmdd = f"{int(date.split('-')[1])}/{int(date.split('-')[2])}"
    top_c = " · ".join(f"{c} {n}" for c,n in sorted(m["countries"].items(), key=lambda x:-x[1])[:5])
    signals = [{"label":"渠道","value":"Google Ads(搜索广告) · 广告系列「玩具」","source":hvu_path.name}]
    if csv_data:
        signals.append({"label":f"Google Ads {mmdd} spend","value":f"US${csv_data['spend']}","source":csv_file or ""})
        signals.append({"label":f"Google Ads {mmdd} 点击/CTR","value":f"{csv_data['clicks']} clicks / CTR {csv_data['ctr']}","source":csv_file or ""})
        try:
            sp = float(csv_data["spend"])
            if m["total"]>0: signals.append({"label":f"{mmdd} CPHQ","value":f"${sp/m['total']:.2f}","source":"csv/HVU"})
        except: pass
    else:
        signals.append({"label":f"Google Ads {mmdd} spend","value":"CSV 未出","source":"待导出"})
    signals.extend([
        {"label":f"Google {mmdd} HVU 总数","value":f"{m['total']} 人(关联 {m['linked']} + 未关联 {m['unlinked']})","source":hvu_path.name},
        {"label":f"{mmdd} HQ1/HQ2","value":f"HQ1 {m['hq1']} / HQ2 {m['hq2']}","source":"hq"},
        {"label":f"{mmdd} 国家","value":top_c,"source":"geo.country"},
        {"label":f"{mmdd} 停留/页数","value":f"{m['avg_duration']}s · {m['avg_pages']}页","source":"duration/page_count"},
        {"label":f"{mmdd} 转化阶段","value":" · ".join(f"{k}({v})" for k,v in m["stages"].items()),"source":"max_conv_stage"},
    ])
    return {"meta":{"card_id":f"daily-{date}-google","card_type":"daily_dashboard","channel":"google",
        "title":f"Google · {mmdd} HVU 快照","schema_version":"v1","last_updated":date,"data_date":date,
        "target_role":["ZJB排查","Claude内部"],"rule_source":"scripts/gen_google_daily_cards.py"},
        "signals":signals,"trigger_conditions":[{"condition":"HVU JSON","met":True,"evidence":hvu_path.name}],
        "skeptic_conditions":[],"actions":[]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    files = find_hvu_files()
    if args.date:
        files = {args.date: files[args.date]} if args.date in files else {}
    built = 0
    for date in sorted(files):
        card_path = CARDS / f"daily-{date}-google.json"
        if card_path.exists() and not args.overwrite:
            print(f"⏭ {date} 已有 · 跳过")
            continue
        csv_data, csv_file = find_csv_for_date(date)
        card = build_card(date, files[date], csv_data, csv_file)
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
        print(f"✅ {date} · HVU {analyze_hvu(files[date])['total']} · spend={'有' if csv_data else '无'}")
        built += 1
    print(f"\n完成: {built} 张新卡")


if __name__ == "__main__":
    main()
