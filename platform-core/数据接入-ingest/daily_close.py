#!/usr/bin/env python3
"""daily_close · Crave AI 每日收口一键脚本 · v1 · 2026-05-13

责任(按顺序执行,任何一段失败记录到 miss_segments 但不终止):
1. ingest  —— scripts/ingest_from_daily_long.py  (含 --dates 支持)
2. google  —— scripts/gen_google_daily_cards.py  (自动补当日 Google 日卡)
3. cards   —— 校验 FB/action/auto-strategy 3 张日卡是否存在,缺则告警
4. build   —— renderer/build.py --runtime  (重建 index.html)
5. verify  —— 读 index.html / dashboard_data.json / DB 对齐当日日期

用法:
  python3 scripts/daily_close.py                 # --date = daily_long 最后一天
  python3 scripts/daily_close.py --date 2026-05-12
  python3 scripts/daily_close.py --no-build      # 跳过 build
  python3 scripts/daily_close.py --auto-push     # 执行完 git commit + push

launchd 用:
  python3 scripts/daily_close.py --auto-push --quiet
"""
from __future__ import annotations
import argparse, csv, json, subprocess, sys
from datetime import datetime
from pathlib import Path

REPO = Path.home() / 'Documents/GitHub/crave-AI'
DAILY_LONG = REPO / 'data/ad_history/current_account_daily_long.csv'
DASHBOARD_JSON = REPO / 'renderer/dashboard_data.json'
INDEX_HTML = REPO / 'index.html'
CARDS_DIR = REPO / 'data/cards'
LOG_FILE = Path.home() / '.crave_ai_daily_close.log'


def run(cmd, label, miss, quiet=False):
    print(f'\n[{label}] {" ".join(cmd)}')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
        if r.returncode != 0:
            miss.append(f'{label}(exit {r.returncode})')
            print(f'  ✗ exit {r.returncode}')
            print(r.stderr[:500])
            return False
        if not quiet:
            tail = r.stdout.strip().split('\n')[-5:]
            for ln in tail: print('  ' + ln)
        return True
    except Exception as e:
        miss.append(f'{label}(exception:{e})')
        print(f'  ✗ {e}')
        return False


def latest_date_in_daily_long() -> str | None:
    if not DAILY_LONG.exists(): return None
    dates = set()
    with DAILY_LONG.open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            d = (r.get('date') or '').strip()
            if d: dates.add(d)
    return max(dates) if dates else None


def check_cards(date: str, miss: list):
    expected = {
        f'daily-{date}.json':        'FB 日卡(daily-*.json)',
        f'daily-{date}-google.json': 'Google 日卡(自动生成)',
        f'auto-strategy-{date}.json': 'auto-strategy 自动策略草稿',
        f'action-pitcher-{date}.json': 'action-pitcher 投手指令',
    }
    print(f'\n[cards] 检查 {date} 必需的 4 张卡:')
    for fname, desc in expected.items():
        p = CARDS_DIR / fname
        if p.exists():
            print(f'  ✓ {fname}')
        else:
            miss.append(f'card_missing:{fname}')
            print(f'  ✗ 缺 {fname}({desc})')


def verify_build(date: str, miss: list):
    # dashboard_data.json latest date
    try:
        dd = json.loads(DASHBOARD_JSON.read_text())
        dates = dd.get('dates', [])
        # 转 MD 格式对比:date=2026-05-12 → 5/12
        ymd = date.split('-')
        md = f'{int(ymd[1])}/{int(ymd[2])}'
        if dates and dates[-1] == md:
            print(f'  ✓ dashboard_data.json latest = {md}')
        else:
            miss.append(f'dashboard_not_latest(got={dates[-1] if dates else "?"} want={md})')
            print(f'  ✗ dashboard_data.json latest={dates[-1] if dates else "?"} · 期望 {md}')
    except Exception as e:
        miss.append(f'dashboard_read_fail:{e}')

    # index.html mtime 应该 > dashboard_data.json mtime
    if INDEX_HTML.exists():
        idx_mtime = INDEX_HTML.stat().st_mtime
        dd_mtime  = DASHBOARD_JSON.stat().st_mtime
        if idx_mtime >= dd_mtime - 1:  # 允许 1s 误差
            print(f'  ✓ index.html mtime ≥ dashboard_data.json mtime')
        else:
            miss.append('index_html_stale')
            print(f'  ✗ index.html 比 dashboard_data.json 旧 · 忘了 rebuild')
    else:
        miss.append('index_html_missing')


def auto_push(miss: list):
    print('\n[push] 检查 git 变更...')
    r = subprocess.run(['git', 'status', '--porcelain'], cwd=REPO, capture_output=True, text=True)
    if not r.stdout.strip():
        print('  (无变更 · 跳过 push)')
        return
    subprocess.run(['git', 'add', '-A'], cwd=REPO, check=True)
    miss_tag = f' · miss=[{",".join(miss)}]' if miss else ''
    msg = f"auto: daily_close {datetime.now().strftime('%Y-%m-%d %H:%M')}{miss_tag}"
    subprocess.run(['git', 'commit', '-m', msg], cwd=REPO, check=False)
    r = subprocess.run(['git', 'push', 'origin', 'main'], cwd=REPO, capture_output=True, text=True)
    if r.returncode == 0:
        print('  ✅ pushed')
    else:
        miss.append(f'push_fail:{r.returncode}')
        print(f'  ✗ push fail: {r.stderr[:200]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='YYYY-MM-DD · 默认取 daily_long 最后一天')
    ap.add_argument('--no-build', action='store_true')
    ap.add_argument('--no-ingest', action='store_true')
    ap.add_argument('--no-google', action='store_true')
    ap.add_argument('--auto-push', action='store_true')
    ap.add_argument('--quiet', action='store_true', help='输出重定向到 ~/.crave_ai_daily_close.log')
    args = ap.parse_args()

    if args.quiet:
        sys.stdout = open(LOG_FILE, 'a')
        sys.stderr = sys.stdout

    print(f'\n{"="*60}\ndaily_close · {datetime.now():%Y-%m-%d %H:%M:%S}\n{"="*60}')

    date = args.date or latest_date_in_daily_long()
    if not date:
        print('ERR: 无法确定日期 · daily_long 为空?')
        sys.exit(2)
    print(f'target date = {date}')

    miss = []

    # 1) ingest
    if not args.no_ingest:
        run(['python3', 'scripts/ingest_from_daily_long.py', '--dates', date], 'ingest', miss)

    # 2) google 日卡
    if not args.no_google:
        run(['python3', 'scripts/gen_google_daily_cards.py', '--date', date, '--overwrite'], 'google', miss)

    # 3) 卡片完整性
    check_cards(date, miss)

    # 4) build
    if not args.no_build:
        run(['python3', 'renderer/build.py', '--runtime'], 'build', miss)

    # 5) verify
    print('\n[verify]')
    verify_build(date, miss)

    # 6) push
    if args.auto_push:
        auto_push(miss)

    # summary
    print(f'\n{"="*60}')
    if miss:
        print(f'⚠ 漏段 {len(miss)}:')
        for m in miss: print(f'  · {m}')
        print('\nHint: 缺 auto-strategy/action-pitcher 日卡是 Claude 手工产物,需 ZJB 让 Claude 生成')
        sys.exit(1)
    else:
        print('✅ 5 段流全部通过')
        sys.exit(0)


if __name__ == '__main__':
    main()
