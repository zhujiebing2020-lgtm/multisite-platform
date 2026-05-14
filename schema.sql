-- z-jb.com 统一平台 · D1 Schema v1

-- 用户/权限表（口令分级）
CREATE TABLE IF NOT EXISTS users (
  passcode TEXT PRIMARY KEY,
  role TEXT NOT NULL,
  owner_code TEXT NOT NULL,
  display_name TEXT,
  sites TEXT NOT NULL DEFAULT '["elysianu"]',
  permissions TEXT NOT NULL DEFAULT '["upload","trigger_agent","view_results"]',
  created_at TEXT DEFAULT (datetime('now'))
);

-- Agent 任务表
CREATE TABLE IF NOT EXISTS agent_jobs (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  site TEXT NOT NULL,
  agent_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  input_ref TEXT,
  output_summary TEXT,
  output_full TEXT,
  github_path TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  completed_at TEXT
);

-- 数据回流湖（后续用）
CREATE TABLE IF NOT EXISTS data_lake (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  site TEXT NOT NULL,
  data_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);

-- 初始用户数据
INSERT OR IGNORE INTO users (passcode, role, owner_code, display_name, sites, permissions) VALUES
  ('xiuxiu', 'pitcher', 'HZM', '梓铭', '["elysianu"]', '["upload","trigger_agent","view_results"]'),
  ('crave2026', 'admin', 'ZJB', 'ZJB', '["*"]', '["*"]');
