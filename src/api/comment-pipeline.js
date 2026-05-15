// src/api/comment-pipeline.js — 多模型评论生成链路

async function callTogether(env, model, messages, options = {}) {
  const resp = await fetch('https://api.together.xyz/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${env.TOGETHER_API_KEY}` },
    body: JSON.stringify({ model, messages, max_tokens: options.maxTokens || 2000, temperature: options.temperature ?? 0.8 }),
  });
  if (!resp.ok) throw new Error(`Together ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  const data = await resp.json();
  return data.choices?.[0]?.message?.content || '';
}

function extractJson(text) {
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error('JSON parse failed: ' + text.slice(0, 200));
  return JSON.parse(m[0]);
}

async function generateDraft(env, params) {
  const { sceneTitle, sceneSynopsis, sceneTags, strategy, count, style, note, retryFeedback } = params;
  const tagStr = Array.isArray(sceneTags) ? sceneTags.join('、') : '';
  const retry = retryFeedback ? `\n\n【上一版本问题（必须修改）】\n${retryFeedback}` : '';

  const prompt = `你是专注成人互动内容的资深文案，为欧美市场合法成人平台撰写真实用户评论。

【产品】标题：${sceneTitle || '互动剧情'}｜简介：${(sceneSynopsis || '').slice(0, 200)}｜标签：${tagStr}
【策略】${strategy}
【要求】英文，${count}条，每条100-180字，${style}
${note ? '补充：' + note : ''}${retry}

原则：1.必须提及剧情具体元素 2.像真实用户写的 3.自然融入标签体验 4.避免套话 5.每条独特视角

输出严格JSON：{"reviews":[{"id":1,"text":"...","persona":"..."}]}`;

  return extractJson(await callTogether(env, 'Qwen/Qwen2.5-72B-Instruct-Turbo', [{ role: 'user', content: prompt }], { temperature: 0.85 }));
}

async function polishDraft(env, draft, ctx) {
  const reviewsText = draft.reviews.map(r => `[Review ${r.id}]\n${r.text}\nPersona: ${r.persona}`).join('\n\n');
  const prompt = `You are a creative editor for adult content testimonials (European/American market).

Polish these reviews to feel more genuine and emotionally resonant. Scene: "${ctx.title}" - ${(ctx.synopsis || '').slice(0, 100)}

${reviewsText}

Guidelines: Add sensory details, vary rhythm, remove marketing-speak, keep 100-180 words each, NO explicit content.
Output strict JSON: {"reviews":[{"id":1,"text":"...","persona":"..."}]}`;

  return extractJson(await callTogether(env, 'meta-llama/Llama-3.3-70B-Instruct-Turbo', [{ role: 'user', content: prompt }], { temperature: 0.7 }));
}

async function auditReviews(env, reviews, ctx) {
  const reviewsText = reviews.map(r => `[Review ${r.id}]\n${r.text}`).join('\n\n');
  const tagStr = Array.isArray(ctx.tags) ? ctx.tags.join(', ') : '';
  const prompt = `Audit these adult platform reviews against 5 criteria. Scene: "${ctx.title}", Tags: ${tagStr}

${reviewsText}

Criteria: 1.AUTHENTICITY(no ad-speak) 2.SCENE_SPECIFICITY(references this scene) 3.TAG_INTEGRATION(connects to tags) 4.LANGUAGE_NATURALNESS(varied,personal) 5.PLATFORM_SAFETY(no explicit content)

Output JSON: {"audit_results":[{"id":1,"criteria":{"authenticity":{"pass":true},"scene_specificity":{"pass":true},"tag_integration":{"pass":true},"language_naturalness":{"pass":true},"platform_safety":{"pass":true}},"overall_pass":true,"feedback":""}],"pass_count":5,"retry_needed":false}`;

  return extractJson(await callTogether(env, 'deepseek-ai/DeepSeek-V3', [{ role: 'user', content: prompt }], { temperature: 0.3 }));
}

async function scoreReviews(env, reviews, ctx) {
  const reviewsText = reviews.map(r => `[${r.id}] ${r.text}`).join('\n\n');
  const baseUrl = env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com';
  const resp = await fetch(`${baseUrl}/v1/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model: 'claude-opus-4-7', max_tokens: 800, messages: [{ role: 'user', content: `Rate each review 1-10 for adult interactive fiction platform. Scene: "${ctx.title}". 9-10=exceptional, 7-8=good, <7=needs work.\n\n${reviewsText}\n\nOutput JSON only: {"scores":[{"id":1,"score":8,"note":"brief"}],"average":7.5,"recommendation":"publish"/"retry"}` }] }),
  });
  const data = await resp.json();
  return extractJson(data.content?.[0]?.text || '{}');
}

export async function generateComments(env, params) {
  const { sceneTitle, sceneSynopsis, sceneTags, count = 5, style, note, strategy } = params;
  const ctx = { title: sceneTitle, synopsis: sceneSynopsis, tags: sceneTags };
  let retryFeedback = null;

  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const draft = await generateDraft(env, { sceneTitle, sceneSynopsis, sceneTags, strategy, count: String(count), style, note, retryFeedback });
      const polished = await polishDraft(env, draft, ctx);
      const audit = await auditReviews(env, polished.reviews, ctx);

      const passedReviews = polished.reviews.filter(r => {
        const a = audit.audit_results?.find(x => x.id === r.id);
        return a?.overall_pass !== false;
      });

      if (!audit.retry_needed || attempt === 3) {
        const toScore = passedReviews.length >= Math.ceil(count * 0.6) ? passedReviews : polished.reviews;
        const scoring = await scoreReviews(env, toScore, ctx);
        return { reviews: toScore, scoring, audit_summary: { attempts: attempt, pass_count: audit.pass_count || passedReviews.length, total: polished.reviews.length }, models_used: ['Claude(strategy)', 'Qwen2.5-72B(draft)', 'Llama-3.3-70B(polish)', 'DeepSeek-V3(audit)', 'Claude(score)'] };
      }

      retryFeedback = audit.audit_results?.filter(r => !r.overall_pass).map(r => `Review ${r.id}: ${r.feedback}`).join('\n');
    } catch (e) {
      if (attempt === 3) return { error: `生成失败(${attempt}次)：${e.message}` };
      retryFeedback = `上轮错误：${e.message}`;
    }
  }
  return { error: '超过最大重试次数' };
}
