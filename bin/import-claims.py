#!/usr/bin/env python3
"""导入 crave-AI claim 卡片到 z-jb.com knowledge_entries 表"""

import json, glob, urllib.request, sys
from datetime import datetime

# 配置
BASE = "https://z-jb.com"
PASSCODE = "crave2026"
CARDS_DIR = sys.argv[1] if len(sys.argv) > 1 else "~/Documents/GitHub/crave-AI/data/cards"

import os
CARDS_DIR = os.path.expanduser(CARDS_DIR)

# 状态映射
STATUS_MAP = {
    "proposed": "hypothesis",
    "validating": "validating",
    "validated": "confirmed",
    "refuted": "falsified",
}

# 类型推断
def infer_type(card):
    meta = card.get("meta", {})
    title = meta.get("title", "").lower()
    claim_side = meta.get("claim_side", "")
    if "技术" in title or "bug" in title or claim_side == "site":
        return "diagnosis"
    if "策略" in title or "roi" in title.lower() or "cphq" in title:
        return "strategy"
    if "断点" in title or "断裂" in title or "死胡同" in title:
        return "flywheel"
    return "strategy"

# 登录拿 cookie
login_data = json.dumps({"passcode": PASSCODE}).encode()
req = urllib.request.Request(f"{BASE}/api/auth", data=login_data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
cookie = resp.headers.get("Set-Cookie", "").split(";")[0]
print(f"登录成功: {cookie[:30]}...")

# 解析所有 claim 卡片
files = glob.glob(os.path.join(CARDS_DIR, "claim-*.json"))
print(f"找到 {len(files)} 个 claim 文件")

imported = 0
for fpath in sorted(files):
    with open(fpath) as f:
        card = json.load(f)

    meta = card.get("meta", {})
    title = meta.get("title", os.path.basename(fpath))
    prop_status = STATUS_MAP.get(meta.get("proposition_status", ""), "hypothesis")
    prop_type = infer_type(card)
    site = "全部"
    signals = card.get("signals", [])
    confidence_signal = next((s for s in signals if s.get("label") == "置信度"), None)

    content = json.dumps({
        "title": title,
        "card_id": meta.get("card_id"),
        "description": meta.get("title"),
        "claim_side": meta.get("claim_side", ""),
        "proposed_date": meta.get("proposed_date", ""),
        "confidence": confidence_signal.get("value", "") if confidence_signal else "",
    }, ensure_ascii=False)

    # 写入 knowledge_entries（通过直接 SQL 不行，用现有 API 不支持 POST）
    # 所以我们用 wrangler d1 execute 的方式，先生成 SQL
    sql = f"INSERT INTO knowledge_entries (type, content, status, source, created_at) VALUES ('{prop_type}', '{content.replace(chr(39), chr(39)+chr(39))}', '{prop_status}', 'crave-ai-import', '{datetime.now().isoformat()}');"
    print(f"  {meta.get('card_id','?'):40s} → {prop_type:12s} | {prop_status}")
    imported += 1

    # 写到临时 SQL 文件
    with open("/tmp/import_claims.sql", "a") as sf:
        sf.write(sql + "\n")

print(f"\n共 {imported} 条。SQL 已写入 /tmp/import_claims.sql")
print("执行: cd ~/Documents/GitHub/multisite-platform && npx wrangler d1 execute multisite-db --remote --file /tmp/import_claims.sql")
