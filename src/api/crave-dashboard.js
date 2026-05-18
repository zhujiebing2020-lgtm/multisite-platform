import { triggerDownstream, triggerIntakeDownstream } from './crave-triggers.js';

export async function handleCraveDashboard(request, env, path) {
  const url = new URL(request.url);
  const method = request.method;

  if (path === '/api/crave/cards' && method === 'GET') {
    const type = url.searchParams.get('type');
    const channel = url.searchParams.get('channel');
    const after = url.searchParams.get('after');
    let sql = 'SELECT card_id, card_type, channel, data_date, payload, last_updated FROM dashboard_cards WHERE 1=1';
    const params = [];
    if (type) { sql += ' AND card_type = ?'; params.push(type); }
    if (channel) { sql += ' AND channel = ?'; params.push(channel); }
    if (after) { sql += ' AND data_date >= ?'; params.push(after); }
    sql += ' ORDER BY data_date DESC, card_id';
    const { results } = await env.DB.prepare(sql).bind(...params).all();
    const cards = {};
    for (const r of results) cards[r.card_id] = JSON.parse(r.payload);
    return Response.json(cards);
  }

  if (path === '/api/crave/cards' && method === 'POST') {
    const body = await request.json();
    const items = Array.isArray(body) ? body : [body];
    const stmt = env.DB.prepare(
      `INSERT OR REPLACE INTO dashboard_cards (card_id, card_type, channel, data_date, payload, last_updated)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    );
    const batch = items.map(item => {
      const meta = item.meta || {};
      return stmt.bind(meta.card_id, meta.card_type || '', meta.channel || '', meta.data_date || meta.last_updated || '', JSON.stringify(item));
    });
    await env.DB.batch(batch);
    const hasDaily = items.some(i => (i.meta || {}).card_type === 'daily_dashboard');
    if (hasDaily) await triggerDownstream(env, 'daily_dashboard');
    return Response.json({ ok: true, count: items.length });
  }

  if (path === '/api/crave/intake' && method === 'GET') {
    const date = url.searchParams.get('date');
    let row;
    if (date) {
      row = await env.DB.prepare('SELECT payload FROM intake_reports WHERE date = ?').bind(date).first();
    } else {
      row = await env.DB.prepare('SELECT payload FROM intake_reports ORDER BY date DESC LIMIT 1').first();
    }
    if (!row) return Response.json(null);
    return Response.json(JSON.parse(row.payload));
  }

  if (path === '/api/crave/intake' && method === 'POST') {
    const body = await request.json();
    await env.DB.prepare(
      `INSERT OR REPLACE INTO intake_reports (date, submitted_by, overall_health, health_note, payload)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(body.date, body.submitted_by || '', body.overall_health || '', body.health_note || '', JSON.stringify(body)).run();
    await triggerIntakeDownstream(env, body);
    return Response.json({ ok: true });
  }

  if (path === '/api/crave/ad-history' && method === 'GET') {
    const days = parseInt(url.searchParams.get('days') || '30');
    const { results } = await env.DB.prepare(
      `SELECT group_name, owner, date, spend, hvu, cphq FROM ad_daily
       WHERE date >= date('now', '-' || ? || ' days') ORDER BY date DESC, group_name`
    ).bind(days).all();
    return Response.json(results);
  }

  if (path === '/api/crave/sync' && method === 'POST') {
    const body = await request.json();
    let counts = { cards: 0, intake: 0 };

    if (body.cards) {
      const entries = Object.entries(body.cards);
      const stmt = env.DB.prepare(
        `INSERT OR REPLACE INTO dashboard_cards (card_id, card_type, channel, data_date, payload, last_updated)
         VALUES (?, ?, ?, ?, ?, datetime('now'))`
      );
      const batchSize = 50;
      for (let i = 0; i < entries.length; i += batchSize) {
        const chunk = entries.slice(i, i + batchSize);
        await env.DB.batch(chunk.map(([id, card]) => {
          const meta = card.meta || {};
          return stmt.bind(id, meta.card_type || '', meta.channel || '', meta.data_date || meta.last_updated || '', JSON.stringify(card));
        }));
      }
      counts.cards = entries.length;
    }

    if (body.intake) {
      const items = Array.isArray(body.intake) ? body.intake : [body.intake];
      const stmt = env.DB.prepare(
        `INSERT OR REPLACE INTO intake_reports (date, submitted_by, overall_health, health_note, payload)
         VALUES (?, ?, ?, ?, ?)`
      );
      await env.DB.batch(items.map(r => stmt.bind(r.date, r.submitted_by || '', r.overall_health || '', r.health_note || '', JSON.stringify(r))));
      counts.intake = items.length;
    }

    return Response.json({ ok: true, counts });
  }

  return new Response('Not Found', { status: 404 });
}
