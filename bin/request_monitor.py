"""bin/request_monitor.py
监听 requests/ 目录,看到新请求 → 自动跑对应 agent → 回写结果

用法:
  python3 bin/request_monitor.py           跑一次扫描(配合 cron)
  python3 bin/request_monitor.py --watch   持续监听(每 60s 扫一次)

请求文件格式(HZM 在 GitHub 网页编辑这个):
---
agent: 数据分析
owner: HZM
---
正文(可选,Claude 看)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
REQ_DIR = REPO / "requests"
DONE_DIR = REPO / "requests" / "_done"


def parse_request(path: Path) -> dict:
    """简单 YAML frontmatter 解析"""
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    meta = {}
    body = text
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = fm_match.group(2).strip()
    return {"meta": meta, "body": body, "path": path}


def run_agent(agent_name: str, owner: Optional[str] = None) -> dict:
    """直接调 agent,不走 Engine(MVP)"""
    sys.path.insert(0, str(REPO / "platform-core/执行层"))
    sys.path.insert(0, str(REPO / "platform-core/中间件"))
    sys.path.insert(0, str(REPO / "platform-core/数据层"))
    sys.path.insert(0, str(REPO / "platform-core/引擎层"))

    import importlib.util
    p = REPO / "platform-core/执行层" / agent_name / "agent.py"
    if not p.is_file():
        return {"error": f"agent {agent_name!r} 不存在"}

    spec = importlib.util.spec_from_file_location(f"agent_{agent_name}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from _base import AgentInput, TimeWindow
    from engine import get_engine

    engine = get_engine()
    tid = engine.submit(agent_name, "elysianu", priority=3, lookback_days=7,
                       upstream_output={"owner_filter": owner} if owner else {})
    task = engine.next()

    inp = AgentInput(site_id="elysianu", time_window=TimeWindow.last_n_days(7),
                     overrides={"owner_filter": owner} if owner else {})
    result = mod.run(inp)
    engine.complete(tid, result)
    return {
        "agent": agent_name, "owner": owner,
        "status": result.status.value,
        "ts": datetime.now().isoformat(),
    }


def process(req: dict) -> dict:
    agent = req["meta"].get("agent", "").strip()
    owner = req["meta"].get("owner", "").strip() or None
    if not agent:
        return {"error": "请求文件缺 agent 字段"}
    print(f"  跑 agent={agent} owner={owner or '(全部)'}")
    return run_agent(agent, owner)


def scan_once() -> int:
    DONE_DIR.mkdir(exist_ok=True)

    # 先 git pull,看 HZM 是否有新请求
    if (REPO / ".git").is_dir():
        result = subprocess.run(
            ["git", "-C", str(REPO), "pull", "--ff-only", "--quiet"],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and "no upstream" not in result.stderr.lower():
            print(f"  ⚠ git pull 失败(忽略,见 stderr): {result.stderr.strip()[:100]}")

    pending = sorted([f for f in REQ_DIR.glob("*.md")
                     if f.name != "README.md" and "_done" not in str(f)])
    if not pending:
        return 0

    for path in pending:
        print(f"\n→ 处理请求 {path.name}")
        try:
            req = parse_request(path)
            result = process(req)
            print(f"  结果: {json.dumps(result, ensure_ascii=False)}")
            # 回写结果到请求文件末尾
            with path.open("a", encoding="utf-8") as f:
                f.write(f"\n\n---\n## 处理结果\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n")
            # 归档
            done_path = DONE_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path.name}"
            shutil.move(str(path), str(done_path))
            print(f"  归档至 {done_path.name}")
        except Exception as e:
            print(f"  ✗ 失败: {e}")

    # 重新生成 dashboard
    print(f"\n→ 重生成 dashboard")
    subprocess.run([sys.executable, str(REPO / "bin/export_dashboard.py")], check=False)
    subprocess.run([sys.executable, str(REPO / "bin/build.py")], check=False)
    subprocess.run([sys.executable, str(REPO / "bin/build_widget.py")], check=False)

    # 自动 commit + push(无 remote 则静默)
    print(f"\n→ 自动 git sync")
    subprocess.run(["bash", str(REPO / "bin/git_sync.sh")], check=False)
    return len(pending)


def main():
    watch_mode = "--watch" in sys.argv
    if watch_mode:
        print(f"━━━ 监听模式 · 每 60s 扫一次 {REQ_DIR} ━━━")
        while True:
            n = scan_once()
            if n:
                print(f"\n=== 本轮处理 {n} 个请求,等待下次... ===")
            time.sleep(60)
    else:
        n = scan_once()
        print(f"\n本轮处理 {n} 个请求")


if __name__ == "__main__":
    main()
