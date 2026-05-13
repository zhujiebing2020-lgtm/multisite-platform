#!/bin/bash
# bin/start.sh
# 一键启动:拉最新代码 → 跑一次真 ingest → 重建 dashboard → 起 monitor 后台监听
#
# 用法:
#   bash bin/start.sh                  一次性跑 + 起后台 monitor
#   bash bin/start.sh --ingest-only    只跑 ingest 不起 monitor
#   bash bin/start.sh --stop           停止后台 monitor

set -e
cd "$(dirname "$0")/.."

MODE="${1:-}"
PID_FILE=/tmp/multisite-monitor.pid
LOG=/tmp/multisite-monitor.log

# ─── stop 模式 ──────────────────────────────
if [ "$MODE" = "--stop" ]; then
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            rm -f "$PID_FILE"
            echo "✓ monitor 已停止 (pid=$PID)"
        else
            rm -f "$PID_FILE"
            echo "⚠ monitor 进程不存在,已清 pid 文件"
        fi
    else
        echo "⚠ 未找到 pid 文件,monitor 未运行?"
    fi
    exit 0
fi

# ─── 主流程 ────────────────────────────────
echo "━━━ 多站群多 agent · 一键启动 ━━━"
echo "repo: $(pwd)"
echo

# 1. 拉最新代码(无 remote 时跳过)
if git remote | grep -q origin; then
    echo "→ git pull"
    git pull --ff-only --quiet 2>/dev/null || echo "  (pull 失败,忽略)"
else
    echo "→ 无 remote 配置,跳过 pull"
fi

# 2. 真 ingest(跑最近 3 天数据)
echo
echo "→ 跑真 ingest(最近 3 天)"
python3 bin/ingest_daily.py --dates 2026-05-11 2026-05-12 2026-05-13 2>&1 | grep -E "(✓|✗|投手|ZJB|read CSV|行数据)" | head -10

# 3. 生成 dashboard(ingest 内部已跑,这里再保险)
echo
echo "→ dashboard 已在 ingest 内重建"

# 4. 自动 push(无 remote 跳过)
echo
echo "→ git sync"
bash bin/git_sync.sh

# 5. 起 monitor(如非 --ingest-only)
if [ "$MODE" = "--ingest-only" ]; then
    echo
    echo "━━━ ingest-only 模式,不起 monitor ━━━"
    exit 0
fi

# 检查是否已有 monitor 在跑
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo
    echo "⚠ monitor 已在运行 (pid=$(cat "$PID_FILE")),跳过启动"
    echo "  想重启:bash bin/start.sh --stop && bash bin/start.sh"
    exit 0
fi

echo
echo "→ 后台起 monitor(每 60s 扫一次 requests/)"
nohup python3 bin/request_monitor.py --watch > "$LOG" 2>&1 &
echo $! > "$PID_FILE"

echo
echo "━━━ 启动完成 ━━━"
echo "  monitor pid    : $(cat "$PID_FILE")"
echo "  monitor log    : $LOG"
echo "  git sync log   : /tmp/multisite-git-sync.log"
echo "  stop monitor   : bash bin/start.sh --stop"
echo
echo "本地预览:"
echo "  open view/index.html"
echo
if git remote | grep -q origin; then
    REMOTE=$(git remote get-url origin 2>/dev/null | sed 's|.*:\(.*\)\.git|\1|; s|.*github.com/\(.*\)\.git|\1|')
    if [ -n "$REMOTE" ]; then
        echo "HZM 远程看板:"
        echo "  https://${REMOTE%%/*}.github.io/${REMOTE##*/}/"
    fi
fi
