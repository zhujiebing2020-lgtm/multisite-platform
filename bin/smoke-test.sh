#!/bin/bash
# bin/smoke-test.sh — 冒烟测试：验证 z-jb.com 核心流程
set -e

BASE="https://z-jb.com"
PASS="crave2026"
FAIL=0
TOTAL=0

check() {
  TOTAL=$((TOTAL+1))
  local desc="$1" expect="$2" actual="$3"
  if echo "$actual" | grep -q "$expect"; then
    printf "  ✓ %s\n" "$desc"
  else
    printf "  ✗ %s (期望含 '%s', 实际: %s)\n" "$desc" "$expect" "${actual:0:120}"
    FAIL=$((FAIL+1))
  fi
}

echo "=== z-jb.com 冒烟测试 ==="
echo ""

# 1. 登录
echo "[Auth]"
LOGIN=$(curl -s -c /tmp/smoke.cookie -X POST "$BASE/api/auth" -H 'Content-Type: application/json' -d "{\"passcode\":\"$PASS\"}")
check "admin 登录" '"ok":true' "$LOGIN"
COOKIE=$(grep session /tmp/smoke.cookie | awk '{print $NF}')

# 2. 退出登录
LOGOUT=$(curl -s -X POST "$BASE/api/logout")
check "退出登录" '"ok":true' "$LOGOUT"

# 3. Admin API
echo ""
echo "[Admin]"
USERS=$(curl -s -b "session=$COOKIE" "$BASE/api/admin/users")
check "列出用户" "owner_code" "$USERS"

LOGS=$(curl -s -b "session=$COOKIE" "$BASE/api/admin/logs?days=1")
check "查询日志" '"id"' "$LOGS"

# 4. 权限隔离
echo ""
echo "[权限]"
# 用投手口令登录
PITCHER_LOGIN=$(curl -s -c /tmp/smoke_p.cookie -X POST "$BASE/api/auth" -H 'Content-Type: application/json' -d '{"passcode":"xiuxiu"}')
check "投手登录" '"ok":true' "$PITCHER_LOGIN"
P_COOKIE=$(grep session /tmp/smoke_p.cookie | awk '{print $NF}')

PITCHER_ADMIN=$(curl -s -b "session=$P_COOKIE" "$BASE/api/admin/users")
check "投手无admin权限" "管理员权限" "$PITCHER_ADMIN"

# 5. 数据上传 (ingest)
echo ""
echo "[Ingest]"
INGEST=$(curl -s -b "session=$COOKIE" -X POST "$BASE/api/ingest" -H 'Content-Type: application/json' \
  -d '{"site":"_test","records":[{"owner":"TEST","date":"2099-01-01","group_name":"smoke_test","spend":0.01,"hvu":0,"cphq":0}]}')
check "ingest 入库" '"ok":true' "$INGEST"

# 6. HVU JSON 上传
echo ""
echo "[Upload]"
UPLOAD_JSON=$(curl -s -b "session=$COOKIE" -X POST "$BASE/api/upload" -H 'Content-Type: application/json' \
  -d '{"filename":"smoke-test.json","contentBase64":"eyJzZXNzaW9ucyI6W119","owner":"TEST","site":"elysianu","channel":"FB"}')
check "JSON 上传" '"ok":true' "$UPLOAD_JSON"

# 7. Dashboard
echo ""
echo "[Dashboard]"
DASH=$(curl -s -b "session=$COOKIE" "$BASE/api/dashboard")
check "dashboard 返回" '"ok":true' "$DASH"

# 8. 前端页面可达（Cloudflare SPA 会 307 .html → 无后缀，用 -L 跟随）
echo ""
echo "[Pages]"
APP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/")
check "主页 200" "200" "$APP"

UPLOAD_PAGE=$(curl -s -o /dev/null -w "%{http_code}" -L "$BASE/upload.html")
check "upload 200" "200" "$UPLOAD_PAGE"

AGENTS_PAGE=$(curl -s -o /dev/null -w "%{http_code}" -L "$BASE/agents.html")
check "agents 200" "200" "$AGENTS_PAGE"

RESULTS_PAGE=$(curl -s -o /dev/null -w "%{http_code}" -L "$BASE/results.html")
check "results 200" "200" "$RESULTS_PAGE"

# 9. 退出按钮存在
APP_HTML=$(curl -s "$BASE/")
check "主页有退出按钮" "退出" "$APP_HTML"
check "主页有用户管理" "admin/users" "$APP_HTML"

# 清理测试数据
curl -s -b "session=$COOKIE" -X POST "$BASE/api/ingest" -H 'Content-Type: application/json' \
  -d '{"site":"_test","records":[{"owner":"TEST","date":"2099-01-01","group_name":"smoke_test","spend":0,"hvu":0,"cphq":0}]}' > /dev/null

# 结果
echo ""
echo "=== 结果: $((TOTAL-FAIL))/$TOTAL 通过 ==="
if [ $FAIL -gt 0 ]; then
  echo "⚠️  $FAIL 项失败"
  exit 1
else
  echo "全部通过"
fi
