// src/api/request.js
// 投手点 agent 按钮 → 写 requests/{owner}-{agent}-{ts}.md → 触发 Actions

export async function handleRequest(request, env) {
  try {
    const pass = request.headers.get('x-pass') || '';
    if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
      return json({ error: '口令错误' }, 401);
    }

    const { filename, content, owner } = await request.json();
    if (!filename || !content || !owner) {
      return json({ error: '缺 filename / content / owner' }, 400);
    }
    if (!/^[A-Za-z0-9_.一-鿿-]+\.md$/.test(filename)) {
      return json({ error: '文件名不合法' }, 400);
    }
    if (!['HZM','CHJ','HNN','ZXR','LZL','PLZ'].includes(owner)) {
      return json({ error: 'owner 不在白名单' }, 400);
    }

    const path = `requests/${filename}`;
    const b64 = btoa(unescape(encodeURIComponent(content)));

    const ghRes = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/contents/${encodeURIComponent(path)}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'multisite-upload-worker',
      },
      body: JSON.stringify({
        message: `req: ${owner} ${filename}`,
        content: b64,
        branch: 'main',
      }),
    });

    if (!ghRes.ok) {
      const t = await ghRes.text();
      return json({ error: `GitHub ${ghRes.status}: ${t.slice(0, 200)}` }, 502);
    }
    return json({ ok: true, path });
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
