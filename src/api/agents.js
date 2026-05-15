// src/api/agents.js — Agent 状态查询 + 手动触发

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleAgentsStatus(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const rows = await env.DB.prepare(
    `SELECT agent_type, status, MAX(created_at) as last_run, COUNT(*) as total_runs
     FROM agent_jobs GROUP BY agent_type ORDER BY last_run DESC`
  ).all();

  return json({ ok: true, agents: rows.results });
}

export async function handleAgentTrigger(request, env, agentId) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { handleTriggerAgent } = await import('./trigger-agent.js');
  const fakeReq = new Request(request.url, {
    method: 'POST',
    headers: request.headers,
    body: JSON.stringify({ agent_type: agentId, site: 'elysianu', params: {} }),
  });
  return handleTriggerAgent(fakeReq, env);
}

export async function handleCrossSiteSummary(request, env) {
  const user = await verifySession(request, env);
  if (!user || user.role !== 'admin') return json({ error: '需要管理员权限' }, 403);

  const spend = await env.DB.prepare(
    "SELECT site, SUM(spend) as total_spend, SUM(hvu) as total_hvu, COUNT(DISTINCT group_name) as groups FROM ad_daily WHERE site != '_test' GROUP BY site"
  ).all();

  const recs = await env.DB.prepare(
    "SELECT status, COUNT(*) as cnt FROM agent_recommendations GROUP BY status"
  ).all();

  return json({
    ok: true,
    sites: spend.results,
    recommendations_by_status: recs.results,
  });
}
