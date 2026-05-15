// src/api/recommendations.js — 建议卡片 CRUD

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleRecommendations(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const url = new URL(request.url);

  if (request.method === 'GET') {
    const site = url.searchParams.get('site');
    const status = url.searchParams.get('status');
    const agent = url.searchParams.get('agent');
    let conditions = ['1=1'];
    let params = [];
    if (site) { conditions.push('site = ?'); params.push(site); }
    if (status) { conditions.push('status = ?'); params.push(status); }
    if (agent) { conditions.push('agent_id = ?'); params.push(agent); }
    if (user.role === 'pitcher') { conditions.push('(confirmed_by = ? OR confirmed_by IS NULL)'); params.push(user.sub); }

    const rows = await env.DB.prepare(
      `SELECT * FROM agent_recommendations WHERE ${conditions.join(' AND ')} ORDER BY created_at DESC LIMIT 100`
    ).bind(...params).all();
    return json({ ok: true, items: rows.results });
  }

  return json({ error: 'method not allowed' }, 405);
}

export async function handleRecommendationUpdate(request, env, id) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  if (request.method === 'PUT') {
    const body = await request.json();
    const rec = await env.DB.prepare('SELECT * FROM agent_recommendations WHERE id = ?').bind(id).first();
    if (!rec) return json({ error: '不存在' }, 404);

    const now = new Date().toISOString();

    if (body.action === 'confirm') {
      await env.DB.prepare(
        'UPDATE agent_recommendations SET status = ?, pitcher_action = ?, confirmed_by = ?, confirmed_at = ? WHERE id = ?'
      ).bind('confirmed', 'confirmed', user.sub, now, id).run();
    } else if (body.action === 'reject') {
      if (!body.reason) return json({ error: '拒绝必须填写原因' }, 400);
      await env.DB.prepare(
        'UPDATE agent_recommendations SET status = ?, pitcher_action = ?, rejection_reason = ?, confirmed_by = ?, confirmed_at = ? WHERE id = ?'
      ).bind('rejected', 'rejected', body.reason, user.sub, now, id).run();
    } else if (body.action === 'executed') {
      await env.DB.prepare(
        'UPDATE agent_recommendations SET status = ?, executed_at = ? WHERE id = ?'
      ).bind('executed', now, id).run();
    }

    return json({ ok: true });
  }

  return json({ error: 'method not allowed' }, 405);
}
