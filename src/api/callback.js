// src/api/callback.js — Actions 执行完后回写结果

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
