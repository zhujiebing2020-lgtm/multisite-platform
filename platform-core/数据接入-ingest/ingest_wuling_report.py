#!/usr/bin/env python3
"""
吴玲 md 报告 → intake.json + 联动 claim/dev-req 卡

输入: vault/3_执行层-人工维护/单平台分析/Facebook/承接端分析-高质量用户/YYYY-MM-DDD-PromptA-综合分析报告.md
输出:
  - data/intake/accept_daily_YYYY-MM-DD.json (覆盖)
  - 已存在的 claim 卡 evidence_chain 追加 path2 条目
  - 已存在的 dev-req 卡 dev_status: aligned → in_progress (符合条件时)

权限分级 (feedback_dev_status_autotrans_authority):
  - Claude 只能改 aligned → in_progress
  - shipped/verified 必须 ZJB 手动改 + 签字
  - 每次变更必须留 state_history

用法:
  python3 scripts/ingest_wuling_report.py --report 0512-PromptA-综合分析报告.md
  python3 scripts/ingest_wuling_report.py --report 0512-PromptA-综合分析报告.md --dry-run
"""
from __future__ import annotations
import json, re, argparse
from pathlib import Path
from datetime import datetime, timezone

REPO = Path.home() / "Documents/GitHub/crave-AI"
INTAKE = REPO / "data/intake"
CARDS = REPO / "data/cards"
VAULT_ACCEPT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/crave ai/3_执行层-人工维护/单平台分析/Facebook/承接端分析-高质量用户"

# 关键词 → claim_id 映射(从 data/cards/claim-*.json 反查)
def load_claim_keywords():
    """从已有 claim 卡里抽 title + signals 作为关键词词袋."""
    claims = {}
    # 业务同义词扩展(中→英)
    SYNONYMS = {
        "结算页": ["order", "checkout", "结算", "支付页"],
        "支付": ["payment", "checkout", "buy now"],
        "buy now": ["立即购买", "支付", "checkout"],
        "scene room": ["场景房间", "scene", "room"],
        "视频": ["video", "播放", "观看"],
        "google": ["谷歌", "google ads"],
        "结算": ["order", "checkout"],
    }
    for f in CARDS.glob("claim-*.json"):
        d = json.loads(f.read_text())
        cid = d["meta"]["card_id"]
        title = d["meta"].get("title", "")
        keywords = set()
        # card_id 自身的关键词
        for kw in re.findall(r"[a-z]+", cid.lower()):
            if len(kw) >= 3:
                keywords.add(kw)
        # 标题里的关键词
        for kw in re.findall(r"[一-鿿]{2,}|[A-Za-z]+", title):
            if len(kw) >= 2:
                keywords.add(kw.lower())
        # signals 第一条
        if d.get("signals"):
            v = str(d["signals"][0].get("value", ""))
            for kw in re.findall(r"[一-鿿]{2,}|[A-Za-z]+", v):
                if len(kw) >= 2:
                    keywords.add(kw.lower())
        # 同义词扩展
        expanded = set(keywords)
        for kw in keywords:
            if kw in SYNONYMS:
                expanded.update(SYNONYMS[kw])
        claims[cid] = {"title": title, "keywords": expanded, "path": f}
    return claims


def load_dev_reqs():
    """已有 dev-req 卡(by linked_claim 索引)."""
    reqs = {}
    for f in CARDS.glob("dev-req-*.json"):
        d = json.loads(f.read_text())
        lc = d["meta"].get("linked_claim")
        if lc:
            reqs.setdefault(lc, []).append({"path": f, "data": d})
    return reqs


def match_claim(text, claims):
    """文本 → 最匹配的 claim_id(关键词重合度最高)."""
    text_l = text.lower()
    best, best_score = None, 0
    for cid, info in claims.items():
        score = sum(1 for kw in info["keywords"] if kw in text_l)
        if score > best_score:
            best, best_score = cid, score
    return best if best_score >= 2 else None  # 至少 2 个关键词命中


def parse_report(md_text, fname=""):
    """解析 md 报告 · 返回结构化字段."""
    # 优先从文件名提取(YYYY-MM-DD 或 MMDD)
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", fname)
    if m:
        date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m = re.search(r"^(\d{4})", fname)  # MMDD 短格式
        if m:
            mmdd = m.group(1)
            date_str = f"2026-{mmdd[:2]}-{mmdd[2:]}"
        else:
            # fallback 从标题
            m = re.search(r"# (\d{2})(\d{2})\s*用户行为", md_text)
            if m:
                date_str = f"2026-{m.group(1)}-{m.group(2)}"
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")

    out = {"date": date_str, "raw_sections": {}}

    # 漏斗(第一部分 4)
    funnel_m = re.search(r"## 4\. 转化漏斗\n\n(.*?)\n\n##", md_text, re.DOTALL)
    if funnel_m:
        out["raw_sections"]["funnel"] = funnel_m.group(1)

    # 商品详情页(第二部分三)
    pp_m = re.search(r"## 三、商品详情页专项分析.*?\n\n(.*?)(?=\n## 四|\n# 第三)", md_text, re.DOTALL)
    if pp_m:
        out["raw_sections"]["product_page"] = pp_m.group(1)

    # Bug 跟踪(第二部分四)
    bug_m = re.search(r"## 四、🔴 Bug问题跟踪\n\n(.*?)(?=\n# 第三)", md_text, re.DOTALL)
    if bug_m:
        out["raw_sections"]["bugs"] = bug_m.group(1)

    # 需人工确认清单
    confirm_m = re.search(r"## 需人工确认清单\n\n(.*?)(?=\n## |\Z)", md_text, re.DOTALL)
    if confirm_m:
        out["raw_sections"]["need_confirm"] = confirm_m.group(1)

    # Bug 跟踪提醒
    bug_alert_m = re.search(r"## 🔴 Bug跟踪提醒\n\n(.*?)(?=\n---|\Z)", md_text, re.DOTALL)
    if bug_alert_m:
        out["raw_sections"]["bug_alert"] = bug_alert_m.group(1)

    return out


def extract_must_fix(parsed, claims):
    """从 bugs/need_confirm 抽 must_fix_today."""
    items = []
    # Bug 跟踪提醒 → P0 must_fix
    if parsed["raw_sections"].get("bug_alert"):
        text = parsed["raw_sections"]["bug_alert"]
        for line in text.split("\n"):
            if "|" in line and not line.startswith("| Bug") and not line.startswith("|---"):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 4 and cols[0]:
                    title = cols[0]
                    linked = match_claim(title, claims)
                    items.append({
                        "title": title,
                        "priority": "P0",
                        "impact": cols[3] if len(cols) > 3 else "",
                        "blocked_by": cols[2] if len(cols) > 2 else "",
                        "linked_claim": linked,
                        "source_section": "bug_alert"
                    })
    # 需人工确认 → P1 must_fix
    if parsed["raw_sections"].get("need_confirm"):
        text = parsed["raw_sections"]["need_confirm"]
        for line in text.split("\n"):
            if "|" in line and not line.startswith("| 文件") and not line.startswith("|---"):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 4 and cols[1]:
                    title = f"{cols[1]} · {cols[3]}"
                    linked = match_claim(cols[3] if len(cols)>3 else "" + " " + (cols[4] if len(cols)>4 else ""), claims)
                    items.append({
                        "title": title,
                        "priority": "P1",
                        "impact": cols[3] if len(cols) > 3 else "",
                        "proposed_fix": cols[4] if len(cols) > 4 else "",
                        "linked_claim": linked,
                        "source_section": "need_confirm"
                    })
    return items


def auto_state_transition(fixed_today_claims, dev_reqs_by_claim, dry_run, report_date, report_name):
    """把对应 dev-req 卡的 aligned → in_progress(权限分级 · 不能跨级).
    只处理 fixed_today 里提到的 claim,不处理 must_fix_today(那是待修列表,不是开始修的信号)."""
    changes = []
    for claim_id in fixed_today_claims:
        for req in dev_reqs_by_claim.get(claim_id, []):
            data = req["data"]
            cur = data["meta"].get("dev_status", "draft")
            if cur != "aligned":
                continue  # Claude 只能改 aligned → in_progress
            data["meta"]["dev_status"] = "in_progress"
            data["meta"]["started_at"] = report_date
            # state_history
            hist = data["meta"].get("state_history", [])
            hist.append({
                "from": "aligned", "to": "in_progress",
                "by": "Claude", "date": report_date,
                "evidence_ref": f"吴玲 {report_name} fixed_today · claim={claim_id}"
            })
            data["meta"]["state_history"] = hist
            if not dry_run:
                req["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2))
            changes.append((req["path"].name, "aligned→in_progress"))
    return changes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True, help="md 报告文件名(在 vault 承接端目录下)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--auto-stub-claim", action="store_true", default=True, help="未匹配的 must_fix 自动立 Path1 推断卡(proposed 状态)")
    args = p.parse_args()

    rp = VAULT_ACCEPT / args.report
    if not rp.exists():
        # 也支持绝对路径
        rp = Path(args.report)
        if not rp.exists():
            print(f"❌ 找不到 {args.report}")
            return

    md = rp.read_text(encoding="utf-8")
    parsed = parse_report(md, args.report)
    print(f"报告日期: {parsed['date']}")
    print(f"识别区块: {list(parsed['raw_sections'].keys())}")

    claims = load_claim_keywords()
    print(f"已有 claim 卡: {len(claims)}")

    must_fix = extract_must_fix(parsed, claims)
    print(f"\n=== must_fix_today {len(must_fix)} 项 ===")
    for x in must_fix:
        print(f"  [{x['priority']}] {x['title'][:60]}")
        print(f"      linked_claim: {x.get('linked_claim') or '⚠ 未匹配(B方案: 立 Path1 推断卡)'}")

    # 构建 intake.json
    # 增量规则:
    #   - modules (长期档案): 不覆盖 · 从最近一份 intake 继承 · 报告里提到的 module 追加 history · 未提到的标"5/12 未更新"
    #   - must_fix_today / fixed_today (当日工作): 覆盖 · 用本次报告解析结果
    #   - overall_health / health_note: 覆盖
    out_path = INTAKE / f"accept_daily_{parsed['date']}.json"

    # 找最近一份 intake 作为 modules 基础
    existing_intakes = sorted(INTAKE.glob("accept_daily_*.json"), reverse=True)
    base_modules = []
    for p in existing_intakes:
        if p.name == out_path.name: continue  # 跳过同日
        try:
            base = json.loads(p.read_text())
            base_modules = base.get("modules", [])
            print(f"  modules 继承自: {p.name}({len(base_modules)} 张)")
            break
        except: continue

    # modules 加"本次未更新"标记
    for m in base_modules:
        h = m.get("history", [])
        # 这次报告里没提到该 module · 保留状态但加一条说明
        h.append({
            "date": parsed["date"],
            "event": f"{parsed['date']} 报告未提及 · 状态保留",
            "detail": "ingest_wuling_report 增量模式 · 不覆盖 modules · 等吴玲明确状态变更"
        })
        m["history"] = h

    intake = {
        "date": parsed["date"],
        "submitted_by": "吴玲",
        "source_report": args.report,
        "_note": f"由 ingest_wuling_report.py 从 md 报告自动解析 · modules 继承自最近 intake · must_fix/fixed 来自本次报告",
        "overall_health": "yellow",
        "health_note": "三天结算页 100% 流失持续",
        "must_fix_today": must_fix,
        "fixed_today": [],
        "modules": base_modules,  # 长期档案 · 增量保留
    }
    if args.dry_run:
        print(f"\n[dry-run] 会写入 {out_path}")
    else:
        out_path.write_text(json.dumps(intake, ensure_ascii=False, indent=2))
        print(f"\n✅ 写入 {out_path.name}")

    # evidence_chain 反向追加
    print(f"\n=== claim evidence_chain 追加 ===")
    matched_claims = {x["linked_claim"] for x in must_fix if x.get("linked_claim")}
    for cid in matched_claims:
        cpath = claims[cid]["path"]
        data = json.loads(cpath.read_text())
        ec = data["meta"].get("evidence_chain", [])
        # 检查是否已有同日 path2 记录
        already = any(e.get("date") == parsed["date"] and e.get("by") == "吴玲" for e in ec)
        if already:
            print(f"  ⏭ {cid} 已有 {parsed['date']} 吴玲记录 · 跳过")
            continue
        ec.append({
            "path": 2, "by": "吴玲", "date": parsed["date"],
            "ref": f"vault/.../{args.report}",
            "action": "re-confirm",
            "tech_detail": f"吴玲 {parsed['date']} 日报再次提及"
        })
        data["meta"]["evidence_chain"] = ec
        if not args.dry_run:
            cpath.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"  ✅ {cid} · +1 path2 条目")

    # dev_status 升级:只对 fixed_today 里的 claim 升级,must_fix_today 不升级
    # (报告里当前没 fixed_today 节,这里留 TODO · 未来吴玲报告加"今日已修"区块时再匹配)
    fixed_claims = set()  # TODO: 从 parsed["raw_sections"]["fixed_today"] 匹配
    dev_reqs = load_dev_reqs()
    changes = auto_state_transition(fixed_claims, dev_reqs, args.dry_run, parsed["date"], args.report)
    if fixed_claims:
        print(f"\n=== dev_status 自动升级(仅 fixed_today 触发) {len(changes)} 项 ===")
        for name, change in changes:
            print(f"  {name}: {change}")
    else:
        print(f"\n=== dev_status 未升级(报告无 fixed_today 区块 · 符合预期)===")

    # 未匹配的 must_fix → B 方案 · 自动立 Path1 推断卡(proposed 状态)
    unmatched = [x for x in must_fix if not x.get("linked_claim")]
    if unmatched and args.auto_stub_claim:
        print(f"\n=== 未匹配的 must_fix · 自动立 Path1 推断卡(B 方案) {len(unmatched)} 项 ===")
        for x in unmatched:
            slug = re.sub(r"[^\w]+", "-", x["title"].lower())[:40].strip("-")
            stub_id = f"claim-stub-{parsed['date']}-{slug}"
            stub_path = CARDS / f"{stub_id}.json"
            if stub_path.exists():
                print(f"  ⏭ {stub_id} 已存在")
                continue
            stub = {
                "meta": {
                    "card_id": stub_id, "card_type": "claim", "channel": "all",
                    "title": f"[Claude推断 · 待ZJB审] {x['title'][:80]}",
                    "schema_version": "v1", "last_updated": parsed["date"],
                    "target_role": ["ZJB排查"], "rule_source": "ingest_wuling_report.py · 自动 stub",
                    "proposition_status": "proposed", "claim_side": "site",
                    "diagnosis_path": "path1_claude_inference",
                    "evidence_chain": [{"path": 1, "by": "Claude", "date": parsed["date"], "ref": f"vault/.../{args.report}", "action": "auto_stub", "tech_detail": x.get("impact","")[:200]}]
                },
                "signals": [{"label": "原始描述", "value": x["title"], "source": args.report}],
                "trigger_conditions": [], "skeptic_conditions": [], "rollback_conditions": [],
                "actions": [{"step": 1, "name": "等 ZJB 审核 · 决定是否升级为 validating", "execution_status": "待审"}]
            }
            if not args.dry_run:
                stub_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2))
            print(f"  ✅ 立卡: {stub_id}")
    elif unmatched:
        print(f"\n=== 未匹配的 must_fix(--auto-stub-claim 关闭 · 不自动立卡)===")
        for x in unmatched:
            print(f"  ⚠ {x['title'][:60]}")


if __name__ == "__main__":
    main()
