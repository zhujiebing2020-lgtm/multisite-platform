// src/api/ingest.js — 接收前端解析好的数据直接入库

export async function handleIngest(request, env) {
  try {
    const pass = request.headers.get('x-pass') || '';
    if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
      return json({ error: '口令错误' }, 401);
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
          'INSERT INTO ad_daily (owner, site, date, group_name, spend, hvu, cphq) VALUES (?, ?, ?, ?, ?, ?, ?)'
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
