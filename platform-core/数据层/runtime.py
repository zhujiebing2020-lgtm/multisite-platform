"""platform-core/数据层/runtime.py
DataRuntime · SQLite 持久化适配器

SVG L6 职责:状态写回 · 执行日志 · 事件源

MVP 形态:
  - sqlite3 标准库,无 ORM
  - 默认 db 路径:platform-core/数据层/runtime.db(P1 可站级分库)
  - 依赖反向禁:本模块不许 import 引擎/事件/执行层
  - 写入是同步的(MVP 流量低),P1 可改异步写入 + 缓冲
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


HERE = Path(__file__).resolve().parent
DEFAULT_DB_PATH = HERE / "runtime.db"
SCHEMA_PATH = HERE / "schema.sql"


class DataRuntime:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    # ─── 连接与 schema ─────────────────────────
    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        with SCHEMA_PATH.open(encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ─── 事件 ──────────────────────────────
    def record_event(
        self,
        event_id: str,
        type: str,
        site_id: str,
        source: str,
        payload: dict,
        ts: float,
    ) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO events (event_id,type,site_id,source,payload_json,ts) VALUES (?,?,?,?,?,?)",
            (event_id, type, site_id, source, json.dumps(payload, ensure_ascii=False), ts),
        )
        conn.commit()

    def list_events(
        self,
        site_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        conn = self._connect()
        if site_id:
            rows = conn.execute(
                "SELECT * FROM events WHERE site_id=? ORDER BY ts DESC LIMIT ?",
                (site_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── 任务状态 ────────────────────────────
    def upsert_task(
        self,
        task_id: str,
        agent_name: str,
        site_id: str,
        priority: int,
        seq: int,
        event_id: Optional[str],
        status: str,
        lookback_days: int,
        created_at: float,
        started_at: Optional[float],
        finished_at: Optional[float],
        error: Optional[str],
    ) -> None:
        conn = self._connect()
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id,agent_name,site_id,priority,seq,event_id,status,
                lookback_days,created_at,started_at,finished_at,error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, agent_name, site_id, priority, seq, event_id, status,
             lookback_days, created_at, started_at, finished_at, error),
        )
        conn.commit()

    def record_task_transition(
        self,
        task_id: str,
        status: str,
        note: str,
        ts: float,
    ) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO task_state_history (task_id,status,note,ts) VALUES (?,?,?,?)",
            (task_id, status, note, ts),
        )
        conn.commit()

    # ─── Agent 执行历史 ─────────────────────
    def record_agent_result(
        self,
        task_id: str,
        site_id: str,
        agent_name: str,
        status: str,
        data: dict,
        emit_events: list[dict],
        cost: float,
        duration_ms: int,
        gap_reason: Optional[str],
        ts: Optional[float] = None,
    ) -> None:
        conn = self._connect()
        conn.execute(
            """INSERT INTO agent_history
               (task_id,site_id,agent_name,status,data_json,emit_events_json,
                cost,duration_ms,gap_reason,ts)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (task_id, site_id, agent_name, status,
             json.dumps(data, ensure_ascii=False),
             json.dumps(emit_events, ensure_ascii=False),
             cost, duration_ms, gap_reason, ts or time.time()),
        )
        conn.commit()

    def load_agent_history(
        self,
        site_id: str,
        agent_name: str,
        limit: int = 10,
    ) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            """SELECT * FROM agent_history
               WHERE site_id=? AND agent_name=?
               ORDER BY ts DESC LIMIT ?""",
            (site_id, agent_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def last_agent_result(
        self,
        site_id: str,
        agent_name: str,
    ) -> Optional[dict]:
        hist = self.load_agent_history(site_id, agent_name, limit=1)
        return hist[0] if hist else None

    # ─── 统计 ────────────────────────────
    def counts(self) -> dict[str, int]:
        conn = self._connect()
        out = {}
        for t in ("events", "tasks", "agent_history", "task_state_history"):
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return out


# ─── 进程单例 ───────────────────────────
_dr: Optional[DataRuntime] = None


def get_data_runtime() -> DataRuntime:
    global _dr
    if _dr is None:
        _dr = DataRuntime()
    return _dr


def reset_data_runtime(db_path: Optional[Path] = None) -> DataRuntime:
    """测试用:重设单例,可指定 db 路径(如 :memory: 或 tmp)"""
    global _dr
    if _dr is not None:
        _dr.close()
    _dr = DataRuntime(db_path=db_path)
    return _dr
