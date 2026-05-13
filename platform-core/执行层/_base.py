"""platform-core/执行层/_base.py
AgentInput / AgentResult dataclass — Agent 执行的统一 I/O 合约

对应 v3 §12.1 (入参) / §12.2 (出参)
对外稳定接口的一部分,SemVer:字段只加不删,改类型 = major bump
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol


# ─── 5 状态枚举(v3 §12.2)────────────────────────────
class AgentStatus(str, Enum):
    SUCCESS = "success"                    # 正常完成,有 data
    NO_DATA = "no_data"                    # 站没数据可分析(新站/低流量)
    EXTERNAL_FAILURE = "external_failure"  # 上游 API 失败(Meta/Google 挂了)
    TIMEOUT = "timeout"                    # 自身超时
    FAILED = "failed"                      # 内部异常


# ─── 时间窗 ───────────────────────────────────────
@dataclass
class TimeWindow:
    start: datetime
    end: datetime

    @classmethod
    def last_n_days(cls, n: int) -> "TimeWindow":
        # end = 今日 00:00 UTC,start = end - n 天(含今天计 n 天回看窗口)
        end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=n)
        return cls(start=start, end=end)

    def describe(self) -> str:
        return f"{self.start.date()} ~ {self.end.date()}"


# ─── Agent 入参(v3 §12.1)──────────────────────────
@dataclass
class AgentInput:
    site_id: str
    time_window: TimeWindow
    upstream_output: dict | None = None    # 链式调用时上一 agent 的输出
    overrides: dict = field(default_factory=dict)  # 来自 LoadedConfig.resolved_thresholds + L4
    # 内容包内容(创意-素材 agent 用),其它 agent 可忽略
    content_pack: dict | None = None


# ─── Agent 出参(v3 §12.2)──────────────────────────
@dataclass
class AgentResult:
    status: AgentStatus
    data: dict = field(default_factory=dict)
    cost: float = 0.0                       # 本次调用 USD
    gap_reason: str | None = None           # status != SUCCESS 时的原因
    duration_ms: int = 0
    agent_name: str = ""
    site_id: str = ""
    # 声明式事件发布:agent.run() 返回时声明要发什么事件,invoker 转发到 bus
    # 每个元素: {"type": str, "payload": dict}
    # 不持有 bus 引用,保持 agent 纯函数 + 无运行时依赖
    emit_events: list[dict] = field(default_factory=list)

    def is_ok(self) -> bool:
        return self.status == AgentStatus.SUCCESS


# ─── Agent 协议 ─────────────────────────────────
class Agent(Protocol):
    """所有 agent 实现这个协议"""
    name: str

    def run(self, inp: AgentInput) -> AgentResult: ...
