"""
Ingest conversion data from 承接端分析 markdown files.
Extracts structured fields using regex (default) or Claude API (--mode api).

Usage:
    python3 renderer/ingest_conversion.py
    python3 renderer/ingest_conversion.py --file specific_file.md
    python3 renderer/ingest_conversion.py --mode api
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCAN_DIR = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/crave ai/3_执行层-人工维护/单平台分析/Facebook/承接端分析-高质量用户"
OUTPUT_FILE = Path.home() / "Documents/GitHub/crave-AI/data/conversion_daily.json"
CONCLUSIONS_FILE = Path.home() / "Documents/GitHub/crave-AI/data/conclusions_pending.json"

# API 配置
API_MODEL = "claude-haiku-4-5-20251001"
API_MAX_TOKENS = 500
API_MAX_INPUT_CHARS = 3000


from typing import Optional


def find_latest_md() -> Optional[Path]:
    """找最新的分析 md 文件（按文件名日期或修改时间）"""
    candidates = []
    for f in SCAN_DIR.rglob("*.md"):
        if f.name.startswith("~") or f.name.startswith("."):
            continue
        # 尝试从文件名提取日期
        date_match = re.search(r'(\d{4})[_-]', f.name) or re.search(r'0[45]\d{2}', f.name)
        candidates.append((f.stat().st_mtime, f))

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def extract_fields_structured(content: str, filename: str) -> dict:
    """从吴玲的结构化格式（YAML-like）中提取字段"""
    result = {
        "date": None,
        "hvu_with_intent": None,
        "intent_rate": None,
        "dropoff_point": None,
        "dropoff_reason": None,
        "signal": None,
        "raw_summary": None,
        "source_file": filename,
        "improvement_suggestion": None,
    }

    # date: 2026-05-08
    m = re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if m:
        result["date"] = m.group(1)

    # session: N (from funnel block)
    m = re.search(r'session:\s*(\d+)', content)
    if m:
        result["hvu_with_intent"] = int(m.group(1))

    # product_page_view: N（XX%...）
    m = re.search(r'product_page_view:\s*\d+[^\d]*?(\d+(?:\.\d+)?)\s*%', content)
    if m:
        result["intent_rate"] = float(m.group(1))

    # top_dropoff: first segment before |
    m = re.search(r'top_dropoff:\s*(.+?)(?:\n|$)', content)
    if m:
        first_item = m.group(1).split("|")[0].strip()
        result["dropoff_point"] = first_item

    # dropoff_reason: collect all 【P0】 items
    p0_items = re.findall(r'【[^】]*P0[^】]*】\s*(.+?)(?:\n|$)', content)
    if p0_items:
        result["dropoff_reason"] = " | ".join(item.strip() for item in p0_items)
        result["signal"] = "⚠️ P0技术阻断：" + p0_items[0].strip()
    else:
        # fallback: first dropoff_reason item
        m = re.search(r'dropoff_reason:\s*\n\s*\d+\.\s*(.+?)(?:\n|$)', content)
        if m:
            result["dropoff_reason"] = m.group(1).strip()

    # raw_summary from funnel block
    funnel_match = re.search(r'session:\s*(\d+)', content)
    product_match = re.search(r'product_page_view:\s*(\d+)', content)
    payment_match = re.search(r'payment_complete:\s*(\d+)', content)
    if funnel_match and product_match and payment_match:
        s = int(funnel_match.group(1))
        p = int(product_match.group(1))
        pay = int(payment_match.group(1))
        pct = round(p / s * 100) if s > 0 else 0
        result["raw_summary"] = f"{s} session/{p}浏览商品页({pct}%)/0加购/{pay}支付。{result['dropoff_point'] or ''}"

    # improvement_suggestion: from 研发需求状态速查 P0 row, or 建议优化 first match
    m = re.search(r'建议新增-P0[^|]*\|\s*(.+?)\s*\|', content)
    if m:
        result["improvement_suggestion"] = m.group(1).strip()
    else:
        m = re.search(r'建议优化:\s*(.+?)(?:\n|$)', content)
        if m:
            result["improvement_suggestion"] = m.group(1).strip()

    return result


def extract_fields(content: str, filename: str) -> dict:
    """用正则从自由文本中提取结构化字段"""
    result = {
        "date": None,
        "hvu_with_intent": None,
        "intent_rate": None,
        "dropoff_point": None,
        "dropoff_reason": None,
        "signal": None,
        "raw_summary": None,
        "source_file": filename,
    }

    # 提取日期
    date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', content)
    if date_match:
        result["date"] = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    else:
        # 从文件名提取
        fn_date = re.search(r'(\d{2})(\d{2})', filename)
        if fn_date:
            result["date"] = f"2026-{fn_date.group(1)}-{fn_date.group(2)}"

    # 提取有购买意向的用户数
    # 模式1: "共XX个session" / "总用户数 | XX个"
    intent_match = re.search(r'共(\d+)个(?:session|用户)', content)
    if not intent_match:
        intent_match = re.search(r'总用户数[^\d]*(\d+)', content)
    if intent_match:
        result["hvu_with_intent"] = int(intent_match.group(1))

    # 提取意向率
    # 模式: "XX%" 在"意向"/"转化"/"购买"附近
    rate_match = re.search(r'(?:意向|转化|购买|完成支付)[^\d]*(\d+(?:\.\d+)?)\s*%', content)
    if not rate_match:
        # 模式2: 非真实用户占比 → 反推真实意向率
        fake_match = re.search(r'(?:非真实|无效)[^\d]*(?:约|共)?(\d+)个[^\d]*(\d+)%', content)
        if fake_match:
            fake_pct = int(fake_match.group(2))
            result["intent_rate"] = 100 - fake_pct
    else:
        result["intent_rate"] = float(rate_match.group(1))

    # 提取卡点
    # 找"原因"/"问题"/"卡点"后面的第一个描述
    dropoff_patterns = [
        r'原因\d[：:]\s*(.+?)(?:\n|$)',
        r'核心(?:原因|问题)[^\n]*\n+[#\s]*(?:原因|问题)?\d?[：:.、]\s*(.+?)(?:\n|$)',
        r'为什么没买[^\n]*\n+[^\n]*(\S.+?)(?:\n|$)',
    ]
    dropoff_reasons = []
    for pat in dropoff_patterns:
        matches = re.findall(pat, content)
        dropoff_reasons.extend(matches)

    if dropoff_reasons:
        result["dropoff_point"] = dropoff_reasons[0].strip()
        if len(dropoff_reasons) > 1:
            result["dropoff_reason"] = " | ".join(r.strip() for r in dropoff_reasons[:5])
        else:
            result["dropoff_reason"] = dropoff_reasons[0].strip()

    # 提取异常信号
    signal_patterns = [
        r'(?:异常|警告|注意|⚠️)[：:]\s*(.+?)(?:\n|$)',
        r'非真实用户[^\d]*(?:约|共)?(\d+)个[^）\n]*',
        r'(\d+)%[^\n]*(?:非真实|无效|机器人)',
    ]
    for pat in signal_patterns:
        sig_match = re.search(pat, content)
        if sig_match:
            result["signal"] = sig_match.group(0).strip()
            break

    # 生成摘要（取第一段有意义的描述）
    # 找"数据来源"或第一个 > 引用块
    summary_match = re.search(r'>\s*数据来源[：:]\s*(.+?)(?:\n|$)', content)
    if summary_match:
        result["raw_summary"] = summary_match.group(1).strip()
    else:
        # 取前200字去掉标题
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#') and not l.startswith('---') and not l.startswith('>')]
        if lines:
            result["raw_summary"] = lines[0][:150]

    # 承接层建议（regex模式：基于卡点关键词生成简单建议）
    suggestion_map = {
        "选择困难": "产品列表页增加横向对比表，突出推荐款",
        "对比": "产品列表页增加横向对比表，突出推荐款",
        "转化链路断裂": "文章/场景底部增加场景化产品推荐卡片",
        "场景": "产品详情页增加场景标签，标注适用场景",
        "代入感": "产品视频增加第一人称视角或使用场景画面",
        "想象不出": "产品视频增加第一人称视角或使用场景画面",
        "注册": "支持游客快速结算，注册嵌入结算流程",
        "登录": "支持游客快速结算，Apple/Google一键登录前置",
        "文案": "产品文案从功能描述改为体验描述（你将获得）",
    }
    result["improvement_suggestion"] = None
    if result["dropoff_point"]:
        for keyword, suggestion in suggestion_map.items():
            if keyword in result["dropoff_point"]:
                result["improvement_suggestion"] = suggestion
                break
        if not result["improvement_suggestion"]:
            result["improvement_suggestion"] = f"排查并优化：{result['dropoff_point'][:30]}"

    return result


def extract_fields_api(content: str, filename: str) -> dict:
    """用 Claude API 从自由文本中提取结构化字段 + 承接层建议"""
    import anthropic

    content_truncated = content[:API_MAX_INPUT_CHARS]

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=API_MODEL,
        max_tokens=API_MAX_TOKENS,
        system="你是数据提取助手。从以下运营分析文档里提取结构化字段。无法确定的字段填 null，不要猜测。同时根据 dropoff_point 和 dropoff_reason，给出1条具体的承接层页面修改建议。要求：直接说改什么，不说废话。只输出JSON，不要其他文字。",
        messages=[{
            "role": "user",
            "content": f"""从以下文档提取字段：

{content_truncated}

输出格式（严格JSON）：
{{
  "date": "YYYY-MM-DD 或 null",
  "hvu_with_intent": 数字或null,
  "intent_rate": 百分比数字或null,
  "dropoff_point": "主要卡点一句话描述或null",
  "dropoff_reason": "详细原因或null",
  "signal": "异常信号或null",
  "raw_summary": "原文核心内容一句话概括",
  "improvement_suggestion": "基于卡点的具体承接层修改建议，1-2句话，直接可执行"
}}"""
        }]
    )

    try:
        result = json.loads(response.content[0].text)
        result["source_file"] = filename
        return result
    except (json.JSONDecodeError, IndexError):
        print(f"  WARNING: API 返回非 JSON，回退到 regex 模式")
        return extract_fields(content, filename)


def load_existing() -> dict:
    """加载已有的 conversion_daily.json"""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            return json.load(f)
    return {"entries": []}


def check_trend(entries: list) -> Optional[dict]:
    """检查连续3天 intent_rate 是否有>20%变化"""
    recent = [e for e in entries if e.get("intent_rate") is not None][-3:]
    if len(recent) < 3:
        return None

    rates = [e["intent_rate"] for e in recent]
    # 检查趋势
    if max(rates) - min(rates) > 20:
        return {
            "type": "转化层异常",
            "status": "需要关注",
            "data": {
                "dates": [e["date"] for e in recent],
                "intent_rates": rates,
                "change": max(rates) - min(rates),
                "direction": "上升" if rates[-1] > rates[0] else "下降",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="指定文件路径（不指定则自动找最新）")
    parser.add_argument("--mode", choices=["regex", "api"], default="regex", help="提取模式：regex（默认）或 api（需要 ANTHROPIC_API_KEY）")
    args = parser.parse_args()

    if args.file:
        target = Path(args.file)
    else:
        target = find_latest_md()

    if not target or not target.exists():
        print("ERROR: 未找到可分析的 md 文件")
        print(f"  扫描目录: {SCAN_DIR}")
        sys.exit(1)

    print(f"[转化层数据接入] 解析: {target.name} (mode={args.mode})")
    content = target.read_text(encoding="utf-8")

    if args.mode == "api":
        fields = extract_fields_api(content, target.name)
    else:
        # 两套 regex 都跑，取字段更多的那套
        fields_structured = extract_fields_structured(content, target.name)
        fields_freeform = extract_fields(content, target.name)

        count_s = sum(1 for k, v in fields_structured.items() if v is not None and k != "source_file")
        count_f = sum(1 for k, v in fields_freeform.items() if v is not None and k != "source_file")

        if count_s >= count_f:
            fields = fields_structured
            print(f"  [模式] 结构化解析命中 ({count_s} 字段 vs 自由文本 {count_f})")
        else:
            fields = fields_freeform
            print(f"  [模式] 自由文本解析命中 ({count_f} 字段 vs 结构化 {count_s})")

    print(f"  日期: {fields['date']}")
    print(f"  有意向用户: {fields['hvu_with_intent']}")
    print(f"  意向率: {fields['intent_rate']}%") if fields['intent_rate'] else print(f"  意向率: null")
    print(f"  主要卡点: {fields['dropoff_point']}")
    print(f"  异常信号: {fields['signal']}")
    print(f"  摘要: {fields['raw_summary'][:80]}...")
    print()

    # 追加到 conversion_daily.json
    data = load_existing()

    # 去重（同日期不重复追加）
    existing_dates = {e.get("date") for e in data["entries"]}
    if fields["date"] not in existing_dates:
        data["entries"].append(fields)
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 已追加到 {OUTPUT_FILE}")
    else:
        print(f"  ⏭️ {fields['date']} 已存在，跳过")

    # 检查趋势异常
    trend = check_trend(data["entries"])
    if trend:
        print(f"  ⚠️ 转化层异常: intent_rate 变化 {trend['data']['change']:.0f}%")
        # 追加到 conclusions_pending.json
        if CONCLUSIONS_FILE.exists():
            with open(CONCLUSIONS_FILE) as f:
                conclusions = json.load(f)
        else:
            conclusions = {"conclusions": []}

        # 去重
        existing_types = [c["type"] for c in conclusions["conclusions"]]
        if "转化层异常" not in existing_types:
            conclusions["conclusions"].append(trend)
            with open(CONCLUSIONS_FILE, "w") as f:
                json.dump(conclusions, f, ensure_ascii=False, indent=2)
            print(f"  ✅ 转化层提案已写入 conclusions_pending.json")


if __name__ == "__main__":
    main()
