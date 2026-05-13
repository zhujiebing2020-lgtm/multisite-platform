"""bin/build_widget.py
生成可被 crave-AI 看板嵌入的精简 widget

输出: view/widget.html
特点:
  · 无外部 CSS/JS 依赖
  · 高度紧凑(适合 iframe 嵌入)
  · 自适应,适配父页面宽度
  · 显示要点:11 agent 状态 / 各投手当日数据摘要 / 最近事件
"""
import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CARDS_DIR = REPO / "data" / "cards"
VIEW_DIR = REPO / "view"

CSS = """
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 12px; color: #222; font-size: 13px; background: #fff; }
  .header { display: flex; justify-content: space-between; align-items: center;
            border-bottom: 2px solid #06c; padding-bottom: 6px; margin-bottom: 10px; }
  .header h2 { margin: 0; font-size: 15px; color: #06c; }
  .header a { color: #888; text-decoration: none; font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; }
  .tile { border: 1px solid #e0e0e0; border-radius: 4px; padding: 8px; background: #fafafa; }
  .tile-title { font-weight: bold; color: #444; font-size: 12px; margin-bottom: 4px; }
  .tile-num { font-size: 16px; color: #06c; font-weight: bold; }
  .tile-sub { color: #888; font-size: 11px; }
  .status-success { color: #2a7; }
  .status-failed { color: #d44; }
  .绿 { color: #2a7; } .黄 { color: #c80; } .橙 { color: #d44; }
  .footer { margin-top: 10px; padding-top: 8px; border-top: 1px solid #eee;
            color: #888; font-size: 11px; text-align: right; }
</style>
"""


def render():
    overviews = sorted(CARDS_DIR.glob("多站群-*-总览.json"))
    if not overviews:
        return "<div>暂无数据</div>"
    overview = json.loads(overviews[-1].read_text(encoding="utf-8"))

    # 投手摘要
    pitcher_tiles = []
    for f in sorted(CARDS_DIR.glob("多站群-*.json")):
        if "总览" in f.name:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        owner = d.get("_meta", {}).get("owner")
        if not owner:
            continue
        # 找最新数据分析输出
        entries = d.get("agent_outputs", [])
        latest = entries[0] if entries else None
        if not latest:
            continue
        data = latest.get("data", {})
        by_color = data.get("按灯色分类", {})
        green = len(by_color.get("绿灯", []))
        yellow = len(by_color.get("黄灯", []))
        orange = (len(by_color.get("橙灯", [])) + len(by_color.get("橙灯/红灯候选", [])))
        n_groups = data.get("本次有日报数据的组", 0)
        pitcher_tiles.append(f"""
          <div class="tile">
            <div class="tile-title">{owner}</div>
            <div class="tile-num">{n_groups} <span style='font-size:11px;color:#888'>组有数据</span></div>
            <div class="tile-sub">
              <span class="绿">{green} 绿</span> /
              <span class="黄">{yellow} 黄</span> /
              <span class="橙">{orange} 橙</span>
            </div>
          </div>
        """)

    # agent 健康度
    agent_tiles = []
    for agent, entries in overview.get("agents", {}).items():
        if not entries:
            continue
        e = entries[0]
        st_class = f"status-{e['status']}"
        agent_tiles.append(f"""
          <div class="tile">
            <div class="tile-title">{agent}</div>
            <div class="tile-num {st_class}" style='font-size:13px'>{e['status']}</div>
            <div class="tile-sub">{datetime.fromtimestamp(e['ts']).strftime('%m-%d %H:%M')}</div>
          </div>
        """)

    repo_url = "https://github.com/zhujiebing2020-lgtm/multisite-platform"
    pages_url = "https://zhujiebing2020-lgtm.github.io/multisite-platform/"

    pitcher_html = ''.join(pitcher_tiles) if pitcher_tiles else '<div style="color:#888">暂无数据</div>'
    agent_html = ''.join(agent_tiles) if agent_tiles else '<div style="color:#888">暂无 agent 运行</div>'
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>多站群多 agent · widget</title>
{CSS}
</head>
<body>
  <div class="header">
    <h2>多站群多 agent</h2>
    <a href="{pages_url}" target="_top">完整看板 →</a>
  </div>

  <div style='font-size:12px; color:#666; margin-bottom:6px'>各投手当日数据</div>
  <div class="grid">
    {pitcher_html}
  </div>

  <div style='font-size:12px; color:#666; margin: 12px 0 6px'>各 agent 健康度</div>
  <div class="grid">
    {agent_html}
  </div>

  <div class="footer">
    更新于 {update_time} ·
    <a href="{repo_url}/tree/main/requests" target="_top">提请求</a>
  </div>
</body>
</html>"""
    return html


def main():
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    html = render()
    (VIEW_DIR / "widget.html").write_text(html, encoding="utf-8")
    print(f"✓ 写出 {VIEW_DIR / 'widget.html'}")


if __name__ == "__main__":
    main()
