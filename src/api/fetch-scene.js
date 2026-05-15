// src/api/fetch-scene.js — 直接 fetch 落地页 HTML，正则提取剧情数据

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleFetchScene(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { url } = await request.json().catch(() => ({}));
  if (!url || !url.includes('creviatech.com')) {
    return json({ error: '仅支持 creviatech.com 页面' }, 400);
  }

  try {
    const resp = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html',
      },
    });

    if (!resp.ok) return json({ error: `落地页返回 ${resp.status}` }, 502);
    const html = await resp.text();

    const titleMatch = html.match(/property="og:title"\s+content="CRAVE AI\s*[-–]\s*([^"|]+)/);
    const title = titleMatch ? titleMatch[1].trim() : '';

    const synopsisMatch = html.match(/Story Synopsis<\/p><p>([^<]+)<\/p>/);
    const synopsis = synopsisMatch ? synopsisMatch[1].trim() : '';

    const tagsRaw = html.match(/<span>#([^<]+)<\/span>/g) || [];
    const tags = tagsRaw.map(t => t.replace(/<\/?span>/g, '').replace('#', '').trim());

    const imageMatch = html.match(/property="og:image"\s+content="([^"]+)"/);
    const coverImage = imageMatch ? imageMatch[1] : '';

    if (!title && !synopsis) {
      return json({ error: '该页面为 SPA 客户端渲染，暂无法自动提取。请手动填写标题和简介。' });
    }

    return json({ title, synopsis, tags, coverImage, url });
  } catch (e) {
    return json({ error: '抓取失败：' + e.message });
  }
}
