// src/api/auth.js — 口令分级验证 + JWT session

export async function handleAuth(request, env) {
  try {
    const { passcode } = await request.json();
    if (!passcode) return json({ error: '请输入口令' }, 400);

    const user = await env.DB.prepare('SELECT * FROM users WHERE passcode = ?').bind(passcode).first();
    if (!user) return json({ error: '口令无效' }, 401);

    const token = await createToken(user, env);
    const resp = json({
      ok: true,
      user: { role: user.role, owner_code: user.owner_code, display_name: user.display_name }
    });
    resp.headers.set('Set-Cookie', `session=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=86400`);
    return resp;
  } catch (e) {
    return json({ error: String(e.message || e) }, 500);
  }
}

export async function verifySession(request, env) {
  const cookie = request.headers.get('Cookie') || '';
  const match = cookie.match(/session=([^;]+)/);
  if (!match) return null;

  try {
    const payload = await verifyToken(match[1], env);
    return payload;
  } catch {
    return null;
  }
}

async function createToken(user, env) {
  const payload = {
    sub: user.owner_code,
    role: user.role,
    sites: JSON.parse(user.sites),
    permissions: JSON.parse(user.permissions),
    display_name: user.display_name,
    exp: Math.floor(Date.now() / 1000) + 86400
  };
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
  const secret = env.JWT_SECRET || env.ACCESS_PASSCODE || 'fallback-secret';
  const sig = await hmacSign(`${header}.${body}`, secret);
  return `${header}.${body}.${sig}`;
}

async function verifyToken(token, env) {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('invalid token');
  const secret = env.JWT_SECRET || env.ACCESS_PASSCODE || 'fallback-secret';
  const expected = await hmacSign(`${parts[0]}.${parts[1]}`, secret);
  if (expected !== parts[2]) throw new Error('invalid signature');
  const payload = JSON.parse(decodeURIComponent(escape(atob(parts[1]))));
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error('expired');
  return payload;
}

async function hmacSign(data, secret) {
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/[+/=]/g, c =>
    c === '+' ? '-' : c === '/' ? '_' : ''
  );
}

export function handleLogout() {
  const resp = json({ ok: true });
  resp.headers.set('Set-Cookie', 'session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0');
  return resp;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json' }
  });
}
