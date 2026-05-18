-- Crave AI Dashboard tables
-- intake_reports: 承接端分析报告
CREATE TABLE IF NOT EXISTS intake_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  submitted_by TEXT,
  overall_health TEXT,
  health_note TEXT,
  payload TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_intake_date ON intake_reports(date);

-- dashboard_cards: 通用卡片容器
CREATE TABLE IF NOT EXISTS dashboard_cards (
  card_id TEXT PRIMARY KEY,
  card_type TEXT NOT NULL,
  channel TEXT,
  data_date TEXT,
  payload TEXT NOT NULL,
  last_updated TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cards_type_date ON dashboard_cards(card_type, data_date);
