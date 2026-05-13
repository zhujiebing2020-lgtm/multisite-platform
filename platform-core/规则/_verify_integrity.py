"""platform-core/规则/_verify_integrity.py

L1 规则完整性校验

用途:
  1. CI / 启动时跑一次,确认 13 个规则文件未被任何方式修改(对账 _FORK_MANIFEST.json)
  2. 客户剥站时校验客户拿到的 platform-core/规则/ 是否完整(防止剥站过程文件损坏)
  3. fork 同步前对比当前 sha 与 manifest 是否一致(若不一致 = 本仓库被改过,需要 ZJB 确认)

设计原则:
  · 不依赖外部库(只用标准库 hashlib/json/pathlib)
  · 不 import 上下文层/中间件/任何 agent 层
  · 失败时退出码 != 0,可挂 git hook
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "_FORK_MANIFEST.json"


def verify() -> tuple[bool, list[str]]:
    if not MANIFEST_PATH.is_file():
        return False, [f"manifest 不存在: {MANIFEST_PATH}"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    errors = []
    n_ok = 0
    for name, meta in manifest.get("files", {}).items():
        path = HERE / name
        if not path.is_file():
            errors.append(f"✗ 缺失文件: {name}")
            continue
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = meta["sha256"]
        if actual_sha != expected:
            errors.append(
                f"✗ sha256 不一致: {name}\n"
                f"     manifest: {expected}\n"
                f"     actual:   {actual_sha}\n"
                f"     → 文件被改过!查 git log + 找 ZJB 确认是否要重新 fork crave-AI"
            )
            continue
        # 检查只读权限
        if path.stat().st_mode & 0o222:
            errors.append(f"⚠ 文件可写(权限非 r--r--r--): {name},应 chmod 444")
        n_ok += 1
    return len(errors) == 0, errors, n_ok if not errors else 0


def main():
    print(f"━━━ L1 规则完整性校验 ━━━")
    print(f"manifest: {MANIFEST_PATH}")
    print()
    result = verify()
    if len(result) == 3:
        ok, errors, n_ok = result
    else:
        ok, errors = result
        n_ok = 0

    if ok:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        total = len(manifest.get("files", {}))
        head = manifest.get("_meta", {}).get("source_repo", {}).get("head_short", "?")
        print(f"✓ 全部 {total} 个规则文件完整性 OK · crave-AI HEAD={head}")
        sys.exit(0)
    else:
        print(f"✗ 校验失败:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
