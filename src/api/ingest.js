// src/api/ingest.js — 接收前端解析好的数据直接入库

import { logOp } from './admin.js';
import { verifySession } from './auth.js';

export async function handleIngest(request, env) {
  try {
    const session = await verifySession(request, env);
    if (!session) {
      const pass = request.headers.get('x-pass') || '';
      if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
        return json({ error: '未登录或口令错误' }, 401);
      }
    }

    const { site, records } = await request.json();
    if (!site || !records || !Array.isArray(records) || records.length === 0) {
      return json({ error: '缺 site 或 records 为空' }, 400);
    }

    const stmts = [];
    for (const r of records) {
      if (!r.group_name || (!r.spend && !r.hvu)) continue;
      stmts.push(
        env.DB.prepare(
          `INSERT INTO ad_daily (owner, site, date, group_name, spend, hvu, cphq) VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(site, date, group_name) DO UPDATE SET owner=excluded.owner, spend=CASE WHEN excluded.spend>0 THEN excluded.spend ELSE ad_daily.spend END, hvu=CASE WHEN excluded.hvu>0 THEN excluded.hvu ELSE ad_daily.hvu END, cphq=excluded.cphq`
        ).bind(
          r.owner || 'unknown',
          site,
          r.date || new Date().toISOString().slice(0, 10),
          r.group_name,
          r.spend || 0,
          r.hvu || 0,
          r.cphq || 0
        )
      );
    }

    let ingested = 0;
    if (stmts.length > 0) {
      for (let i = 0; i < stmts.length; i += 100) {
        await env.DB.batch(stmts.slice(i, i + 100));
      }
      ingested = stmts.length;
    }

    await logOp(env, records[0]?.owner || 'unknown', 'upload', { site, rows: ingested }, request);

    // 合约四B：数据复查 — 行数一致性
    const sourceRows = records.length;
    const validRows = records.filter(r => r.group_name && (r.spend || r.hvu)).length;
    const checkResult = ingested === validRows ? 'pass' : 'fail';
    await logOp(env, 'SYSTEM', 'data_check', {
      type: 'row_consistency',
      source_rows: sourceRows,
      valid_rows: validRows,
      ingested,
      result: checkResult,
      detail: checkResult === 'pass'
        ? `✅ 源${sourceRows}行 → 有效${validRows}行 → 入库${ingested}行，一致`
        : `⚠️ 源${sourceRows}行 → 有效${validRows}行 → 入库${ingested}行，不一致`
    }, request);

    return json({ ok: true, ingested });
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
