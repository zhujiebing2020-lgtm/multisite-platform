// src/api/callback.js — Actions 执行完后回写结果

import { logOp } from './admin.js';

export async function handleCallback(request, env) {
  const secret = request.headers.get('x-callback-secret') || '';
  if (!env.CALLBACK_SECRET || secret !== env.CALLBACK_SECRET) {
    return json({ error: 'unauthorized' }, 401);
  }

  try {
    const { job_id, status, output_summary, output_full } = await request.json();
    if (!job_id) return json({ error: 'missing job_id' }, 400);

    const now = new Date().toISOString();
    await env.DB.prepare(
      'UPDATE agent_jobs SET status = ?, output_summary = ?, output_full = ?, completed_at = ? WHERE id = ?'
    ).bind(
      status || 'done',
      output_summary || null,
      output_full || null,
      now,
      job_id
    ).run();

    const job = await env.DB.prepare('SELECT owner, agent_type, site FROM agent_jobs WHERE id = ?').bind(job_id).first();
    if (job) {
      await logOp(env, job.owner, status === 'failed' ? 'agent_failed' : 'agent_done', { agent_type: job.agent_type, site: job.site, job_id }, request);

      // Agent 成功时，将输出写入建议卡片表
      if (status !== 'failed' && output_full) {
        try {
          const parsed = JSON.parse(output_full);
          const items = parsed.recommendations || parsed.actions || (Array.isArray(parsed) ? parsed : [parsed]);
          for (const item of items) {
            await env.DB.prepare(
              'INSERT INTO agent_recommendations (agent_id, group_name, site, recommendation, risk_level, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
            ).bind(
              job.agent_type,
              item.group_name || item.group || null,
              job.site,
              JSON.stringify(item),
              item.risk_level || 'medium',
              'pending',
              now
            ).run();
          }
        } catch (e) { /* output 不是 JSON 或无建议结构，跳过 */ }
      }
    }

    return json({ ok: true });
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
