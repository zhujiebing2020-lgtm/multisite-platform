// src/api/kling.js — 图片上传到 R2 + Kling API 代理

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

// Runway API 调用（替代 Kling）
async function runwayFetch(env, path, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Authorization': `Bearer ${env.RUNWAY_API_KEY}`, 'Content-Type': 'application/json', 'X-Runway-Version': '2024-11-06' },
  };
  if (body) opts.body = JSON.stringify(body);
  return fetch(`https://api.dev.runwayml.com/v1${path}`, opts);
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

export async function handleUploadImageDirect(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const contentType = request.headers.get('content-type') || '';
  const filename = decodeURIComponent(request.headers.get('x-filename') || `${Date.now()}.jpg`);
  const key = `ref-images/${Date.now()}-${filename.replace(/[^a-zA-Z0-9._-]/g, '_')}`;

  await env.R2.put(key, request.body, {
    httpMetadata: { contentType: contentType || 'image/jpeg' }
  });

  // 通过 Worker 代理访问（不依赖 R2 公开域名）
  const url = `/api/r2/${key}`;
  return json({ ok: true, url, key });
}

export async function handleR2Get(request, env, key) {
  const obj = await env.R2.get(key);
  if (!obj) return new Response('Not found', { status: 404 });
  return new Response(obj.body, {
    headers: { 'Content-Type': obj.httpMetadata?.contentType || 'image/jpeg', 'Cache-Control': 'public, max-age=86400' }
  });
}

export async function handleGenerateScenes(request, env, ctx) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { reference_image_url, scenes, style } = await request.json();
  if (!reference_image_url || !scenes || !scenes.length) return json({ error: '缺少参考图或场景' }, 400);

  // 图片生成暂用参考图作为所有 scene 的占位（后续接 Flux/DALL-E）
  const results = scenes.map(scene => ({ index: scene.index, image_url: reference_image_url }));
  return json({ ok: true, results });
}

export async function handleGenerateScenesStatus(request, env, batchId) {
  return json({ ok: true, status: 'completed', results: [] });
}

export async function handleKlingGenerate(request, env, ctx) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { image_url, prompt, duration, aspect_ratio } = await request.json();
  if (!image_url) return json({ error: '缺少图片' }, 400);

  const ratioMap = { '9:16': '720:1280', '16:9': '1280:720', '1:1': '960:960' };
  const resp = await runwayFetch(env, '/image_to_video', 'POST', {
    promptImage: image_url,
    promptText: prompt || '',
    duration: duration || 5,
    ratio: ratioMap[aspect_ratio] || '720:1280',
    model: 'gen4_turbo',
  });

  if (!resp.ok) {
    const err = await resp.text();
    return json({ error: `Runway API ${resp.status}: ${err.slice(0, 200)}` }, 502);
  }

  const result = await resp.json();
  return json({ ok: true, task_id: result.id });
}

export async function handleKlingStatus(request, env, taskId) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const resp = await runwayFetch(env, `/tasks/${taskId}`);

  if (!resp.ok) {
    const err = await resp.text();
    return json({ error: `Runway API ${resp.status}: ${err.slice(0, 200)}` }, 502);
  }

  const result = await resp.json();
  const statusMap = { SUCCEEDED: 'succeed', FAILED: 'failed', RUNNING: 'running', PENDING: 'pending' };
  return json({
    ok: true,
    status: statusMap[result.status] || result.status,
    video_url: result.output?.[0] || null,
  });
}
