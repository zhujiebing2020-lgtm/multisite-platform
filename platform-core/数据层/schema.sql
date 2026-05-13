-- platform-core/数据层/schema.sql
-- SVG L6 Data Runtime · 状态写回 / 执行日志 / 事件源
-- 对应内存结构:EventBus._log / TaskEngine._tasks / TaskEngine.history

PRAGMA foreign_keys = ON;

-- 事件流水(EventBus.log 的持久化)
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    site_id      TEXT NOT NULL,
    source       TEXT,
    payload_json TEXT,
    ts           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_site_ts ON events(site_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);

-- 任务状态流(每次 transition 追加一行,tasks 是最新状态快照)
CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    agent_name     TEXT NOT NULL,
    site_id        TEXT NOT NULL,
    priority       INTEGER NOT NULL,
    seq            INTEGER NOT NULL,
    event_id       TEXT,
    status         TEXT NOT NULL,
    lookback_days  INTEGER,
    created_at     REAL NOT NULL,
    started_at     REAL,
    finished_at    REAL,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_site_agent ON tasks(site_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS task_state_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL,
    status     TEXT NOT NULL,
    note       TEXT,
    ts         REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);
CREATE INDEX IF NOT EXISTS idx_task_state_history_task ON task_state_history(task_id);

-- Agent 执行历史(历史继承的持久化,对应 TaskEngine.history)
CREATE TABLE IF NOT EXISTS agent_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    site_id         TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    status          TEXT NOT NULL,
    data_json       TEXT,
    emit_events_json TEXT,
    cost            REAL,
    duration_ms     INTEGER,
    gap_reason      TEXT,
    ts              REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_history_site_agent_ts
    ON agent_history(site_id, agent_name, ts DESC);
