# requests/uploads/ — xlsx 上传归档目录（投手不要直接动）

**投手入口：** `https://multisite-platform.pages.dev/upload.html` 拖 xlsx 即可。

系统会通过 Cloudflare Function 把文件写到这里 → GitHub Actions 自动 ingest → 触发数据分析 agent → 重建看板。

---

## 这里是什么

- `requests/uploads/*.xlsx` — 投手刚上传、待 ingest 的 xlsx
- `requests/uploads/_done/` — ingest 完归档

## 文件名规则

系统在前端自动按 `{投手}-{日期}-{原文件名}.xlsx` 命名，无需投手手动改名。

## xlsx 表头要求

`bin/ingest_from_xlsx.py` 从第 1 行识别（中英文都接受）：
- `Ad set name` / `广告组名` — 含"广告组NN"或"组NN"识别组号
- `Amount spent` / `花费` / `已使用金额` — 花费金额
- 可选 `HVU` — 高价值用户数

表头识别失败 → 处理结果带 `error: 找不到 'Ad set name' 列`，截图发 ZJB。

## 旧的"在 GitHub 网页 Upload files"流程已废弃

5/14 ZJB 决策：投手不接触 GitHub。
