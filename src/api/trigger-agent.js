// src/api/trigger-agent.js — 投手触发 agent · 异步调 Claude API

import { verifySession } from './auth.js';
import { logOp } from './admin.js';

const AGENT_TYPES = {
  comment_gen: { name: '评论生成', prompt: (p) => `你是一个专门为成人玩具独立站生成真实用户评论的文案专家。

【任务】
为产品「${p.group||''}」生成 ${p.count||10} 条真实女性用户评论，用于 Facebook/Instagram 广告评论区。

【产品落地页】
${p.landing_url||'（未提供）'}
（请先理解落地页的产品卖点、使用场景、情感诉求）

【广告剧本方向】
${p.script_theme||'女性自我探索'}
（评论内容必须和这个剧本方向强相关，像是看了这个广告后真实产生的感受）

【评论者人设要求】
- 全部是女性视角，25-45 岁
- 包含以下几类人：
  * 单身女性（自我探索、独立）
  * 有伴侣但伴侣不满足（寻求补充）
  * 夫妻/长期关系中的女性（改善亲密关系）
  * 刚开箱的新用户（第一次体验）
  * 使用一段时间的老用户（对比之前的产品）

【字数要求】
- 每条评论 80-150 字
- 必须有开箱/收到货/使用过程的具体细节
- 至少 60% 是口语化的短句，不要书面语
- 可以有真实的小缺点（增加可信度），但整体正向

【语气要求】
- 真实、口语化、有情绪波动
- 可以用省略号、感叹号、emoji（不超过 2 个/条）
- 不要用"非常""十分""极其"等书面词
- 像在跟闺蜜说话，不像在写产品评测
${p.note?'\n【补充要求】\n'+p.note:''}

【输出格式】
输出纯JSON，不要markdown标记：
{"comments":[{"text":"评论内容","stars":5,"persona":"人设类型"}]}` },
  video_script: { name: '视频脚本', prompt: (p) => {
    const sd = p.sceneData;
    if (sd && sd.synopsis && sd.title) {
      const tagStr = Array.isArray(sd.tags) ? sd.tags.join('、') : '';
      return `你是一位专业的短视频广告脚本策划师，擅长为互动叙事产品创作投放素材。

【落地页剧情信息】
标题：${sd.title}
剧情简介：${sd.synopsis}
内容标签：${tagStr}
落地页：${p.group||''}

【创作要求】
- 视频时长：${p.duration||'30s'}
- 风格：${p.style||'写实'}
${p.direction?'- 补充要求：'+p.direction:''}

【脚本创作原则】
1. 开场 Hook（0-3秒）必须直接切入剧情中最有张力的冲突点或情绪高点
2. 每个场景的画面描述要具体可执行（镜头角度、光线氛围、人物动作）
3. 音频文案简短有力，配合画面节奏
4. 结尾 CTA 引导用户点击体验完整互动剧情
5. 整体节奏：冲突→升级→反转→钩子

【输出格式（严格JSON，不要有任何其他文字）】
{"title":"脚本标题（基于剧情，不超过15字）","duration":"${p.duration||'30s'}","hook":"开场钩子文案（不超过20字）","scenes":[{"time":"0-3s","visual":"具体画面描述","audio":"配音或字幕"},{"time":"3-8s","visual":"具体画面描述","audio":"配音或字幕"},{"time":"8-12s","visual":"具体画面描述","audio":"配音或字幕"},{"time":"12-${p.duration||'30s'}","visual":"具体画面描述","audio":"配音或字幕"}],"cta":"结尾行动号召","scene_ref":"${sd.title}"}`;
    }
    return `你是一位专业的短视频广告脚本策划师。

产品落地页：${p.group||''}
视频时长：${p.duration||'30s'}
风格：${p.style||'写实'}
${p.direction?'补充要求：'+p.direction:''}

注意：未获取到落地页剧情数据，请根据URL生成通用脚本框架。

【输出格式（严格JSON，不要有任何其他文字）】
{"title":"脚本标题","duration":"${p.duration||'30s'}","hook":"开场钩子文案","scenes":[{"time":"0-3s","visual":"画面描述","audio":"配音或字幕"},{"time":"3-8s","visual":"画面描述","audio":"配音或字幕"},{"time":"8-12s","visual":"画面描述","audio":"配音或字幕"},{"time":"12-${p.duration||'30s'}","visual":"画面描述","audio":"配音或字幕"}],"cta":"结尾行动号召","warning":"未获取到落地页剧情，建议点击解析剧情后重新生成"}`;
  }},
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
