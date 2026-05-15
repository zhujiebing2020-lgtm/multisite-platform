// src/api/admin.js — 用户管理 + 操作日志查询（admin only）

import { verifySession } from './auth.js';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

function genPasscode() {
  const chars = 'abcdefghjkmnpqrstuvwxyz23456789';
  return Array.from(crypto.getRandomValues(new Uint8Array(8))).map(b => chars[b % chars.length]).join('');
}

async function requireAdmin(request, env) {
  const session = await verifySession(request, env);
  if (!session || session.role !== 'admin') return null;
  return session;
}

export async function handleAdminUsers(request, env) {
  const admin = await requireAdmin(request, env);
  if (!admin) return json({ error: '需要管理员权限' }, 403);

  if (request.method === 'GET') {
    const rows = await env.DB.prepare('SELECT passcode, role, owner_code, display_name, sites, permissions, created_at FROM users').all();
    return json(rows.results);
  }

  if (request.method === 'POST') {
    const { owner_code, display_name, role, sites } = await request.json();
    if (!owner_code || !role) return json({ error: '缺少 owner_code 或 role' }, 400);
    const passcode = genPasscode();
    await env.DB.prepare(
      'INSERT INTO users (passcode, role, owner_code, display_name, sites, permissions) VALUES (?, ?, ?, ?, ?, ?)'
    ).bind(passcode, role, owner_code, display_name || owner_code, JSON.stringify(sites || ['elysianu']), JSON.stringify(['upload', 'trigger_agent', 'view_results'])).run();
    await logOp(env, admin.sub, 'create_user', { owner_code, role }, request);
    return json({ ok: true, passcode, owner_code });
  }

  return json({ error: 'method not allowed' }, 405);
}

export async function handleAdminUser(request, env, ownerCode) {
  const admin = await requireAdmin(request, env);
  if (!admin) return json({ error: '需要管理员权限' }, 403);

  if (request.method === 'PUT') {
    const body = await request.json();
    const user = await env.DB.prepare('SELECT * FROM users WHERE owner_code = ?').bind(ownerCode).first();
    if (!user) return json({ error: '用户不存在' }, 404);

    const newPasscode = body.reset_passcode ? genPasscode() : user.passcode;
    const role = body.role || user.role;
    const sites = body.sites ? JSON.stringify(body.sites) : user.sites;
    const display_name = body.display_name || user.display_name;
    const permissions = body.permissions ? JSON.stringify(body.permissions) : user.permissions;

    await env.DB.prepare('DELETE FROM users WHERE owner_code = ?').bind(ownerCode).run();
    await env.DB.prepare(
      'INSERT INTO users (passcode, role, owner_code, display_name, sites, permissions) VALUES (?, ?, ?, ?, ?, ?)'
    ).bind(newPasscode, role, ownerCode, display_name, sites, permissions).run();
    await logOp(env, admin.sub, 'update_user', { owner_code: ownerCode, reset_passcode: !!body.reset_passcode }, request);
    return json({ ok: true, passcode: body.reset_passcode ? newPasscode : undefined });
  }

  if (request.method === 'DELETE') {
    await env.DB.prepare('DELETE FROM users WHERE owner_code = ?').bind(ownerCode).run();
    await logOp(env, admin.sub, 'delete_user', { owner_code: ownerCode }, request);
    return json({ ok: true });
  }

  return json({ error: 'method not allowed' }, 405);
}

export async function handleAdminLogs(request, env) {
  const admin = await requireAdmin(request, env);
  if (!admin) return json({ error: '需要管理员权限' }, 403);

  const url = new URL(request.url);
  const days = parseInt(url.searchParams.get('days') || '7');
  const owner = url.searchParams.get('owner');

  let sql = 'SELECT * FROM operation_log WHERE ts >= datetime("now", ?)';
  const params = [`-${days} days`];
  if (owner) { sql += ' AND owner_code = ?'; params.push(owner); }
  sql += ' ORDER BY ts DESC LIMIT 100';

  const rows = await env.DB.prepare(sql).bind(...params).all();
  return json(rows.results);
}

export async function logOp(env, owner_code, action, detail, request) {
  const ip = request?.headers?.get('cf-connecting-ip') || '';
  await env.DB.prepare(
    'INSERT INTO operation_log (owner_code, action, detail, ip) VALUES (?, ?, ?, ?)'
  ).bind(owner_code, action, JSON.stringify(detail), ip).run();
}
