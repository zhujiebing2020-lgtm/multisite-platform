# requests/uploads/ — xlsx 上传区(投手自助 ingest)

**HZM / CHJ / HNN 把 FB 后台导出的 xlsx 直接拖到这里上传,monitor 自动 ingest。**

## 用法 · HZM 视角

### 1. 上传 xlsx
1. 打开 https://github.com/zhujiebing2020-lgtm/multisite-platform/tree/main/requests/uploads
2. 右上角 **Add file** → **Upload files**
3. 把你的 xlsx 拖到中间区域(可拖多个文件)
4. 文件名按这个格式:
   ```
   HZM-2026-05-14.xlsx
   HZM-FB-2026-05-14.xlsx     (前缀 HZM 让系统识别 owner)
   ```
5. 滚到底,Commit message 写"上传 5/14 数据",绿色按钮 **Commit changes**

### 2. xlsx 表头要求
平台从你的 xlsx 第 1 行表头识别这两列(中英文都接受):
- `Ad set name`(或 `广告组名`)— 包含"广告组NN"或"组NN"识别组号
- `Amount spent`(或 `花费`、`已使用金额`)— 花费金额
- 可选:`HVU`(高价值用户数)

## 处理流程

```
HZM 上传 HZM-2026-05-14.xlsx
   ↓ Commit
[60 秒内]
  ZJB Mac monitor scan → git pull → 看到新 xlsx
   ↓ 调 bin/ingest_from_xlsx.py
   解析 xlsx → 按组聚合 spend/hvu/cphq → 落 data/uploads/HZM-2026-05-14-xxxxxx.json
   ↓ 触发 数据分析 agent owner=HZM
   ↓ 归档 xlsx 到 _done/
   ↓ 重生成 dashboard + 自动 push
[5-10 分钟]
  HZM 刷新看板 → 看到自己当日数据
```

## 状态查看
- 处理中:文件在本目录顶层
- 处理完:自动归档到 `_done/`
- 解析后的结构化 JSON:`data/uploads/HZM-{date}-{time}.json`

## 常见问题

**Q · 上传后多久能在看板看到?**
2 分钟 monitor 处理 + 5 分钟 GitHub Pages 重渲染 ≈ 5-7 分钟。

**Q · 文件名没按规则,怎么办?**
不带 owner 前缀(HZM/CHJ/...)→ 系统标 owner=unknown,数据归不到你头上。重命名后重传。

**Q · xlsx 表头平台识别不出来?**
处理结果会有 `error: 找不到 'Ad set name' 列`。把你 xlsx 表头格式截图发 ZJB,他帮你改解析器(或你导出时勾选这两列)。

**Q · 隐私担心?**
repo 是公开的,投手数据(组号 / 花费)会进 git 历史。如果敏感:
- 选项 1:repo 改私有(需要 GitHub Pro 付费)
- 选项 2:.gitignore 加 `data/uploads/*.json`,只在本地处理(但 HZM 看不到 dashboard)
- 选项 3:加密上传(P1 工程)
