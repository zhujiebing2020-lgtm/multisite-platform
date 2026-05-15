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
