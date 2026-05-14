#!/bin/bash
# bin/git_sync.sh
# 自动 commit + push 处理结果到 GitHub
# monitor 处理完请求后调用,或单独手动跑
#
# 安全策略:
#   · 只 add 看板产物 + 归档请求(data/cards/ view/ requests/_done/)
#   · 不 add 代码改动(code/rules 需要人工 review 后手动 commit)
#   · 无 remote 时静默退出(本地开发友好)
#   · push 失败不崩(记 log,等下一次重试)

set -e
cd "$(dirname "$0")/.."

LOG=/tmp/multisite-git-sync.log

# 1. 无 remote 则跳过
if ! git remote | grep -q origin; then
    echo "[$(date +%H:%M:%S)] ⚠ 未配置 remote origin,跳过 push" | tee -a "$LOG"
    exit 0
fi

# 2. 只 add 看板产物 + 归档请求
git add data/cards/ data/uploads/ view/ requests/_done/ requests/uploads/_done/ 2>/dev/null || true

# 3. 没改动就退出
if git diff --cached --quiet; then
    echo "[$(date +%H:%M:%S)] 无改动,跳过" | tee -a "$LOG"
    exit 0
fi

# 4. 统计改动
CHANGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
REQUESTS=$(git diff --cached --name-only requests/_done/ 2>/dev/null | wc -l | tr -d ' ')

# 5. 规范 commit message(加 [skip ci] 防 Actions 触发循环)
MSG="auto: dashboard refresh · ${CHANGED} files [skip ci]"
if [ "$REQUESTS" -gt 0 ]; then
    MSG="auto: 处理 ${REQUESTS} 个请求 + 刷新看板 [skip ci]"
fi

git -c user.name="multisite-monitor" -c user.email="monitor@local" \
    commit -q -m "$MSG" || {
        echo "[$(date +%H:%M:%S)] ✗ commit 失败" | tee -a "$LOG"
        exit 1
    }

echo "[$(date +%H:%M:%S)] ✓ commit: $MSG" | tee -a "$LOG"

# 6. push(失败不崩,只记 log)
if git push origin HEAD 2>>"$LOG"; then
    echo "[$(date +%H:%M:%S)] ✓ push 成功" | tee -a "$LOG"
else
    echo "[$(date +%H:%M:%S)] ✗ push 失败(见 $LOG),下次重试" | tee -a "$LOG"
    exit 0   # 不崩,让 monitor 继续
fi
