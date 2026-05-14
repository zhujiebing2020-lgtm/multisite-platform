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
  .agent-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                 gap: 8px; margin: 6px 0; }}
  .agent-btn {{ display: block; padding: 10px 12px; color: #fff; text-decoration: none;
                border-radius: 6px; transition: opacity 0.15s; }}
  .agent-btn:hover {{ opacity: 0.85; }}
  .agent-name {{ font-weight: bold; font-size: 14px; }}
  .agent-desc {{ font-size: 11px; opacity: 0.9; margin-top: 2px; }}
  .config-btn {{ display: inline-block; padding: 8px 14px; background: #444; color: #fff;
                 border-radius: 4px; text-decoration: none; }}
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


REPO_URL_DEFAULT = "https://github.com/zhujiebing2020-lgtm/multisite-platform"

# 11 个 agent · 业务前缀中文 + 用途说明 + 是否常用
AGENTS = [
    {"name": "数据分析",   "desc": "看自己组的灯色 / CPHQ / HVU",     "primary": True},
    {"name": "归因诊断",   "desc": "ROI 异动时排外因(env_flag)",      "primary": True},
    {"name": "知识沉淀",   "desc": "提炼命题(三要素+置信度)",         "primary": True},
    {"name": "策略简报",   "desc": "命题→投放方向(Hook/KPI)",          "primary": True},
    {"name": "文案",       "desc": "Hook / 正文 / 评论区",              "primary": False},
    {"name": "故事脚本",   "desc": "视频脚本(4 镜头逐帧)",              "primary": False},
    {"name": "素材审核",   "desc": "禁用词 / 调性 / 反 AI 腔",           "primary": False},
    {"name": "研发需求",   "desc": "UX 缺口→P0/P1/P2 技术需求",          "primary": False},
    {"name": "意志继承",   "desc": "S/B 类自动规则触发",                "primary": False},
    {"name": "搬运",       "desc": "子站→总站数据回灌",                 "primary": False},
    {"name": "交接消息",   "desc": "策略→飞书/微信粘贴版",              "primary": False},
]


def render_agent_buttons(owner: str, repo_url: str) -> str:
    """投手入口卡:跳到同域 upload.html(零 GitHub 依赖)
    历史上这里直接跳 GitHub 新建文件页;5/14 ZJB 否决,投手不该接触 GitHub。
    """
    return f'''
    <div class="card">
      <div class="card-header">投手工作台</div>
      <p style="margin: 8px 0 12px; font-size: 14px;">
        上传当日 xlsx、触发 agent、看自己看板 —— 全在这一个页面。
      </p>
      <a class="request-btn" href="upload.html" style="background:#06c; font-size:15px; padding:10px 20px">
        → 打开工作台
      </a>
      <p style="font-size:12px; color:#888; margin-top:12px">
        首次需要 ZJB 发的访问口令 · 不需要 GitHub 账号
      </p>
    </div>'''


def build_pitcher_view(owner: str, entries: list, all_owners: list, repo_url: str = REPO_URL_DEFAULT) -> str:
    html = HTML_HEAD.format(title=f"多站群多 agent · 投手 {owner}")
    html += html_nav(owner, all_owners)
    html += f"<h1>投手 {owner} 自看</h1>"
    html += render_agent_buttons(owner, repo_url)
    html += f"<h2>近期 agent 输出({len(entries)} 条)</h2>"
    for entry in entries[:20]:
        html += render_agent_card(entry)

    html += f'<div class="footer">生成于 {datetime.now().isoformat()} · build.py</div>'
    html += "</body></html>"
    return html


def list_recent_requests(limit: int = 10) -> list:
    """读 requests/ + requests/_done/ 列最近请求"""
    requests_dir = REPO / "requests"
    done_dir = requests_dir / "_done"
    rows = []

    # 处理中(在 requests/ 顶层但不是 README)
    for f in requests_dir.glob("*.md"):
        if f.name == "README.md":
            continue
        rows.append({
            "name": f.name, "status": "处理中",
            "ts": f.stat().st_mtime, "agent": "(未解析)",
            "owner": "(未解析)",
        })

    # 已处理(_done/)
    if done_dir.is_dir():
        for f in sorted(done_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            # 解析 frontmatter
            agent, owner = "?", "?"
            try:
                text = f.read_text(encoding="utf-8")
                import re
                m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if m:
                    for line in m.group(1).split("\n"):
                        if line.startswith("agent:"):
                            agent = line.split(":", 1)[1].strip()
                        elif line.startswith("owner:"):
                            owner = line.split(":", 1)[1].strip()
            except Exception:
                pass
            rows.append({
                "name": f.name, "status": "已处理",
                "ts": f.stat().st_mtime, "agent": agent, "owner": owner,
            })

    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows[:limit]


def build_overview(overview_data: dict, all_owners: list, repo_url: str = REPO_URL_DEFAULT) -> str:
    html = HTML_HEAD.format(title="多站群多 agent · 总览")
    html += html_nav("总览", all_owners)
    html += "<h1>多站群多 agent · ZJB 总览</h1>"

    html += f"""
    <div class="card">
      <div class="card-header">概览</div>
      <p>共 {len(overview_data.get('agents', {}))} 个 agent 跑过 ·
         {len(overview_data.get('events_recent', []))} 个最近事件 ·
         {len(all_owners)} 个投手</p>
      <p><a href="upload.html">→ 投手工作台</a></p>
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

    # 最近请求(P0-9.13 修 2)
    html += "<h2>最近请求(投手提的)</h2>"
    requests = list_recent_requests(limit=10)
    if not requests:
        html += "<p style='color:#888'>暂无请求记录</p>"
    else:
        html += "<table><tr><th>状态</th><th>时间</th><th>投手</th><th>agent</th><th>文件</th></tr>"
        for r in requests:
            ts_str = datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
            status_color = "#c80" if r["status"] == "处理中" else "#2a7"
            html += (
                f'<tr><td style="color:{status_color}">{r["status"]}</td>'
                f'<td>{ts_str}</td><td>{r["owner"]}</td><td>{r["agent"]}</td>'
                f'<td style="font-size:11px;color:#666">{r["name"]}</td></tr>'
            )
        html += "</table>"
        html += f'<p style="font-size:12px;color:#888"><a href="upload.html">打开投手工作台</a></p>'

    html += f'<div class="footer">生成于 {datetime.now().isoformat()} · build.py</div>'
    html += "</body></html>"
    return html


def build_station_overview(overview_data: dict, all_owners: list, all_sites: list) -> str:
    """站群总览(z-jb.com 根域)·极简版。
    包含: 子站卡片(crave/elysianu/+扩) · 全局 KPI · 投手×站×渠道热力(若数据足)
    """
    html = HTML_HEAD.format(title="z-jb.com · 站群总览")

    # 顶部导航(总览本身 + 投手页 + 投手工作台)
    html += '<div class="nav">'
    html += '<a href="index.html"><b>★ 站群总览</b></a>'
    for o in all_owners:
        html += f' | <a href="{o}.html">{o}</a>'
    html += ' | <a href="upload.html">投手工作台</a>'
    html += '</div>'

    html += '<h1>z-jb.com · 站群总览</h1>'
    html += '<p style="color:#888;font-size:13px">总站协调 · 各子站独立运营 · 数据回流训练 agent</p>'

    # 子站卡片
    html += '<h2>子站</h2>'
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:12px 0">'

    # crave 子站(独立 CNAME · 永远在)
    html += (
        '<div class="card" style="border-left:4px solid #06c">'
        '<div class="card-header">crave <span style="font-size:11px;color:#888">高权限</span></div>'
        '<p style="font-size:12px;color:#666;margin:6px 0">决策台 / 规则集中地 / agent 引擎</p>'
        '<a href="https://crave.z-jb.com" target="_blank" style="font-size:13px">→ crave.z-jb.com</a>'
        '</div>'
    )

    # 已知子站(从数据里抓 site,加上 elysianu 兜底)
    seen_sites = set(all_sites) | {"elysianu"}
    for site in sorted(seen_sites):
        html += (
            f'<div class="card">'
            f'<div class="card-header">{site}</div>'
            f'<p style="font-size:12px;color:#666;margin:6px 0">业务运营子站</p>'
            f'<a href="https://{site}.z-jb.com" target="_blank" style="font-size:13px">→ {site}.z-jb.com</a> '
            f'<span style="font-size:11px;color:#888">|</span> '
            f'<a href="site/{site}.html" style="font-size:13px">本地预览</a>'
            f'</div>'
        )

    # 加站占位
    html += (
        '<div class="card" style="border:2px dashed #ccc;background:#fafafa">'
        '<div class="card-header" style="color:#888">+ 添加新站</div>'
        '<p style="font-size:12px;color:#888;margin:6px 0">投手工作台"+ 加站"按钮提交后,'
        '由 ZJB 加入 sites/ 配置</p>'
        '</div>'
    )
    html += '</div>'

    # 全局 KPI
    html += '<h2>全局 KPI</h2>'
    html += (
        f'<div class="card">'
        f'<p>共 <b>{len(overview_data.get("agents", {}))}</b> 个 agent 跑过 · '
        f'<b>{len(overview_data.get("events_recent", []))}</b> 个最近事件 · '
        f'<b>{len(all_owners)}</b> 个投手 · '
        f'<b>{len(seen_sites)}</b> 个子站</p>'
        f'<p style="margin-top:8px"><a href="upload.html">→ 投手工作台(上传 xlsx / 触发 agent)</a></p>'
        f'</div>'
    )

    # 各 agent 最近一次执行
    html += '<h2>各 agent 最近一次执行</h2>'
    html += '<table><tr><th>Agent</th><th>状态</th><th>时间</th><th>耗时</th></tr>'
    for name, runs in overview_data.get("agents", {}).items():
        # runs 可能是 list(多次执行) 或单 dict — 兼容两种
        if isinstance(runs, list):
            e = runs[0] if runs else {}
        else:
            e = runs or {}
        ts_str = ""
        if e.get("ts"):
            try:
                ts_str = datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts_str = "?"
        st = e.get("status", "?")
        html += (
            f'<tr><td>{name}</td><td class="status-{st}">{st}</td>'
            f'<td>{ts_str}</td><td>{e.get("duration_ms","?")}ms</td></tr>'
        )
    html += "</table>"

    # 最近请求
    html += '<h2>最近请求(投手提的)</h2>'
    requests = list_recent_requests(limit=10)
    if not requests:
        html += "<p style='color:#888'>暂无请求记录</p>"
    else:
        html += '<table><tr><th>状态</th><th>时间</th><th>投手</th><th>agent</th><th>文件</th></tr>'
        for r in requests:
            ts_str = datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
            status_color = "#c80" if r["status"] == "处理中" else "#2a7"
            html += (
                f'<tr><td style="color:{status_color}">{r["status"]}</td>'
                f'<td>{ts_str}</td><td>{r["owner"]}</td><td>{r["agent"]}</td>'
                f'<td style="font-size:11px;color:#666">{r["name"]}</td></tr>'
            )
        html += "</table>"

    html += f'<div class="footer">生成于 {datetime.now().isoformat()} · build.py · z-jb.com 站群总览</div>'
    html += "</body></html>"
    return html


def build_site_view(site: str, all_owners: list, all_sites: list) -> str:
    """子站视图({site}.z-jb.com)。
    内容: 该站 KPI · 该站投手列表 · 该站最近 agent 输出
    数据来源: data/uploads/*.json 里 _meta.site == site 的;data/cards/ 里 site 字段匹配的
    """
    html = HTML_HEAD.format(title=f"{site}.z-jb.com · 子站运营视图")

    html += '<div class="nav">'
    html += '<a href="../index.html">站群总览</a> | '
    html += f'<a href="../index.html#{site}"><b>★ {site}</b></a> | '
    html += '<a href="../upload.html">投手工作台</a>'
    html += '</div>'

    html += f'<h1>{site} · 子站</h1>'
    html += '<p style="color:#888;font-size:13px">该站独立运营视图 · 数据范围限定本站</p>'

    # 该站数据汇总
    site_uploads = []
    uploads_dir = REPO / "data" / "uploads"
    if uploads_dir.exists():
        for f in sorted(uploads_dir.glob("*.json"), reverse=True)[:50]:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("_meta", {}).get("site") == site:
                    site_uploads.append((f.name, d))
            except Exception:
                continue

    html += '<h2>本站当日数据</h2>'
    if not site_uploads:
        html += '<p style="color:#888">暂无上传数据 — 在投手工作台选择本站并上传 xlsx</p>'
    else:
        html += '<table><tr><th>投手</th><th>渠道</th><th>日期</th><th>组数</th><th>来源</th></tr>'
        for fname, d in site_uploads[:20]:
            m = d.get("_meta", {})
            html += (
                f'<tr><td>{m.get("owner","?")}</td>'
                f'<td>{m.get("channel","?")}</td>'
                f'<td>{m.get("date","?")}</td>'
                f'<td>{len(d.get("rows", []))}</td>'
                f'<td style="font-size:11px;color:#666">{m.get("source_file","")}</td></tr>'
            )
        html += "</table>"

    html += '<h2>本站投手</h2>'
    site_owners = sorted({d.get("_meta", {}).get("owner") for _, d in site_uploads
                          if d.get("_meta", {}).get("owner")})
    if site_owners:
        html += '<div class="agent-grid">'
        for o in site_owners:
            html += f'<a class="agent-btn" href="../{o}.html" style="background:#06c"><div class="agent-name">{o}</div></a>'
        html += '</div>'
    else:
        html += '<p style="color:#888">暂无</p>'

    html += f'<div class="footer">生成于 {datetime.now().isoformat()} · build.py · {site} 子站视图</div>'
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

    # 收集所有 site(从 data/uploads/*.json _meta.site)
    all_sites: set[str] = set()
    uploads_dir = REPO / "data" / "uploads"
    if uploads_dir.exists():
        for f in uploads_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                s = d.get("_meta", {}).get("site")
                if s:
                    all_sites.add(s)
            except Exception:
                continue
    # 兜底加 elysianu(即使无数据,UI 也要展示)
    all_sites.add("elysianu")
    all_sites_list = sorted(all_sites)

    # 生成 index.html(站群总览)
    overview_html = build_station_overview(overview_data, all_owners, all_sites_list)
    (VIEW_DIR / "index.html").write_text(overview_html, encoding="utf-8")
    print(f"✓ 写出 view/index.html (站群总览)")

    # 每个投手一份
    for owner, d in pitcher_data.items():
        entries = d.get("agent_outputs", [])
        h = build_pitcher_view(owner, entries, all_owners)
        (VIEW_DIR / f"{owner}.html").write_text(h, encoding="utf-8")
        print(f"✓ 写出 view/{owner}.html")

    # 每个子站一份(view/site/{site}.html)
    site_dir = VIEW_DIR / "site"
    site_dir.mkdir(exist_ok=True)
    for site in all_sites_list:
        h = build_site_view(site, all_owners, all_sites_list)
        (site_dir / f"{site}.html").write_text(h, encoding="utf-8")
        print(f"✓ 写出 view/site/{site}.html")

    print(f"\n→ 双击 {VIEW_DIR / 'index.html'} 本地预览")
    print(f"→ 子域 {{site}}.z-jb.com 会通过 src/index.js 路由到 view/site/{{site}}.html")


if __name__ == "__main__":
    main()
