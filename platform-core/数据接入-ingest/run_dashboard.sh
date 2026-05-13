#!/bin/bash
# Crave AI 看板更新全流程 v3.1 · 2026-05-13 重写 · 委派 daily_close.py
#
# v3.1 变更:
# - 全权委派 scripts/daily_close.py · 单一真理源
# - daily_close 完成 5 段(ingest/google/卡片校验/build/verify + optional push)
# - ZJB 5/13 反馈修复:忘 rebuild / 漏卡 / commit msg 不标漏段 · daily_close 统一解决

set -e

REPO="$HOME/Documents/GitHub/crave-AI"
LOG_FILE="$HOME/.crave_ai_dashboard.log"
cd "$REPO"

SKIP_INGEST=0
AUTO_PUSH=0
QUIET=0
for arg in "$@"; do
    case "$arg" in
        --skip-ingest) SKIP_INGEST=1 ;;
        --auto-push) AUTO_PUSH=1 ;;
        --quiet) QUIET=1 ;;
    esac
done

# quiet 模式:输出全部重定向到日志
if [ "$QUIET" -eq 1 ]; then
    exec >> "$LOG_FILE" 2>&1
fi

echo ""
echo "=================================================="
echo "=== Crave AI 看板更新 v3 · $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "=================================================="

if [ "$SKIP_INGEST" -eq 0 ]; then
    echo ""
    echo "[delegate → daily_close.py] 完整 5 段流(ingest + google + 卡片校验 + build + verify)"
    ARGS=""
    [ "$AUTO_PUSH" -eq 1 ] && ARGS="$ARGS --auto-push"
    python3 "$REPO/scripts/daily_close.py" $ARGS
else
    echo ""
    echo "[skip-ingest] 仅 build + verify"
    ARGS="--no-ingest --no-google"
    [ "$AUTO_PUSH" -eq 1 ] && ARGS="$ARGS --auto-push"
    python3 "$REPO/scripts/daily_close.py" $ARGS
fi

echo ""
echo "=== Done · $(date '+%H:%M:%S') ==="
