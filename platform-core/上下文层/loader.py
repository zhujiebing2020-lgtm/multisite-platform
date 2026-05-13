"""platform-core/上下文层/loader.py
load_site_config(site_id) -> LoadedConfig

实现 loader.md §1-§3 的稳定接口:
  · 扫描 sites/{site_id}/config.yaml 发现站
  · 解析打法包引用 {作者}-{品类}-{风格}@v{版本}
  · 四层覆盖合并(L1 平台默认 → L2 打法包 → L3 站级 → L4 运行时)
  · 返回 LoadedConfig 强类型对象

硬约束:不许 import sites/ 下的 Python(loader.md §1.2)。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

# 本文件所在目录 = platform-core/上下文层/
# 上溯 3 层 = repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_CORE = REPO_ROOT / "platform-core"
SITES_DIR = REPO_ROOT / "sites"
DEFAULTS_PATH = PLATFORM_CORE / "上下文层" / "defaults.yaml"
PLAYBOOKS_DIR = PLATFORM_CORE / "能力包" / "打法包-投手能力"

# 引用语法:{作者}-{品类}-{风格}@v{版本}
# 兼容中文,例:投手HZM-成人付费-激进@v0.1.0
PLAYBOOK_REF_RE = re.compile(
    r"^(?P<author>[^-@]+)-(?P<category>[^-@]+)-(?P<stage>[^-@]+)@v(?P<version>[\d.]+)$"
)

# 站 config 字段中英别名(漏洞 1 修复)
# 优先读中文 key(投手直觉),英文 key 作 fallback(客户剥站国际化)
FIELD_ALIAS = {
    "playbook": ["打法包", "playbook"],
    "production": ["产出包", "production", "productions"],
    "content": ["内容包", "content", "content_pack"],
}


def _get_aliased(cfg: dict, logical_name: str, default=None):
    """按 FIELD_ALIAS 的顺序逐个尝试取值,首个非空返回"""
    for key in FIELD_ALIAS.get(logical_name, [logical_name]):
        if key in cfg and cfg[key] not in (None, "", []):
            return cfg[key]
    return default

# 让 import context 工作:把本目录加进 sys.path
sys.path.insert(0, str(Path(__file__).parent))
from context import LoadedConfig, ResolvedField  # noqa: E402


# ─── 异常类(loader.md §4)──────────────────────────────
class SiteNotFoundError(Exception): ...
class ConfigMissingError(Exception): ...
class ConfigParseError(Exception): ...
class PlaybookNotFoundError(Exception): ...
class PlaybookRefSyntaxError(Exception): ...
class PlaybookVersionMismatchError(Exception): ...
class CategoryMismatchError(Exception): ...


# ─── 工具 ────────────────────────────────────────────
def _read_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigParseError(f"{path}: {e}") from e


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    """嵌套 dict 打平成 'a.b.c' → value,用于字段级覆盖"""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _parse_ref(ref: str) -> dict[str, str]:
    m = PLAYBOOK_REF_RE.match(ref.strip())
    if not m:
        raise PlaybookRefSyntaxError(
            f"打法包引用格式错误: {ref!r} (期望 author-category-stage@vX.Y.Z)"
        )
    return m.groupdict()


# ─── 主接口 ──────────────────────────────────────────
def load_site_config(
    site_id: str,
    runtime_overrides: dict | None = None,
) -> LoadedConfig:
    # Step 1 · 站 config
    site_dir = SITES_DIR / site_id
    if not site_dir.is_dir():
        raise SiteNotFoundError(site_id)
    site_cfg_path = site_dir / "config.yaml"
    if not site_cfg_path.is_file():
        raise ConfigMissingError(str(site_cfg_path))
    site_cfg = _read_yaml(site_cfg_path)

    # Step 2 · 定位打法包(漏洞 1 修复:支持中英 alias)
    ref = _get_aliased(site_cfg, "playbook")
    if not ref:
        raise ConfigMissingError(
            f"{site_cfg_path}: 缺少打法包字段 (尝试过: {FIELD_ALIAS['playbook']})"
        )
    parts = _parse_ref(ref)
    pb_path = PLAYBOOKS_DIR / f"{parts['author']}-{parts['category']}-{parts['stage']}.yaml"
    if not pb_path.is_file():
        raise PlaybookNotFoundError(f"{ref} → 找不到 {pb_path}")
    playbook = _read_yaml(pb_path)

    # Step 3 · 版本匹配
    pb_version = playbook.get("_meta", {}).get("version")
    if str(pb_version) != parts["version"]:
        raise PlaybookVersionMismatchError(
            f"引用 {ref} 期望 v{parts['version']}, 文件 _meta.version={pb_version}"
        )

    # Step 4 · category 校验
    site_cat = site_cfg.get("_meta", {}).get("category")
    pb_cat = playbook.get("_meta", {}).get("category")
    if site_cat != pb_cat:
        raise CategoryMismatchError(
            f"site.category={site_cat!r} ≠ playbook.category={pb_cat!r}"
        )

    # Step 5 · 四层覆盖合并(扁平字段级,L4>L3>L2>L1)
    l1 = _flatten((_read_yaml(DEFAULTS_PATH) or {}).get("thresholds", {}))
    l2 = _flatten(playbook.get("thresholds_overrides", {}) or {})
    l3 = _flatten(site_cfg.get("thresholds_overrides", {}) or {})
    l4 = _flatten(runtime_overrides or {})

    merged: dict[str, ResolvedField] = {}
    for layer, payload in (("L1", l1), ("L2", l2), ("L3", l3), ("L4", l4)):
        for k, v in payload.items():
            merged[k] = ResolvedField(value=v, source=layer)

    return LoadedConfig(
        site_id=site_id,
        owner=site_cfg.get("_meta", {}).get("owner", ""),
        category=site_cat or "",
        playbook_ref=ref,
        playbook_author=parts["author"],
        playbook_version=parts["version"],
        playbook_stage=parts["stage"],
        playbook_lineage=playbook.get("_meta", {}).get("lineage", []),
        enabled_agents=playbook.get("enabled_agents", []),
        active_flow=playbook.get("active_flow", ""),
        resolved_thresholds=merged,
        production_packages=(
            _get_aliased(site_cfg, "production", [])
            or playbook.get("production_packages", [])
        ),
        # 漏洞 2 修复:内容包解析顺序明确写出(loader.md §2.3 已同步)
        # 站 config.内容包 > 打法包.default_content_pack > None
        content_pack=(
            _get_aliased(site_cfg, "content")
            or playbook.get("default_content_pack")
        ),
        budget=site_cfg.get("budget", {}),
        raw_site_cfg=site_cfg,
        raw_playbook=playbook,
    )


# ─── CLI 自测 ────────────────────────────────────────
if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("用法: python loader.py <site_id>")
        sys.exit(1)
    cfg = load_site_config(sys.argv[1])

    print(f"site_id         : {cfg.site_id}")
    print(f"owner           : {cfg.owner}")
    print(f"category        : {cfg.category}")
    print(f"playbook_ref    : {cfg.playbook_ref}")
    print(f"playbook_stage  : {cfg.playbook_stage}")
    print(f"playbook_lineage: {cfg.playbook_lineage}")
    print(f"enabled_agents  : {cfg.enabled_agents}")
    print(f"active_flow     : {cfg.active_flow}")
    print(f"content_pack    : {cfg.content_pack}")
    print(f"budget          : {json.dumps(cfg.budget, ensure_ascii=False)}")
    print()
    print(f"─── resolved_thresholds ({len(cfg.resolved_thresholds)} 项) ───")
    for k in sorted(cfg.resolved_thresholds.keys()):
        print(f"  {k:40s} = {cfg.resolved_thresholds[k]}")
