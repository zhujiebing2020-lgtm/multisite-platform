// functions/api/upload.js
// Cloudflare Pages Function · 接收投手 xlsx 上传 → 推到 GitHub repo → 触发 Actions
//
// 环境变量(Cloudflare Pages → Settings → Environment variables):
//   GITHUB_TOKEN  · fine-grained PAT, scope: Contents write on this repo
//   GITHUB_REPO   · 例如 "zhujiebing2020-lgtm/multisite-platform"
//   ACCESS_PASSCODE · ZJB 发给投手的口令(单一共享口令,简单够用)

export async function onRequestPost({ request, env }) {
  try {
    const pass = request.headers.get('x-pass') || '';
    if (!env.ACCESS_PASSCODE || pass !== env.ACCESS_PASSCODE) {
      return json({ error: '口令错误' }, 401);
    }

    const { filename, contentBase64, owner } = await request.json();
    if (!filename || !contentBase64 || !owner) {
      return json({ error: '缺 filename / contentBase64 / owner' }, 400);
    }
    if (!/^[A-Za-z0-9_.一-龥-]+\.xlsx?$/i.test(filename)) {
      return json({ error: '文件名不合法' }, 400);
    }
    if (!['HZM','CHJ','HNN','ZXR','LZL','PLZ'].includes(owner)) {
      return json({ error: 'owner 不在白名单' }, 400);
    }

    const path = `requests/uploads/${filename}`;
    const ghRes = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/contents/${encodeURIComponent(path)}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'multisite-upload-fn',
      },
      body: JSON.stringify({
        message: `upload: ${owner} ${filename}`,
        content: contentBase64,
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
