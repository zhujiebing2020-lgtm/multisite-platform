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

export async function handleUploadImageDirect(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const contentType = request.headers.get('content-type') || '';
  const filename = request.headers.get('x-filename') || `${Date.now()}.jpg`;
  const key = `ref-images/${Date.now()}-${filename.replace(/[^a-zA-Z0-9._-]/g, '_')}`;

  await env.R2.put(key, request.body, {
    httpMetadata: { contentType: contentType || 'image/jpeg' }
  });

  const url = `https://crave.${env.R2_DOMAIN || 'r2.dev'}/${key}`;
  return json({ ok: true, url, key });
}

export async function handleGenerateScenes(request, env, ctx) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { reference_image_url, scenes, style } = await request.json();
  if (!reference_image_url || !scenes || !scenes.length) return json({ error: '缺少参考图或场景' }, 400);

  const klingBase = env.KLING_BASE_URL || 'https://api.klingai.com';
  const results = [];

  // 并行生成所有 scene 图片
  const promises = scenes.map(async (scene) => {
    const prompt = `${scene.visual}，保持与参考图一致的人物外貌和风格，${style || 'realistic'}风格，竖版9:16`;
    const resp = await fetch(`${klingBase}/v1/images/generations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.KLING_API_KEY}`,
      },
      body: JSON.stringify({
        prompt,
        image: reference_image_url,
        n: 1,
        aspect_ratio: '9:16',
      }),
    });
    if (!resp.ok) {
      const err = await resp.text();
      return { index: scene.index, error: `${resp.status}: ${err.slice(0, 100)}` };
    }
    const data = await resp.json();
    const imageUrl = data.data?.[0]?.url || data.images?.[0]?.url || data.data?.task_result?.images?.[0]?.url || null;
    return { index: scene.index, image_url: imageUrl, task_id: data.data?.task_id };
  });

  const settled = await Promise.all(promises);
  // 如果有 task_id（异步模式），返回第一个 task_id 让前端轮询
  const asyncTasks = settled.filter(r => r.task_id && !r.image_url);
  if (asyncTasks.length > 0) {
    // 存任务映射到 DB 供轮询
    const batchId = crypto.randomUUID();
    await env.DB.prepare(
      'INSERT INTO operation_log (owner_code, action, detail) VALUES (?, ?, ?)'
    ).bind(user.sub, 'scene_gen', JSON.stringify({ batch_id: batchId, tasks: settled })).run();
    return json({ ok: true, task_id: batchId, status: 'processing' });
  }

  // 同步模式：直接返回结果
  return json({ ok: true, results: settled.filter(r => r.image_url) });
}

export async function handleGenerateScenesStatus(request, env, batchId) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  // 从日志查找批次信息
  const log = await env.DB.prepare(
    "SELECT detail FROM operation_log WHERE action='scene_gen' AND detail LIKE ? ORDER BY ts DESC LIMIT 1"
  ).bind(`%${batchId}%`).first();
  if (!log) return json({ error: '批次不存在' }, 404);

  const detail = JSON.parse(log.detail);
  const klingBase = env.KLING_BASE_URL || 'https://api.klingai.com';
  const results = [];
  let allDone = true;

  for (const task of detail.tasks) {
    if (task.image_url) { results.push(task); continue; }
    if (!task.task_id) continue;
    const resp = await fetch(`${klingBase}/v1/images/generations/${task.task_id}`, {
      headers: { 'Authorization': `Bearer ${env.KLING_API_KEY}` },
    });
    if (resp.ok) {
      const data = await resp.json();
      const url = data.data?.task_result?.images?.[0]?.url;
      if (url) { results.push({ index: task.index, image_url: url }); }
      else { allDone = false; }
    } else { allDone = false; }
  }

  return json({ ok: true, status: allDone ? 'completed' : 'processing', results });
}

export async function handleKlingGenerate(request, env, ctx) {
  const user = await verifySession(request, env);
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
