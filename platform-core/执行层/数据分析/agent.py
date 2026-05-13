"""platform-core/执行层/数据分析/agent.py

数据分析 agent · 第一个按 IO 合约严格实现的 agent

职责:
  · 投手视角 — 只看 owner=<当前投手> 的组
  · ZJB 视角 — 可跨投手聚合(by_owner 拆解)
  · 读 L1 规则:group_master.json(组归属)+ thresholds.json(CPHQ 灯色)
  · 输入走合约一七槽位清洗
  · 输出走合约二 rule_source + 合约三 target_role 校验

数据来源:
  · MVP 接受外部传入的 mock/ZJB 推送的 HVU-xlsx-summary(合约零:不主动触发 AdClaw)
  · 真实接入 P1(吴玲日报 / 桌面 xlsx ingest)

输出规范:
  · target_role=[投手] 当投手视角 · 语气:陈述句+可执行判断
  · target_role=[ZJB排查,Claude] 当 ZJB 视角 · 语气:提问句式(合约三 L128)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# 引入中间件 + _base
PLATFORM_CORE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM_CORE / "中间件"))
sys.path.insert(0, str(PLATFORM_CORE / "执行层"))
sys.path.insert(0, str(PLATFORM_CORE / "规则"))

from _base import AgentInput, AgentResult, AgentStatus  # noqa: E402
from 七槽位清洗 import clean as clean_7slot  # noqa: E402
from target_role校验 import validate as validate_role, TargetRole  # noqa: E402
from 规则指针校验 import validate as validate_rule  # noqa: E402


name = "数据分析"

RULES_DIR = PLATFORM_CORE / "规则"
DATA_DIR = PLATFORM_CORE / "数据底盘"
GROUP_MASTER_RULE = "platform-core/规则/group_master.json"
THRESHOLDS_RULE = "platform-core/规则/thresholds.json"
AUTO_STRATEGY_RULE = "platform-core/规则/auto_strategy_rules.json"


# ─── 读真 CSV 底盘 ─────────────────────
def _load_daily_long_csv(owner_filter: str | None = None) -> list[dict]:
    """从 数据底盘/ad_history/current_account_daily_long.csv 读真实数据"""
    import csv
    csv_path = DATA_DIR / "ad_history" / "current_account_daily_long.csv"
    if not csv_path.is_file():
        return []
    rows = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
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


# ─── CPHQ 灯色分级(读真规则)─────────────
def _classify_cphq(cphq: float, thresholds: dict) -> str:
    """按 thresholds.json#cphq_color 判定灯色"""
    color = thresholds["cphq_color"]
    if cphq <= color["green"]["max"]:
        return "绿灯"
    if cphq <= color["yellow"]["max"]:
        return "黄灯"
    if cphq >= color["red"]["spend_min"]:
        return "橙灯/红灯候选"
    return "橙灯"


# ─── 主 agent 入口 ────────────────────────
def run(inp: AgentInput) -> AgentResult:
    """
    入参:
      inp.site_id — 多站场景路由用
      inp.overrides — L1-L4 合并后的阈值(含 owner_filter 判定投手/ZJB 视角)
      inp.upstream_output — 可能含 event_payload(事件触发)或 raw_data(直接数据)

    MVP 模拟数据来源:
      优先读 upstream_output["daily_rows"](外部推的清洗数据)
      否则返回 no_data
    """
    t0 = time.time()
    upstream = inp.upstream_output or {}
    overrides = inp.overrides or {}

    # ─── 1. 合约一·七槽位清洗(如果上游给了原始字段)────
    raw_input = upstream.get("raw_input")
    if raw_input:
        cleaned = clean_7slot(raw_input)
        if cleaned.has_unknown_required():
            return AgentResult(
                status=AgentStatus.NO_DATA,
                gap_reason=f"合约一 7 槽位缺必填: {cleaned.missing_required}\n{cleaned.prompt_for_missing()}",
                duration_ms=int((time.time() - t0) * 1000),
                agent_name=name, site_id=inp.site_id,
            )

    # ─── 2. 读 L1 真规则 ─────────────────
    try:
        group_master = json.loads((RULES_DIR / "group_master.json").read_text(encoding="utf-8"))
        thresholds = json.loads((RULES_DIR / "thresholds.json").read_text(encoding="utf-8"))
    except Exception as e:
        return AgentResult(
            status=AgentStatus.EXTERNAL_FAILURE,
            gap_reason=f"L1 规则读取失败: {e}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # ─── 3. 视角判定 ─────────────────────
    # owner_filter: None=ZJB 视角, 具体缩写(HZM/CHJ/HNN)=投手视角
    owner_filter = overrides.get("owner_filter") or upstream.get("owner_filter")
    is_zjb_view = owner_filter is None

    # ─── 4. 组过滤 ─────────────────────
    all_groups = group_master["groups"]
    if is_zjb_view:
        visible_groups = all_groups
    else:
        visible_groups = {
            gid: g for gid, g in all_groups.items()
            if g.get("owner") == owner_filter
        }

    # ─── 5. 数据聚合 ─────────────────────
    # 优先读 upstream 推入的 daily_rows;否则读真 CSV 底盘
    daily_rows = upstream.get("daily_rows")
    if daily_rows is None:
        daily_rows = _load_daily_long_csv(owner_filter)

    by_color: dict[str, list] = {}
    per_group_cphq = {}

    for row in daily_rows:
        gid = str(row.get("group_id", row.get("group", "")))
        # 从 group_master 匹配(兼容 CSV 里 group 字段带名字如"组17 18 Sensual")
        matched_gid = None
        for k, g in visible_groups.items():
            if k == gid or g["name"] in gid or gid in g["name"]:
                matched_gid = k
                break
        if matched_gid is None:
            continue
        cphq = row.get("cphq")
        if cphq is None or cphq == "":
            continue
        cphq = float(cphq)
        color = _classify_cphq(cphq, thresholds)
        entry = {
            "group": visible_groups[matched_gid]["name"],
            "owner": visible_groups[matched_gid]["owner"],
            "cphq": cphq,
            "hvu": row.get("hvu"),
            "spend": row.get("spend"),
            "date": row.get("date"),
            "color": color,
        }
        by_color.setdefault(color, []).append(entry)
        per_group_cphq[matched_gid] = entry

    # ─── 6. 输出结构化结论 ─────────────────
    data = {
        "视角": "ZJB 统筹" if is_zjb_view else f"投手 {owner_filter} 自看",
        "视角说明": (
            "跨投手聚合,按 owner 拆解"
            if is_zjb_view
            else f"只看 {owner_filter} 负责的组,不含他人组"
        ),
        "在册组数": len(visible_groups),
        "本次有日报数据的组": len(per_group_cphq),
        "CPHQ 灯色阈值来源": {
            "rule_file": THRESHOLDS_RULE,
            "version": thresholds["_meta"]["version"],
            "updated": thresholds["_meta"]["updated"],
            "绿": f"≤ ${thresholds['cphq_color']['green']['max']}",
            "黄": f"${thresholds['cphq_color']['yellow']['min']}-${thresholds['cphq_color']['yellow']['max']}",
            "橙": f"≥ ${thresholds['cphq_color']['orange']['min']}",
            "红": f"HVU={thresholds['cphq_color']['red']['hvu']} 且花费≥${thresholds['cphq_color']['red']['spend_min']}",
        },
        "按灯色分类": {k: v for k, v in by_color.items() if v},
    }

    # ZJB 视角补 by_owner 拆解
    if is_zjb_view:
        by_owner = {}
        for entry in per_group_cphq.values():
            by_owner.setdefault(entry["owner"], []).append(entry)
        data["按投手拆解"] = {
            owner: {
                "组数": len(entries),
                "绿灯数": sum(1 for e in entries if e["color"] == "绿灯"),
                "CPHQ均值": round(sum(e["cphq"] for e in entries) / len(entries), 2) if entries else None,
            }
            for owner, entries in by_owner.items()
        }

    # ─── 7. 合约三·target_role + 语气 ─────
    # 投手视角 = 投手(陈述句+可执行),ZJB 视角 = ZJB排查+Claude(提问句式)
    if is_zjb_view:
        roles = ["ZJB排查", "Claude"]
        data["语气提示"] = "ZJB 视角 · 必须用提问句式(合约三 L128),不坚信自己对"
    else:
        roles = ["投手"]
        data["语气提示"] = "投手视角 · 陈述句+可执行判断,不加 next_action"

    role_check = validate_role(roles=roles, conclusion_type="data_insight")
    if not role_check.ok:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"合约三 target_role 校验失败: {role_check.errors}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # ─── 8. 合约二·rule_source 校验 ───────
    rule_src = "platform-core/规则/thresholds.json"  # 本次主规则
    rule_check = validate_rule(
        rule_source=rule_src,
        processing_action=None,  # 数据分析不在 7 处理动作表内,走通用路径
        repo_root=PLATFORM_CORE.parent,  # repo root = multisite-platform/
    )
    # warnings 允许(比如建议双向指针),errors 阻断
    if not rule_check.ok:
        return AgentResult(
            status=AgentStatus.FAILED,
            gap_reason=f"合约二 rule_source 校验失败: {rule_check.errors}",
            duration_ms=int((time.time() - t0) * 1000),
            agent_name=name, site_id=inp.site_id,
        )

    # ─── 9. 写入合约标识 ─────────────────
    data["_io_contract"] = {
        "target_role": roles,
        "rule_source": rule_src,
        "processing_actions_touched": ["group_master_read", "cphq_classify"],
    }

    return AgentResult(
        status=AgentStatus.SUCCESS,
        data=data,
        cost=0.0,
        duration_ms=int((time.time() - t0) * 1000),
        agent_name=name,
        site_id=inp.site_id,
    )
