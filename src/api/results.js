// src/api/results.js — 查询 agent 执行结果

import { verifySession } from './auth.js';

export async function handleResults(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const owner = user.role === 'admin' ? null : user.sub;
  let query, params;

  if (owner) {
    query = 'SELECT id, owner, site, agent_type, status, output_summary, created_at, completed_at FROM agent_jobs WHERE owner = ? ORDER BY created_at DESC LIMIT 50';
    params = [owner];
  } else {
    query = 'SELECT id, owner, site, agent_type, status, output_summary, created_at, completed_at FROM agent_jobs ORDER BY created_at DESC LIMIT 100';
    params = [];
  }

  const stmt = owner
    ? env.DB.prepare(query).bind(...params)
    : env.DB.prepare(query);
  const { results } = await stmt.all();

  return json({ ok: true, jobs: results });
}

export async function handleResultDetail(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const url = new URL(request.url);
  const jobId = url.pathname.replace('/api/results/', '');

  const job = await env.DB.prepare('SELECT * FROM agent_jobs WHERE id = ?').bind(jobId).first();
  if (!job) return json({ error: '任务不存在' }, 404);

  if (user.role !== 'admin' && job.owner !== user.sub) {
    return json({ error: '无权查看' }, 403);
  }

  return json({ ok: true, job });
}

export async function handleClearPending(request, env) {
  const user = await verifySession(request, env);
  if (!user || user.role !== 'admin') return json({ error: '需要管理员权限' }, 403);

  const result = await env.DB.prepare(
    "UPDATE agent_jobs SET status = 'failed', output_summary = '超时自动清除' WHERE status = 'pending' AND created_at < datetime('now', '-24 hours')"
  ).run();

  return json({ ok: true, count: result.meta?.changes || 0 });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
