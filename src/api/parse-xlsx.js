// src/api/parse-xlsx.js — 在 Worker 端解析 xlsx 并存入 D1
// 使用简化的 xlsx 解析（CSV fallback + 基础 xlsx 解码）

import { logOp } from './admin.js';
import { verifySession } from './auth.js';

export async function handleUploadAndParse(request, env) {
  try {
    // 支持 session cookie 或 x-pass 认证
    const session = await verifySession(request, env);
    if (!session) {
      const pass = request.headers.get('x-pass') || '';
      if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
        return json({ error: '未登录或口令错误' }, 401);
      }
    }

    const { filename, contentBase64, owner, site, channel } = await request.json();
    if (!filename || !contentBase64 || !owner || !site) {
      return json({ error: '缺必填字段' }, 400);
    }

    // 同时推到 GitHub（保留原有逻辑）
    const path = `requests/uploads/${filename}`;
    const ghPath = path.split('/').map(encodeURIComponent).join('/');
    const ghPromise = fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/contents/${ghPath}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'multisite-platform-worker',
      },
      body: JSON.stringify({
        message: `upload: ${owner}/${site}/${channel || 'FB'} ${filename}`,
        content: contentBase64,
        branch: 'main',
      }),
    });

    // HVU JSON 文件处理
    if (filename.toLowerCase().endsWith('.json')) {
      const binary = Uint8Array.from(atob(contentBase64), c => c.charCodeAt(0));
      const text = new TextDecoder().decode(binary);
      const data = JSON.parse(text);
      const sessions = data.sessions || [];
      const date = extractDateFromFilename(filename) || new Date().toISOString().slice(0, 10);

      // 查已有组名，按编号建映射
      const existing = await env.DB.prepare('SELECT DISTINCT group_name FROM ad_daily WHERE site=?').bind(site).all();
      const nameMap = {};
      for (const r of existing.results) {
        const m = r.group_name.match(/^组(\d+)/);
        if (m) nameMap[m[1]] = r.group_name;
      }

      const byGroup = {};
      for (const s of sessions) {
        const task = s.linkedTask || {};
        const name = task.name || '';
        const m = name.match(/广告组(\d+)/);
        if (!m) continue;
        const num = m[1];
        const key = nameMap[num] || `组${num}`;
        if (!byGroup[key]) byGroup[key] = 0;
        byGroup[key]++;
      }
      const stmts = [];
      for (const [group, hvu] of Object.entries(byGroup)) {
        stmts.push(env.DB.prepare(
          `INSERT INTO ad_daily (owner, site, date, group_name, hvu) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(site, date, group_name) DO UPDATE SET hvu=excluded.hvu, cphq=CASE WHEN ad_daily.spend>0 THEN round(ad_daily.spend*1.0/excluded.hvu,2) ELSE 0 END`
        ).bind(owner, site, date, group, hvu));
      }
      if (stmts.length > 0) {
        await env.DB.batch(stmts);
      }
      await ghPromise;
      await logOp(env, owner, 'upload', { site, filename, type: 'hvu_json', groups: Object.keys(byGroup).length }, request);
      return json({ ok: true, path, parsed: Object.keys(byGroup).length, message: `✓ HVU JSON 解析完成，${Object.keys(byGroup).length} 个组` });
    }

    // 解析 xlsx 内容
    const binary = Uint8Array.from(atob(contentBase64), c => c.charCodeAt(0));
    let rows = parseXlsx(binary);

    if (!rows || rows.length < 2) {
      await ghPromise;
      return json({ ok: true, path, parsed: 0, message: '文件已上传但无法解析数据行' });
    }

    // 检测格式：横向看板格式 vs 标准纵向格式
    const header = rows[0].map(h => String(h || '').trim());
    let parsed = 0;
    let defaultDate = extractDateFromFilename(filename) || new Date().toISOString().slice(0, 10);
    const stmts = [];

    // 检测原始 FB 格式（广告组XX：开头，按年龄/性别拆行，需聚合）
    if (isRawFbFormat(header, rows)) {
      const spendCol = findCol(header.map(h=>h.toLowerCase()), ['已花费金额', 'amount spent', 'จำนวนเงินที่ใช้จ่ายไป']);
      const adsetCol = findCol(header.map(h=>h.toLowerCase()), ['广告组名称', 'ad set name', 'ชื่อชุดโฆษณา']);
      if (spendCol === -1 || adsetCol === -1) {
        await ghPromise;
        return json({ ok: true, path, parsed: 0, message: '已上传但未找到广告组/花费列' });
      }
      const agg = {};
      for (let i = 1; i < rows.length; i++) {
        const adset = String(rows[i][adsetCol] || '').trim();
        const m = adset.match(/广告组(\d+)/);
        if (!m) continue;
        const key = `组${m[1]}`;
        if (!agg[key]) agg[key] = 0;
        agg[key] += parseNum(rows[i][spendCol]);
      }
      for (const [group, spend] of Object.entries(agg)) {
        if (spend <= 0) continue;
        stmts.push(env.DB.prepare(
          `INSERT INTO ad_daily (owner, site, date, group_name, spend) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(site, date, group_name) DO UPDATE SET spend=excluded.spend, cphq=CASE WHEN ad_daily.hvu>0 THEN round(excluded.spend*1.0/ad_daily.hvu,2) ELSE 0 END`
        ).bind(owner, site, defaultDate, group, round2(spend)));
        parsed++;
      }
    } else if (isHorizontalFormat(header)) {
      // 横向看板格式：行=组，列=日期，单元格=$spend/hvu/$cphq
      const dateColumns = [];
      for (let c = 3; c < header.length; c++) {
        const dateStr = parseDateHeader(header[c]);
        if (dateStr) dateColumns.push({ col: c, date: dateStr });
      }

      for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        const groupName = String(row[0] || '').trim();
        const rowOwner = String(row[1] || '').trim() || owner;
        if (!groupName || groupName === '合计' || groupName.includes('图例')) continue;

        for (const { col, date } of dateColumns) {
          const cell = String(row[col] || '').trim();
          if (!cell || cell === '—' || cell === '') continue;
          const parsed_cell = parseCellValue(cell);
          if (!parsed_cell || (parsed_cell.spend === 0 && parsed_cell.hvu === 0)) continue;

          stmts.push(
            env.DB.prepare(
              `INSERT INTO ad_daily (owner, site, date, group_name, spend, hvu, cphq) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(site, date, group_name) DO UPDATE SET spend=excluded.spend, hvu=excluded.hvu, cphq=excluded.cphq`
            ).bind(rowOwner, site, date, groupName, parsed_cell.spend, parsed_cell.hvu, parsed_cell.cphq)
          );
          parsed++;
        }
      }
    } else {
      // 标准纵向格式：每行一条记录
      const colMap = {
        group: findCol(header.map(h=>h.toLowerCase()), ['group', '组', '广告组', 'ad_group', 'campaign']),
        date: findCol(header.map(h=>h.toLowerCase()), ['date', '日期', 'day']),
        spend: findCol(header.map(h=>h.toLowerCase()), ['spend', '花费', 'amount_spent', 'amount spent', 'cost']),
        hvu: findCol(header.map(h=>h.toLowerCase()), ['hvu', 'high_value_users', 'conversions', 'results']),
        cphq: findCol(header.map(h=>h.toLowerCase()), ['cphq', 'cost_per_hvu', 'cpa', 'cost_per_result']),
        impressions: findCol(header.map(h=>h.toLowerCase()), ['impressions', '展示', 'impr']),
        clicks: findCol(header.map(h=>h.toLowerCase()), ['clicks', '点击', 'link_clicks']),
      };

      if (colMap.group === -1 || colMap.spend === -1) {
        await ghPromise;
        return json({ ok: true, path, parsed: 0, message: '已上传但未找到 group/spend 列，请检查表头: ' + header.slice(0,5).join(', ') });
      }

      for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        const groupName = String(row[colMap.group] || '').trim();
        if (!groupName) continue;
        const date = colMap.date !== -1 ? normalizeDate(row[colMap.date]) || defaultDate : defaultDate;
        const spend = parseNum(row[colMap.spend]);
        const hvu = Math.round(parseNum(row[colMap.hvu]));
        const cphq = parseNum(row[colMap.cphq]);
        const impressions = Math.round(parseNum(colMap.impressions !== -1 ? row[colMap.impressions] : 0));
        const clicks = Math.round(parseNum(colMap.clicks !== -1 ? row[colMap.clicks] : 0));
        if (spend === 0 && hvu === 0 && impressions === 0) continue;

        stmts.push(
          env.DB.prepare(
            `INSERT INTO ad_daily (owner, site, date, group_name, spend, hvu, cphq, impressions, clicks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(site, date, group_name) DO UPDATE SET spend=excluded.spend, hvu=CASE WHEN excluded.hvu>0 THEN excluded.hvu ELSE ad_daily.hvu END, cphq=excluded.cphq, impressions=excluded.impressions, clicks=excluded.clicks`
          ).bind(owner, site, date, groupName, spend, hvu, cphq, impressions, clicks)
        );
        parsed++;
      }
    }

    if (stmts.length > 0) {
      for (let i = 0; i < stmts.length; i += 100) {
        await env.DB.batch(stmts.slice(i, i + 100));
      }
    }

    await ghPromise;
    if (parsed > 0) await logOp(env, owner, 'upload', { site, filename, rows: parsed }, request);
    return json({ ok: true, path, parsed, date: defaultDate, message: `✓ 已解析 ${parsed} 条广告组数据` });
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

// 查询看板数据
export async function handleDashboard(request, env) {
  const { verifySession } = await import('./auth.js');
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const url = new URL(request.url);
  const days = parseInt(url.searchParams.get('days') || '7');
  const owner = user.role === 'admin' ? url.searchParams.get('owner') || null : user.sub;
  const site = url.searchParams.get('site') || null;

  let query, params = [];
  let conditions = ["site != '_test'"];
  if (owner) { conditions.push('owner = ?'); params.push(owner); }
  if (site) { conditions.push('site = ?'); params.push(site); }
  const where = conditions.join(' AND ');

  query = `SELECT owner, date, group_name, spend, hvu, cphq, impressions, clicks
           FROM ad_daily WHERE ${where} ORDER BY date DESC, spend DESC LIMIT 1000`;

  const stmt = params.length ? env.DB.prepare(query).bind(...params) : env.DB.prepare(query);
  const { results } = await stmt.all();

  // 汇总
  const dates = [...new Set(results.map(r => r.date))].sort().reverse().slice(0, days);
  const latestDate = dates[0] || null;
  const latestRows = results.filter(r => r.date === latestDate);
  const totalSpend = latestRows.reduce((s, r) => s + (r.spend || 0), 0);
  const totalHvu = latestRows.reduce((s, r) => s + (r.hvu || 0), 0);
  const avgCphq = totalHvu > 0 ? totalSpend / totalHvu : 0;

  // 按日汇总趋势
  const daily = dates.map(d => {
    const dayRows = results.filter(r => r.date === d);
    return {
      date: d,
      spend: dayRows.reduce((s, r) => s + (r.spend || 0), 0),
      hvu: dayRows.reduce((s, r) => s + (r.hvu || 0), 0),
      groups: dayRows.length,
    };
  });

  return json({
    ok: true,
    latest_date: latestDate,
    summary: { spend: round2(totalSpend), hvu: totalHvu, cphq: round2(avgCphq), groups: latestRows.length },
    daily,
    groups: latestRows.map(r => ({ name: r.group_name, spend: round2(r.spend), hvu: r.hvu, cphq: round2(r.cphq) })),
  });
}

// --- xlsx 解析（简化版，处理 xlsx zip 格式）---
function parseXlsx(data) {
  try {
    // 尝试作为 ZIP (xlsx) 解析
    const files = unzip(data);
    if (files && files['xl/worksheets/sheet1.xml']) {
      return parseSheet(files['xl/worksheets/sheet1.xml'], files['xl/sharedStrings.xml']);
    }
  } catch (e) {}

  // fallback: 尝试作为 CSV/TSV
  try {
    const text = new TextDecoder().decode(data);
    if (text.includes(',') || text.includes('\t')) {
      const sep = text.includes('\t') ? '\t' : ',';
      return text.trim().split('\n').map(line => line.split(sep).map(c => c.replace(/^"|"$/g, '').trim()));
    }
  } catch (e) {}
  return null;
}

function unzip(data) {
  const files = {};
  let pos = 0;
  while (pos < data.length - 4) {
    if (data[pos] === 0x50 && data[pos+1] === 0x4B && data[pos+2] === 0x03 && data[pos+3] === 0x04) {
      const nameLen = data[pos+26] | (data[pos+27] << 8);
      const extraLen = data[pos+28] | (data[pos+29] << 8);
      const compMethod = data[pos+8] | (data[pos+9] << 8);
      const compSize = data[pos+18] | (data[pos+19] << 8) | (data[pos+20] << 16) | (data[pos+21] << 24);
      const uncompSize = data[pos+22] | (data[pos+23] << 8) | (data[pos+24] << 16) | (data[pos+25] << 24);
      const name = new TextDecoder().decode(data.slice(pos+30, pos+30+nameLen));
      const dataStart = pos + 30 + nameLen + extraLen;

      if (compMethod === 0) {
        files[name] = new TextDecoder().decode(data.slice(dataStart, dataStart + uncompSize));
      } else if (compMethod === 8) {
        try {
          const compressed = data.slice(dataStart, dataStart + compSize);
          const ds = new DecompressionStream('raw');
          // Workers 支持 DecompressionStream，但同步解析更复杂
          // 简化：存 raw 后面用 streaming 解
          files[name] = null; // 标记需要解压
          files['_raw_' + name] = compressed;
        } catch (e) {}
      }
      pos = dataStart + compSize;
    } else {
      pos++;
    }
  }
  return files;
}

function parseSheet(xml, sharedStrings) {
  if (!xml) return null;
  // 简化的 XML 解析
  const strings = [];
  if (sharedStrings) {
    const matches = sharedStrings.matchAll(/<t[^>]*>([^<]*)<\/t>/g);
    for (const m of matches) strings.push(m[1]);
  }

  const rows = [];
  const rowMatches = xml.matchAll(/<row[^>]*>(.*?)<\/row>/gs);
  for (const rm of rowMatches) {
    const cells = [];
    const cellMatches = rm[1].matchAll(/<c[^>]*(?:t="([^"]*)")?[^>]*>(?:<v>([^<]*)<\/v>)?/g);
    for (const cm of cellMatches) {
      const type = cm[1];
      const val = cm[2] || '';
      if (type === 's') cells.push(strings[parseInt(val)] || val);
      else cells.push(val);
    }
    rows.push(cells);
  }
  return rows.length > 0 ? rows : null;
}

// --- 原始 FB 格式检测 ---
function isRawFbFormat(header, rows) {
  const h = header.map(s => (s || '').toLowerCase()).join(' ');
  if (h.includes('广告组名称') || h.includes('ad set name') || h.includes('ชื่อชุดโฆษณา')) {
    // 确认数据行含"广告组XX"
    for (let i = 1; i < Math.min(rows.length, 5); i++) {
      const row = rows[i] || [];
      if (row.some(c => /广告组\d+/.test(String(c || '')))) return true;
    }
  }
  return false;
}

// --- 横向看板格式检测和解析 ---
function isHorizontalFormat(header) {
  // 如果前几列是 广告组/投手/落地页，后面是日期格式，就是横向格式
  const first = (header[0] || '').toLowerCase();
  if (first.includes('广告组') || first.includes('组') || first === 'group') {
    // 检查第4列开始是否像日期
    for (let i = 3; i < Math.min(header.length, 8); i++) {
      if (parseDateHeader(header[i])) return true;
    }
  }
  return false;
}

function parseDateHeader(h) {
  if (!h) return null;
  const s = String(h).trim();
  // 格式: "4/5" or "5/13" or "2026-05-13"
  const m = s.match(/^(\d{1,2})\/(\d{1,2})$/);
  if (m) {
    const month = m[1].padStart(2, '0');
    const day = m[2].padStart(2, '0');
    return `2026-${month}-${day}`;
  }
  const m2 = s.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (m2) return `${m2[1]}-${m2[2].padStart(2,'0')}-${m2[3].padStart(2,'0')}`;
  return null;
}

function parseCellValue(cell) {
  // 格式: "$13.95/3/$4.65" = spend/hvu/cphq
  // 或: "$13.95/0/—"
  if (!cell || cell === '—') return null;
  const parts = cell.split('/');
  if (parts.length >= 2) {
    const spend = parseNum(parts[0]);
    const hvu = Math.round(parseNum(parts[1]));
    const cphq = parts.length >= 3 ? parseNum(parts[2]) : (hvu > 0 ? spend / hvu : 0);
    return { spend, hvu, cphq: Math.round(cphq * 100) / 100 };
  }
  // 单个数字可能是 spend
  const n = parseNum(cell);
  if (n > 0) return { spend: n, hvu: 0, cphq: 0 };
  return null;
}

// --- 工具函数 ---
function findCol(header, aliases) {
  for (const a of aliases) {
    const idx = header.indexOf(a);
    if (idx !== -1) return idx;
  }
  for (let i = 0; i < header.length; i++) {
    for (const a of aliases) {
      if (header[i].includes(a)) return i;
    }
  }
  return -1;
}

function parseNum(v) {
  if (v === null || v === undefined || v === '') return 0;
  const n = parseFloat(String(v).replace(/[$,¥€]/g, ''));
  return isNaN(n) ? 0 : n;
}

function normalizeDate(v) {
  if (!v) return null;
  const s = String(v).trim();
  const m = s.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`;
  return null;
}

function extractDateFromFilename(name) {
  const m = name.match(/(\d{4})[-_]?(\d{2})[-_]?(\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  const m2 = name.match(/(\d{1,2})[-._](\d{1,2})/);
  if (m2) return `2026-${m2[1].padStart(2,'0')}-${m2[2].padStart(2,'0')}`;
  return null;
}

function round2(n) { return Math.round(n * 100) / 100; }

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
