"""platform-core/上下文层/context.py
LoadedConfig dataclass — 站运行时上下文的强类型数据结构

loader.md §2.3 定义。
对外稳定接口的一部分:字段只加不删,改类型 = major bump。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResolvedField:
    """打平后的单个阈值字段,带四层来源追溯"""
    value: Any
    source: str  # L1 / L2 / L3 / L4

    def __repr__(self) -> str:
        return f"{self.value!r}@{self.source}"


@dataclass
class LoadedConfig:
    """
    站的完整运行时上下文。
    Agent 不属于站,带着这个 context 运行(SVG §15.1)。
    """
    # 站级信息
    site_id: str
    owner: str
    category: str

    # 打法包解析结果
    playbook_ref: str
    playbook_author: str
    playbook_version: str
    playbook_stage: str
    playbook_lineage: list[str]

    # 启用的 agent + flow
    enabled_agents: list[str]
    active_flow: str

    # 四层合并后的阈值(扁平 key,带来源标记)
    resolved_thresholds: dict[str, ResolvedField]

    # 能力包引用
    production_packages: list[str]
    content_pack: str | None

    # 预算
    budget: dict

    # 原始 dict(审计用,不参与逻辑)
    raw_site_cfg: dict = field(repr=False, default_factory=dict)
    raw_playbook: dict = field(repr=False, default_factory=dict)

    def is_active(self) -> bool:
        return self.raw_site_cfg.get("_meta", {}).get("status") not in ("paused",)
