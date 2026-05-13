"""platform-core/引擎层/engine.py
Task Engine · MVP

SVG L4 职责:状态机 · 优先级 · 任务队列 · 回滚 · 历史继承

MVP 形态:
  - 内存 dict + 进程内顺序消费,不引外部依赖
  - 单线程,无并发(P1 升 Redis Queue/Celery)
  - 状态机 5 态:pending → running → {success, failed, rolled_back}
  - 优先级:int,小=优先(0 = 最高);同优先级 FIFO
  - 历史继承:engine.history[(site_id, agent)] = [AgentResult, ...](按时间)
  - 回滚:任务 marked failed 后,留 rollback() 钩子,MVP 不真回滚
"""
from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from heapq import heappush, heappop
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "执行层"))
from _base import AgentResult, AgentStatus  # noqa: E402

# 数据层持久化;engine 可以 import 数据层,反过来不行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "数据层"))
try:
    from runtime import get_data_runtime  # noqa: E402
    _HAS_DR = True
except Exception:
    _HAS_DR = False


# ─── 状态机 ──────────────────────────────────────
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# 状态转移合法表(明示,避免随手乱跳)
LEGAL_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.SUCCESS, TaskStatus.FAILED},
    TaskStatus.SUCCESS: {TaskStatus.ROLLED_BACK},
    TaskStatus.FAILED: {TaskStatus.ROLLED_BACK},
    TaskStatus.ROLLED_BACK: set(),
}


# ─── Task 数据模型 ──────────────────────────────
@dataclass(order=True)
class Task:
    """
    单个任务。dataclass(order=True) + _sort_key 让 heapq 按 (priority, seq) 排序。
    """
    _sort_key: tuple = field(init=False, repr=False)
    priority: int                       # 小=优先,0 最高
    seq: int                            # 同优先级内 FIFO
    task_id: str
    agent_name: str
    site_id: str
    event_id: Optional[str] = None      # 触发本任务的事件,审计用
    lookback_days: int = 7
    upstream_output: Optional[dict] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[AgentResult] = None
    error: Optional[str] = None
    state_history: list = field(default_factory=list)   # [(timestamp, status, note)]

    def __post_init__(self):
        self._sort_key = (self.priority, self.seq)
        self._log_transition(self.status, "created")

    def _log_transition(self, new_status: TaskStatus, note: str = ""):
        self.state_history.append((time.time(), new_status.value, note))

    def transition(self, new_status: TaskStatus, note: str = ""):
        if new_status not in LEGAL_TRANSITIONS.get(self.status, set()):
            raise ValueError(
                f"非法状态转移: {self.status.value} → {new_status.value} "
                f"(task_id={self.task_id})"
            )
        self.status = new_status
        self._log_transition(new_status, note)


# ─── TaskEngine ────────────────────────────────
class TaskEngine:
    def __init__(self):
        self._queue: list[Task] = []
        self._seq_counter: int = 0
        self._tasks: dict[str, Task] = {}
        # 历史继承:(site_id, agent_name) -> [AgentResult, AgentResult, ...]
        self.history: dict[tuple[str, str], list[AgentResult]] = {}

    # ─── 持久化钩子(所有落库都走这里,便于统一关闭)─────
    def _persist_task_upsert(self, t: Task) -> None:
        if not _HAS_DR:
            return
        try:
            get_data_runtime().upsert_task(
                task_id=t.task_id, agent_name=t.agent_name, site_id=t.site_id,
                priority=t.priority, seq=t.seq, event_id=t.event_id,
                status=t.status.value, lookback_days=t.lookback_days,
                created_at=t.created_at, started_at=t.started_at,
                finished_at=t.finished_at, error=t.error,
            )
        except Exception as e:
            import sys as _sys
            print(f"[engine] upsert_task 失败: {e}", file=_sys.stderr)

    def _persist_task_transition(self, t: Task, new_status: TaskStatus, note: str) -> None:
        if not _HAS_DR:
            return
        try:
            import time as _t
            get_data_runtime().record_task_transition(
                task_id=t.task_id, status=new_status.value, note=note, ts=_t.time(),
            )
        except Exception as e:
            import sys as _sys
            print(f"[engine] record_task_transition 失败: {e}", file=_sys.stderr)

    def _persist_agent_result(self, t: Task, r: AgentResult) -> None:
        if not _HAS_DR:
            return
        try:
            get_data_runtime().record_agent_result(
                task_id=t.task_id, site_id=t.site_id, agent_name=t.agent_name,
                status=r.status.value, data=r.data, emit_events=r.emit_events,
                cost=r.cost, duration_ms=r.duration_ms, gap_reason=r.gap_reason,
            )
        except Exception as e:
            import sys as _sys
            print(f"[engine] record_agent_result 失败: {e}", file=_sys.stderr)

    def submit(
        self,
        agent_name: str,
        site_id: str,
        priority: int = 5,
        event_id: Optional[str] = None,
        lookback_days: int = 7,
        upstream_output: Optional[dict] = None,
    ) -> str:
        """投递任务,返回 task_id"""
        self._seq_counter += 1
        task = Task(
            priority=priority,
            seq=self._seq_counter,
            task_id=str(uuid.uuid4())[:8],
            agent_name=agent_name,
            site_id=site_id,
            event_id=event_id,
            lookback_days=lookback_days,
            upstream_output=upstream_output,
        )
        heappush(self._queue, task)
        self._tasks[task.task_id] = task
        self._persist_task_upsert(task)
        self._persist_task_transition(task, TaskStatus.PENDING, "created")
        return task.task_id

    def next(self) -> Optional[Task]:
        """取下一个待执行任务,标记 running"""
        if not self._queue:
            return None
        task = heappop(self._queue)
        task.started_at = time.time()
        task.transition(TaskStatus.RUNNING, "dispatched")
        self._persist_task_upsert(task)
        self._persist_task_transition(task, TaskStatus.RUNNING, "dispatched")
        return task

    def complete(self, task_id: str, result: AgentResult) -> None:
        """任务完成,落历史"""
        task = self._tasks[task_id]
        task.finished_at = time.time()
        task.result = result

        if result.status == AgentStatus.SUCCESS:
            task.transition(TaskStatus.SUCCESS, f"agent_status={result.status.value}")
            note = f"agent_status={result.status.value}"
            new_status = TaskStatus.SUCCESS
        else:
            task.transition(TaskStatus.FAILED, f"agent_status={result.status.value}; {result.gap_reason}")
            task.error = result.gap_reason
            note = f"agent_status={result.status.value}; {result.gap_reason}"
            new_status = TaskStatus.FAILED

        # 历史继承:无论成功失败都入历史(失败也是经验)
        key = (task.site_id, task.agent_name)
        self.history.setdefault(key, []).append(result)

        # 落库
        self._persist_task_upsert(task)
        self._persist_task_transition(task, new_status, note)
        self._persist_agent_result(task, result)

    def fail(self, task_id: str, error: str) -> None:
        """任务运行时异常(非 agent 自然返回 failed)"""
        task = self._tasks[task_id]
        task.finished_at = time.time()
        task.error = error
        task.transition(TaskStatus.FAILED, f"engine_error: {error}")
        self._persist_task_upsert(task)
        self._persist_task_transition(task, TaskStatus.FAILED, f"engine_error: {error}")

    def rollback(self, task_id: str, reason: str = "") -> None:
        """MVP 占位:只改状态不真撤销;真回滚 P1"""
        task = self._tasks[task_id]
        task.transition(TaskStatus.ROLLED_BACK, reason)
        self._persist_task_upsert(task)
        self._persist_task_transition(task, TaskStatus.ROLLED_BACK, reason)

    # ─── 历史继承查询 ──────────────────────────
    def last_result(self, site_id: str, agent_name: str) -> Optional[AgentResult]:
        results = self.history.get((site_id, agent_name), [])
        return results[-1] if results else None

    def history_count(self, site_id: str, agent_name: str) -> int:
        return len(self.history.get((site_id, agent_name), []))

    # ─── 调度内省 ───────────────────────────
    def pending_count(self) -> int:
        return len(self._queue)

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[Task]:
        return list(self._tasks.values())


# ─── 进程单例 ───────────────────────────────────
_engine: Optional[TaskEngine] = None


def get_engine() -> TaskEngine:
    """MVP 进程单例;真正多进程时换 Redis-backed engine"""
    global _engine
    if _engine is None:
        _engine = TaskEngine()
    return _engine


def reset_engine() -> None:
    """测试用,清空单例"""
    global _engine
    _engine = None
