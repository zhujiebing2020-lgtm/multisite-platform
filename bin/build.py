"""bin/build.py
读 data/cards/多站群-*.json → 生成 view/{投手}.html + view/index.html

零依赖(纯标准库 + f-string)
打开 view/index.html 即可看(本地双击 / GitHub Pages 自动渲染)
"""
import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CARDS_DIR = REPO / "data" / "cards"
VIEW_DIR = REPO / "view"


HTML_HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 1100px; margin: 20px auto; padding: 0 20px; color: #222; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
  h2 {{ margin-top: 30px; color: #444; }}
  .nav {{ background: #f5f5f5; padding: 10px; border-radius: 6px; margin-bottom: 20px; }}
  .nav a {{ margin-right: 16px; color: #06c; text-decoration: none; }}
  .nav a:hover {{ text-decoration: underline; }}
  .card {{ border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin: 12px 0; }}
  .card-header {{ font-weight: bold; color: #333; margin-bottom: 8px; }}
  .status-success {{ color: #2a7; }}
  .status-failed {{ color: #d44; }}
  .status-no_data {{ color: #888; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  th {{ background: #f5f5f5; }}
  .绿灯 {{ color: #2a7; font-weight: bold; }}
  .黄灯 {{ color: #c80; font-weight: bold; }}
  .橙灯, .橙灯红灯候选 {{ color: #d44; font-weight: bold; }}
  pre {{ background: #f9f9f9; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
  .request-btn {{ display: inline-block; padding: 8px 14px; background: #06c; color: #fff;
                  border-radius: 4px; text-decoration: none; margin: 4px; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;
             color: #888; font-size: 12px; }}
</style>
</head>
<body>
"""


def html_nav(current: str, all_owners: list[str]) -> str:
    links = [f'<a href="index.html">总览</a>']
    for owner in all_owners:
        marker = "★ " if owner == current else ""
        links.append(f'<a href="{owner}.html">{marker}{owner}</a>')
    return f'<div class="nav">{" | ".join(links)}</div>'


def render_agent_card(entry: dict) -> str:
    ts = entry.get("ts", 0)
    ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"
    status = entry.get("status", "?")
    status_class = f"status-{status}"
    data = entry.get("data", {})

    body_parts = []

    # 通用字段
    if "视角" in data:
        body_parts.append(f"<p><b>视角:</b> {data['视角']}</p>")
    if "在册组数" in data:
        body_parts.append(f"<p>在册 {data['在册组数']} 组 · 有日报数据 {data.get('本次有日报数据的组', '?')} 组</p>")

    # 按灯色
    if "按灯色分类" in data:
        body_parts.append("<table><tr><th>灯色</th><th>组数</th></tr>")
        for color, entries in data["按灯色分类"].items():
            css = color.replace("/", "")
            body_parts.append(f'<tr><td class="{css}">{color}</td><td>{len(entries)}</td></tr>')
        body_parts.append("</table>")

        for color, entries in data["按灯色分类"].items():
            if not entries:
                continue
            css = color.replace("/", "")
            body_parts.append(f'<h3 class="{css}">{color} ({len(entries)} 组)</h3>')
            body_parts.append("<table><tr><th>组</th><th>投手</th><th>CPHQ</th><th>HVU</th><th>日期</th></tr>")
            for e in entries[:20]:
                body_parts.append(
                    f"<tr><td>{e.get('group','?')}</td><td>{e.get('owner','?')}</td>"
                    f"<td>${e.get('cphq', '?')}</td><td>{e.get('hvu','?')}</td>"
                    f"<td>{e.get('date','?')}</td></tr>"
                )
            if len(entries) > 20:
                body_parts.append(f"<tr><td colspan=5>... 共 {len(entries)} 行</td></tr>")
            body_parts.append("</table>")

    # 按投手拆解(ZJB 视角)
    if "按投手拆解" in data:
        body_parts.append("<h3>按投手拆解</h3>")
        body_parts.append("<table><tr><th>投手</th><th>组数</th><th>绿灯数</th><th>CPHQ均</th></tr>")
        for owner, stats in data["按投手拆解"].items():
            body_parts.append(
                f"<tr><td>{owner}</td><td>{stats.get('组数','?')}</td>"
                f"<td>{stats.get('绿灯数','?')}</td><td>${stats.get('CPHQ均值','?')}</td></tr>"
            )
        body_parts.append("</table>")

    # 合约标识
    io = data.get("_io_contract", {})
    if io:
        body_parts.append(f"<p style='font-size:12px;color:#888'>"
                          f"target_role: {io.get('target_role')} · "
                          f"rule_source: {io.get('rule_source','')[:50]}</p>")

    return f"""
    <div class="card">
      <div class="card-header">
        {ts_str} · <span class="{status_class}">{status}</span> · {entry.get('duration_ms','?')}ms
      </div>
      {''.join(body_parts)}
    </div>
    """


REPO_URL_DEFAULT = "https://github.com/你的用户名/multisite-platform"


def build_pitcher_view(owner: str, entries: list[dict], all_owners: list[str], repo_url: str = REPO_URL_DEFAULT) -> str:
    html = HTML_HEAD.format(title=f"多站群多 agent · 投手 {owner}")
    html += html_nav(owner, all_owners)
    html += f"<h1>投手 {owner} 自看</h1>"
    html += f"""
    <div class="card">
      <div class="card-header">触发 agent</div>
      <a class="request-btn" href="{repo_url}/new/main/requests?filename=HZM-请求-{datetime.now().strftime('%Y%m%d-%H%M')}.md&value=---%0Aagent%3A+数据分析%0Aowner%3A+{owner}%0A---%0A%0A请帮我跑一次数据分析" target="_blank">
        📝 新建请求 · 跑数据分析
      </a>
      <a class="request-btn" href="{repo_url}/blob/main/platform-core/能力包/打法包-投手能力/投手{owner}-成人付费-激进.yaml" target="_blank">
        ⚙ 改打法包阈值
      </a>
      <p style="font-size:13px; color:#666; margin-top:10px">
      点上面任一按钮跳到 GitHub 网页 → 编辑保存 → 5-10 分钟后回此页 refresh 看新数据
      </p>
    </div>
    """
    html += f"<h2>近期 agent 输出({len(entries)} 条)</h2>"
    for entry in entries[:20]:
        html += render_agent_card(entry)

    html += f'<div class="footer">生成于 {datetime.now().isoformat()} · build.py</div>'
    html += "</body></html>"
    return html


def build_overview(overview_data: dict, all_owners: list[str], repo_url: str = REPO_URL_DEFAULT) -> str:
    html = HTML_HEAD.format(title="多站群多 agent · 总览")
    html += html_nav("总览", all_owners)
    html += "<h1>多站群多 agent · ZJB 总览</h1>"

    html += f"""
    <div class="card">
      <div class="card-header">概览</div>
      <p>共 {len(overview_data.get('agents', {}))} 个 agent 跑过 ·
         {len(overview_data.get('events_recent', []))} 个最近事件 ·
         {len(all_owners)} 个投手</p>
      <p><a href="{repo_url}/tree/main/requests" target="_blank">查看待处理请求</a></p>
    </div>
    """

    # 每个 agent 最近一次
    html += "<h2>各 agent 最近一次执行</h2>"
    html += "<table><tr><th>Agent</th><th>状态</th><th>时间</th><th>耗时</th></tr>"
    for agent, entries in overview_data.get("agents", {}).items():
        if not entries:
            continue
        e = entries[0]
        ts_str = datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M") if e.get("ts") else "?"
        html += (
            f'<tr><td>{agent}</td>'
            f'<td class="status-{e["status"]}">{e["status"]}</td>'
            f'<td>{ts_str}</td><td>{e.get("duration_ms","?")}ms</td></tr>'
        )
    html += "</table>"

    # 近期事件
    html += "<h2>近期事件流水</h2>"
    html += "<table><tr><th>时间</th><th>事件</th><th>来源</th></tr>"
    for ev in overview_data.get("events_recent", [])[:20]:
        ts_str = datetime.fromtimestamp(ev["ts"]).strftime("%H:%M:%S") if ev.get("ts") else "?"
        html += f'<tr><td>{ts_str}</td><td>{ev["type"]}</td><td>{ev.get("source","")}</td></tr>'
    html += "</table>"

    html += f'<div class="footer">生成于 {datetime.now().isoformat()} · build.py</div>'
    html += "</body></html>"
    return html


def main():
    VIEW_DIR.mkdir(parents=True, exist_ok=True)

    # 找最新一份 cards
    overview_cards = sorted(CARDS_DIR.glob("多站群-*-总览.json"))
    if not overview_cards:
        print("⚠ 未找到 data/cards/多站群-*-总览.json,先跑 bin/export_dashboard.py")
        return

    latest_overview = overview_cards[-1]
    overview_data = json.loads(latest_overview.read_text(encoding="utf-8"))
    print(f"✓ 读取总览: {latest_overview.name}")

    # 找各投手 cards
    pitcher_data: dict[str, dict] = {}
    for f in CARDS_DIR.glob("多站群-*.json"):
        if "总览" in f.name:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        owner = d.get("_meta", {}).get("owner")
        if owner:
            pitcher_data[owner] = d
            print(f"✓ 读取 {owner}: {f.name}")

    all_owners = sorted(pitcher_data.keys())

    # 生成 index.html(总览)
    overview_html = build_overview(overview_data, all_owners)
    (VIEW_DIR / "index.html").write_text(overview_html, encoding="utf-8")
    print(f"✓ 写出 view/index.html")

    # 每个投手一份
    for owner, d in pitcher_data.items():
        entries = d.get("agent_outputs", [])
        h = build_pitcher_view(owner, entries, all_owners)
        (VIEW_DIR / f"{owner}.html").write_text(h, encoding="utf-8")
        print(f"✓ 写出 view/{owner}.html")

    print(f"\n→ 双击 {VIEW_DIR / 'index.html'} 本地预览")
    print(f"→ git push 到 GitHub Pages 后 HZM 浏览器可访问")


if __name__ == "__main__":
    main()
