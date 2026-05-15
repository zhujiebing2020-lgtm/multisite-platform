// src/api/trigger-agent.js — 投手触发 agent · 异步调 Claude API

import { verifySession } from './auth.js';
import { logOp } from './admin.js';

const AGENT_TYPES = {
  comment_gen: { name: '评论生成', prompt: (p) => `你是一个情趣用品电商的用户体验文案专家。请为产品系列"${p.group||''}"撰写${p.count||10}条产品体验分享文案，用于社交媒体营销素材。要求：每条风格不同、口语化、有真实感受细节、避免模板化表达。${p.note?'补充要求：'+p.note:''}。输出JSON格式：{"comments":[{"text":"文案内容","stars":5}]}` },
  video_script: { name: '视频脚本', prompt: (p) => `你是一个短视频创意脚本专家。为广告组"${p.group||''}"生成一个15-30秒的视频脚本。方向：${p.direction||'产品展示'}。输出JSON格式：{"title":"标题","duration":"时长","scenes":[{"time":"0-5s","visual":"画面描述","audio":"音频/旁白"}],"hook":"开头钩子文案"}` },
  strategy: { name: '自动策略', prompt: (p, data) => `你是一个广告投放策略专家。基于以下广告组数据，生成今日行动建议。每条建议包含：广告组名、建议动作、原因、风险等级。\n\n数据：${JSON.stringify(data||{})}\n\n输出JSON格式：{"actions":[{"group":"组名","action":"建议动作","reason":"原因","risk_level":"low|medium|high"}]}` },
  creative_agent: { name: '素材生成', prompt: (p) => `你是一个成人用品电商的创意Brief专家。为广告组"${p.group||''}"生成Creative Brief。落地页类型：${p.landing_type||'文章页'}。受众：${p.audience||'自动'}。${p.notes?'补充：'+p.notes:''}。输出JSON格式：{"hook_variants":["钩子1","钩子2","钩子3"],"headline":"标题建议","audience_description":"受众描述","compliance_status":"compliant","compliance_reason":""}` },
};

export async function handleTriggerAgent(request, env, ctx) {
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

    const jobId = crypto.randomUUID();
    const now = new Date().toISOString();

    await env.DB.prepare(
      'INSERT INTO agent_jobs (id, owner, site, agent_type, status, input_ref, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).bind(jobId, owner, site, agent_type, 'pending', JSON.stringify(params || {}), now).run();

    await logOp(env, owner, 'trigger_agent', { agent_type, site, job_id: jobId }, request);

    // 异步执行 Claude API 调用
    ctx.waitUntil(executeAgent(env, jobId, agent_type, site, params || {}));

    return json({ ok: true, job_id: jobId, agent: AGENT_TYPES[agent_type].name, status: 'pending' });
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

async function executeAgent(env, jobId, agentType, site, params) {
  try {
    const agentDef = AGENT_TYPES[agentType];
    let contextData = null;

    // 策略 agent 需要拉取当前数据
    if (agentType === 'strategy') {
      const rows = await env.DB.prepare(
        "SELECT group_name, spend, hvu, cphq FROM ad_daily WHERE site != '_test' ORDER BY date DESC LIMIT 30"
      ).all();
      contextData = rows.results;
    }

    const prompt = agentDef.prompt(params, contextData);
    const baseUrl = env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com';

    const resp = await fetch(`${baseUrl}/v1/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-opus-4-7',
        max_tokens: 2000,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!resp.ok) {
      const err = await resp.text();
      await env.DB.prepare(
        'UPDATE agent_jobs SET status = ?, output_summary = ?, completed_at = ? WHERE id = ?'
      ).bind('failed', `API错误: ${resp.status} ${err.slice(0, 200)}`, new Date().toISOString(), jobId).run();
      return;
    }

    const result = await resp.json();
    const content = result.content?.[0]?.text || '';
    const now = new Date().toISOString();

    // 提取摘要
    let summary = content.slice(0, 100);
    try {
      const parsed = JSON.parse(content);
      if (parsed.actions) summary = `${parsed.actions.length} 条建议`;
      else if (parsed.comments) summary = `${parsed.comments.length} 条评论`;
      else if (parsed.title) summary = parsed.title;
      else if (parsed.hook_variants) summary = parsed.hook_variants[0];
    } catch (e) {}

    await env.DB.prepare(
      'UPDATE agent_jobs SET status = ?, output_summary = ?, output_full = ?, completed_at = ? WHERE id = ?'
    ).bind('done', summary, content, now, jobId).run();

    // 写入 agent_recommendations
    try {
      const parsed = JSON.parse(content);
      const items = parsed.actions || parsed.recommendations || (Array.isArray(parsed) ? parsed : []);
      for (const item of items) {
        await env.DB.prepare(
          'INSERT INTO agent_recommendations (agent_id, group_name, site, recommendation, risk_level, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
        ).bind(agentType, item.group || item.group_name || null, site, JSON.stringify(item), item.risk_level || 'medium', 'pending', now).run();
      }
    } catch (e) {}

  } catch (e) {
    await env.DB.prepare(
      'UPDATE agent_jobs SET status = ?, output_summary = ?, completed_at = ? WHERE id = ?'
    ).bind('failed', String(e.message || e).slice(0, 200), new Date().toISOString(), jobId).run();
  }
}

export { AGENT_TYPES };

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
