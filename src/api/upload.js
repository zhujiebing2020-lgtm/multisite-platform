// src/api/upload.js
// 接收投手 xlsx 上传 → 推到 GitHub repo → 触发 Actions

const OWNERS = ['HZM','CHJ','HNN','ZXR','LZL','PLZ'];
const CHANNELS = ['FB','Google','Twitter','TikTok'];

export async function handleUpload(request, env) {
  try {
    const pass = request.headers.get('x-pass') || '';
    if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
      return json({ error: '口令错误' }, 401);
    }

    const { filename, contentBase64, owner, site, channel } = await request.json();
    if (!filename || !contentBase64 || !owner || !site || !channel) {
      return json({ error: '缺 filename / contentBase64 / owner / site / channel' }, 400);
    }
    if (!/^[A-Za-z0-9_.一-鿿-]+\.xlsx?$/i.test(filename)) {
      return json({ error: '文件名不合法' }, 400);
    }
    if (!OWNERS.includes(owner)) {
      return json({ error: 'owner 不在白名单' }, 400);
    }
    if (!/^[a-z0-9_-]+$/i.test(site)) {
      return json({ error: 'site 标识只能字母数字_-' }, 400);
    }
    if (!CHANNELS.includes(channel)) {
      return json({ error: `channel 必须是: ${CHANNELS.join('/')}` }, 400);
    }

    const path = `requests/uploads/${filename}`;
    const ghPath = path.split('/').map(encodeURIComponent).join('/');
    const ghRes = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/contents/${ghPath}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'multisite-upload-worker',
      },
      body: JSON.stringify({
        message: `upload: ${owner}/${site}/${channel} ${filename}`,
        content: contentBase64,
        branch: 'main',
      }),
    });

    if (!ghRes.ok) {
      const t = await ghRes.text();
      return json({ error: `GitHub ${ghRes.status}: ${t.slice(0, 200)}` }, 502);
    }
    return json({ ok: true, path, meta: { owner, site, channel } });
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
