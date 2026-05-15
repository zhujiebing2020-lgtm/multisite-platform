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

export async function handleAcceptData(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const url = new URL(request.url);
  const days = parseInt(url.searchParams.get('days') || '14');

  const sessions = await env.DB.prepare(
    `SELECT date, sessions, hq1_sessions, hq2_sessions, hq1_rate, hq2_rate, avg_duration_sec, bounce_rate
     FROM site_session_stats WHERE site='elysianu' AND platform='overall'
     ORDER BY date DESC LIMIT ?`
  ).bind(days).all();

  const groups = await env.DB.prepare(
    `SELECT group_name, platform, sessions, hq1, hq2, hq1_rate, hq2_rate, cphq
     FROM ad_group_stats WHERE site='elysianu'
     ORDER BY sessions DESC LIMIT 30`
  ).all();

  const latest = sessions.results[0] || {};
  return json({
    ok: true,
    kpis: {
      hq1_rate: latest.hq1_rate || 0,
      hq2_rate: latest.hq2_rate || 0,
      bounce_rate: latest.bounce_rate || 0,
      avg_duration: latest.avg_duration_sec || 0,
    },
    daily: sessions.results,
    groups: groups.results,
  });
}
