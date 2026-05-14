// src/api/parse-xlsx.js — 在 Worker 端解析 xlsx 并存入 D1
// 使用简化的 xlsx 解析（CSV fallback + 基础 xlsx 解码）

export async function handleUploadAndParse(request, env) {
  try {
    const pass = request.headers.get('x-pass') || '';
    if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
      return json({ error: '口令错误' }, 401);
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

    // 解析 xlsx 内容
    const binary = Uint8Array.from(atob(contentBase64), c => c.charCodeAt(0));
    const rows = parseXlsx(binary);

    if (!rows || rows.length < 2) {
      await ghPromise;
      return json({ ok: true, path, parsed: 0, message: '文件已上传但无法解析数据行' });
    }

    // 找列索引
    const header = rows[0].map(h => String(h || '').toLowerCase().trim());
    const colMap = {
      group: findCol(header, ['group', '组', 'ad_group', 'campaign']),
      date: findCol(header, ['date', '日期', 'day']),
      spend: findCol(header, ['spend', '花费', 'amount_spent', 'amount spent', 'cost']),
      hvu: findCol(header, ['hvu', 'high_value_users', 'conversions', 'results']),
      cphq: findCol(header, ['cphq', 'cost_per_hvu', 'cpa', 'cost_per_result']),
      impressions: findCol(header, ['impressions', '展示', 'impr']),
      clicks: findCol(header, ['clicks', '点击', 'link_clicks']),
    };

    if (colMap.group === -1 || colMap.spend === -1) {
      await ghPromise;
      return json({ ok: true, path, parsed: 0, message: '已上传但未找到 group/spend 列，请检查表头' });
    }

    // 解析日期：从文件名或数据中提取
    let defaultDate = extractDateFromFilename(filename) || new Date().toISOString().slice(0, 10);

    // 插入 D1
    const stmts = [];
    let parsed = 0;
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
          'INSERT INTO ad_daily (owner, site, date, group_name, spend, hvu, cphq, impressions, clicks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        ).bind(owner, site, date, groupName, spend, hvu, cphq, impressions, clicks)
      );
      parsed++;
    }

    if (stmts.length > 0) {
      // D1 batch 限制 100 条
      for (let i = 0; i < stmts.length; i += 100) {
        await env.DB.batch(stmts.slice(i, i + 100));
      }
    }

    await ghPromise;
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

  let query, params;
  if (owner) {
    query = `SELECT date, group_name, spend, hvu, cphq, impressions, clicks
             FROM ad_daily WHERE owner = ? ORDER BY date DESC, spend DESC LIMIT 500`;
    params = [owner];
  } else {
    query = `SELECT owner, date, group_name, spend, hvu, cphq, impressions, clicks
             FROM ad_daily ORDER BY date DESC, spend DESC LIMIT 1000`;
    params = [];
  }

  const stmt = owner ? env.DB.prepare(query).bind(...params) : env.DB.prepare(query);
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
