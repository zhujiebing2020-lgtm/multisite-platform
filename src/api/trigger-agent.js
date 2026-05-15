// src/api/trigger-agent.js — 投手触发 agent

import { verifySession } from './auth.js';
import { logOp } from './admin.js';

const AGENT_TYPES = {
  data_analysis: { name: '数据分析', desc: '分析你的广告组表现，给出加减预算建议' },
  comment_gen: { name: '评论生成', desc: '为绿灯组生成产品评论（反AI腔 v1.2）' },
  video_script: { name: '视频脚本', desc: '根据广告组生成视频创意脚本' },
  strategy: { name: '自动策略', desc: '基于最新数据生成投放动作指令' },
};

export async function handleTriggerAgent(request, env) {
  const user = await verifySession(request, env);
  if (!user) {
    const pass = request.headers.get('x-pass') || '';
    if (!pass || pass !== env.ACCESS_PASSCODE) {
      return json({ error: '未登录或口令错误' }, 401);
    }
  }

  try {
    const { agent_type, site, params } = await request.json();
    const owner = user?.sub || 'unknown';

    if (!agent_type || !AGENT_TYPES[agent_type]) {
      return json({ error: `agent_type 必须是: ${Object.keys(AGENT_TYPES).join('/')}` }, 400);
    }
    if (!site || !/^[a-z0-9_-]+$/i.test(site)) {
      return json({ error: 'site 不合法' }, 400);
    }

    const jobId = crypto.randomUUID();
    const now = new Date().toISOString();

    await env.DB.prepare(
      'INSERT INTO agent_jobs (id, owner, site, agent_type, status, input_ref, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).bind(jobId, owner, site, agent_type, 'pending', JSON.stringify(params || {}), now).run();

    const mdContent = [
      '---',
      `agent: ${agent_type}`,
      `owner: ${owner}`,
      `site: ${site}`,
      `job_id: ${jobId}`,
      '---',
      '',
      JSON.stringify(params || {}, null, 2),
    ].join('\n');

    const filename = `${now.slice(0,19).replace(/[-:T]/g, '').slice(0,15)}_${owner}-${agent_type}.md`;
    const path = `requests/${filename}`;
    const ghPath = path.split('/').map(encodeURIComponent).join('/');

    const ghRes = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/contents/${ghPath}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'multisite-platform-worker',
      },
      body: JSON.stringify({
        message: `agent: ${owner}/${agent_type}/${site} [job:${jobId}]`,
        content: btoa(unescape(encodeURIComponent(mdContent))),
        branch: 'main',
      }),
    });

    if (!ghRes.ok) {
      const t = await ghRes.text();
      await env.DB.prepare('UPDATE agent_jobs SET status = ? WHERE id = ?').bind('failed', jobId).run();
      return json({ error: `GitHub ${ghRes.status}: ${t.slice(0, 200)}` }, 502);
    }

    await logOp(env, owner, 'trigger_agent', { agent_type, site, job_id: jobId }, request);
    return json({ ok: true, job_id: jobId, agent: AGENT_TYPES[agent_type].name, status: 'pending' });
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

export { AGENT_TYPES };

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
