-- 广告日数据表（从投手上传的 xlsx 解析入库）
CREATE TABLE IF NOT EXISTS ad_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner TEXT NOT NULL,
  site TEXT NOT NULL,
  date TEXT NOT NULL,
  group_name TEXT NOT NULL,
  spend REAL DEFAULT 0,
  hvu INTEGER DEFAULT 0,
  cphq REAL DEFAULT 0,
  impressions INTEGER DEFAULT 0,
  clicks INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ad_daily_owner_date ON ad_daily(owner, date);
CREATE INDEX IF NOT EXISTS idx_ad_daily_site_date ON ad_daily(site, date);
