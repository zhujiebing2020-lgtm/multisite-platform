// src/api/kling.js — 图片上传到 R2 + Kling API 代理

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleUploadImage(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { filename, contentBase64 } = await request.json();
  if (!filename || !contentBase64) return json({ error: '缺少文件' }, 400);

  const key = `scenes/${Date.now()}_${filename}`;
  const binary = Uint8Array.from(atob(contentBase64), c => c.charCodeAt(0));
  await env.R2.put(key, binary, { httpMetadata: { contentType: 'image/' + (filename.split('.').pop() || 'png') } });

  const url = `https://crave.${env.R2_DOMAIN || 'r2.dev'}/${key}`;
  return json({ ok: true, url, key });
}

export async function handleKlingGenerate(request, env, ctx) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { image_url, prompt, duration, aspect_ratio } = await request.json();
  if (!image_url) return json({ error: '缺少图片' }, 400);

  const klingBase = env.KLING_BASE_URL || 'https://api.klingai.com';
  const resp = await fetch(`${klingBase}/v1/videos/image2video`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.KLING_API_KEY}`,
    },
    body: JSON.stringify({
      image: image_url,
      prompt: prompt || '',
      duration: duration || 5,
      aspect_ratio: aspect_ratio || '9:16',
    }),
  });

  if (!resp.ok) {
    const err = await resp.text();
    return json({ error: `Kling API ${resp.status}: ${err.slice(0, 200)}` }, 502);
  }

  const result = await resp.json();
  return json({ ok: true, task_id: result.data?.task_id || result.task_id || result.id });
}

export async function handleKlingStatus(request, env, taskId) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const klingBase = env.KLING_BASE_URL || 'https://api.klingai.com';
  const resp = await fetch(`${klingBase}/v1/videos/image2video/${taskId}`, {
    headers: { 'Authorization': `Bearer ${env.KLING_API_KEY}` },
  });

  if (!resp.ok) {
    const err = await resp.text();
    return json({ error: `Kling API ${resp.status}: ${err.slice(0, 200)}` }, 502);
  }

  const result = await resp.json();
  const data = result.data || result;
  return json({
    ok: true,
    status: data.task_status || data.status,
    video_url: data.task_result?.videos?.[0]?.url || data.video_url || null,
  });
}
