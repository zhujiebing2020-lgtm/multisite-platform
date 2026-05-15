// src/api/knowledge.js — 知识库管理

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleKnowledge(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

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

export async function handleKnowledgeAdd(request, env) {
  const user = await verifySession(request, env);
  if (!user || user.role !== 'admin') return json({ error: '需要管理员权限' }, 403);

  const { type, content, status } = await request.json();
  if (!type || !content) return json({ error: '缺少 type 或 content' }, 400);

  await env.DB.prepare(
    'INSERT INTO knowledge_entries (type, content, status, source, created_at) VALUES (?, ?, ?, ?, ?)'
  ).bind(type, content, status || 'hypothesis', 'manual', new Date().toISOString()).run();

  return json({ ok: true });
}

export async function handleScripts(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  if (request.method === 'GET') {
    const rows = await env.DB.prepare('SELECT * FROM scripts ORDER BY created_at DESC LIMIT 100').all();
    return json({ ok: true, items: rows.results });
  }

  if (request.method === 'POST') {
    const { items } = await request.json();
    if (!items || !items.length) return json({ error: '无数据' }, 400);
    for (const s of items) {
      await env.DB.prepare(
        'INSERT INTO scripts (title, tags, product, emotion, scene) VALUES (?, ?, ?, ?, ?)'
      ).bind(s.title || '', s.tags || '', s.product || '', s.emotion || '', s.scene || '').run();
    }
    return json({ ok: true, count: items.length });
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
