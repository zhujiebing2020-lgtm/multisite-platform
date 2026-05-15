// src/api/knowledge.js — 知识库管理

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleKnowledge(request, env) {
  const user = await verifySession(request, env);
  if (!user || user.role !== 'admin') return json({ error: '需要管理员权限' }, 403);

  if (request.method === 'GET') {
    const url = new URL(request.url);
    const type = url.searchParams.get('type');
    let sql = 'SELECT * FROM knowledge_entries';
    let params = [];
    if (type) { sql += ' WHERE type = ?'; params.push(type); }
    sql += ' ORDER BY created_at DESC LIMIT 100';
    const rows = params.length
      ? await env.DB.prepare(sql).bind(...params).all()
      : await env.DB.prepare(sql).all();
    return json({ ok: true, items: rows.results });
  }

  return json({ error: 'method not allowed' }, 405);
}

export async function handleKnowledgeToRule(request, env, id) {
  const user = await verifySession(request, env);
  if (!user || user.role !== 'admin') return json({ error: '需要管理员权限' }, 403);

  const entry = await env.DB.prepare('SELECT * FROM knowledge_entries WHERE id = ?').bind(id).first();
  if (!entry) return json({ error: '不存在' }, 404);

  const now = new Date().toISOString();
  await env.DB.prepare(
    'UPDATE knowledge_entries SET status = ?, validated_at = ? WHERE id = ?'
  ).bind('confirmed', now, id).run();

  return json({ ok: true, message: '已转化为规则' });
}
