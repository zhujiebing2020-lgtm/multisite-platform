// src/index.js — Worker 入口
// 路由: API → 子域 → 静态资源

import { handleUpload } from './api/upload.js';
import { handleRequest } from './api/request.js';
import { handleAuth, handleLogout, verifySession } from './api/auth.js';
import { handleTriggerAgent } from './api/trigger-agent.js';
import { handleResults, handleResultDetail, handleClearPending } from './api/results.js';
import { handleUploadAndParse, handleDashboard } from './api/parse-xlsx.js';
import { handleIngest } from './api/ingest.js';
import { handleAdminUsers, handleAdminUser, handleAdminLogs } from './api/admin.js';
import { handleRecommendations, handleRecommendationUpdate } from './api/recommendations.js';
import { handleKnowledge, handleKnowledgeToRule, handleScripts, handleKnowledgeAdd } from './api/knowledge.js';
import { handleAgentsStatus, handleAgentTrigger, handleCrossSiteSummary, handleAcceptData } from './api/agents.js';
import { handleUploadImage, handleUploadImageDirect, handleR2Get, handleKlingGenerate, handleKlingStatus, handleGenerateScenes, handleGenerateScenesStatus } from './api/kling.js';
import { handleFetchScene } from './api/fetch-scene.js';
import { handleCraveDashboard } from './api/crave-dashboard.js';

const ROOT_HOSTS = new Set(['z-jb.com', 'www.z-jb.com']);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 公开 API：登录
    if (request.method === 'POST' && url.pathname === '/api/auth') {
      return handleAuth(request, env);
    }

    // 退出登录
    if (request.method === 'POST' && url.pathname === '/api/logout') {
      return handleLogout();
    }

    // Admin API
    if (url.pathname === '/api/admin/users' && (request.method === 'GET' || request.method === 'POST')) {
      return handleAdminUsers(request, env);
    }
    if (url.pathname.startsWith('/api/admin/users/') && (request.method === 'PUT' || request.method === 'DELETE')) {
      const code = url.pathname.split('/').pop();
      return handleAdminUser(request, env, code);
    }
    if (url.pathname === '/api/admin/logs' && request.method === 'GET') {
      return handleAdminLogs(request, env);
    }

    // 建议卡片
    if (url.pathname === '/api/recommendations' && request.method === 'GET') {
      return handleRecommendations(request, env);
    }
    if (url.pathname.startsWith('/api/recommendations/') && request.method === 'PUT') {
      const id = url.pathname.split('/').pop();
      return handleRecommendationUpdate(request, env, id);
    }
    // 知识库
    if (url.pathname === '/api/knowledge' && request.method === 'GET') {
      return handleKnowledge(request, env);
    }
    if (url.pathname === '/api/knowledge/add' && request.method === 'POST') {
      return handleKnowledgeAdd(request, env);
    }
    if (url.pathname.match(/^\/api\/knowledge\/\d+\/to-rule$/) && request.method === 'POST') {
      const id = url.pathname.split('/')[3];
      return handleKnowledgeToRule(request, env, id);
    }
    // 剧本库
    if (url.pathname === '/api/scripts' && (request.method === 'GET' || request.method === 'POST')) {
      return handleScripts(request, env);
    }
    // Agent 状态
    if (url.pathname === '/api/agents/status' && request.method === 'GET') {
      return handleAgentsStatus(request, env);
    }
    if (url.pathname.startsWith('/api/agents/') && url.pathname.endsWith('/trigger') && request.method === 'POST') {
      const agentId = url.pathname.split('/')[3];
      return handleAgentTrigger(request, env, agentId);
    }
    // 跨站汇总
    if (url.pathname === '/api/cross-site/summary' && request.method === 'GET') {
      return handleCrossSiteSummary(request, env);
    }
    // 承接诊断数据
    if (url.pathname === '/api/accept/data' && request.method === 'GET') {
      return handleAcceptData(request, env);
    }
    // 落地页剧情解析
    if (url.pathname === '/api/fetch-scene' && request.method === 'POST') {
      return handleFetchScene(request, env);
    }
    // Kling JWT 调试
    if (url.pathname === '/api/test-kling' && request.method === 'GET') {
      try {
        const b64url = (str) => btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
        const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
        const now = Math.floor(Date.now() / 1000);
        const payload = b64url(JSON.stringify({ iss: env.KLING_API_KEY, iat: now, exp: now + 1800, nbf: now - 5 }));
        const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.KLING_SECRET_KEY), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
        const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${header}.${payload}`));
        const sigStr = btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
        const token = `${header}.${payload}.${sigStr}`;
        const klingBase = env.KLING_BASE_URL || 'https://api.klingai.com';
        const resp = await fetch(`${klingBase}/v1/images/generations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ prompt: 'a red apple', n: 1, aspect_ratio: '1:1' }),
        });
        const data = await resp.text();
        return new Response(JSON.stringify({ status: resp.status, kling_key_prefix: (env.KLING_API_KEY||'').slice(0,8), body: data.slice(0, 500) }), { headers: { 'Content-Type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), { headers: { 'Content-Type': 'application/json' } });
      }
    }
    // OpenRouter 连通测试
    if (url.pathname === '/api/test-openrouter' && request.method === 'GET') {
      try {
        const resp = await fetch('https://openrouter.ai/api/v1/chat/completions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${env.OPENROUTER_API_KEY}` },
          body: JSON.stringify({ model: 'qwen/qwen-2.5-72b-instruct', messages: [{ role: 'user', content: 'Say hello in 5 words' }], max_tokens: 50 }),
        });
        const data = await resp.json();
        return new Response(JSON.stringify({ status: resp.status, data }), { headers: { 'Content-Type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), { headers: { 'Content-Type': 'application/json' } });
      }
    }
    // 图片上传 + Kling 视频生成
    if (url.pathname === '/api/upload/image' && request.method === 'POST') {
      return handleUploadImage(request, env);
    }
    if (url.pathname === '/api/upload/image-direct' && request.method === 'PUT') {
      return handleUploadImageDirect(request, env);
    }
    if (url.pathname.startsWith('/api/r2/') && request.method === 'GET') {
      const key = url.pathname.replace('/api/r2/', '');
      return handleR2Get(request, env, decodeURIComponent(key));
    }
    if (url.pathname === '/api/kling/generate-clip' && request.method === 'POST') {
      return handleKlingGenerate(request, env, ctx);
    }
    if (url.pathname.startsWith('/api/kling/status/') && request.method === 'GET') {
      const taskId = url.pathname.split('/').pop();
      return handleKlingStatus(request, env, taskId);
    }
    if (url.pathname === '/api/image/generate-scenes' && request.method === 'POST') {
      return handleGenerateScenes(request, env, ctx);
    }
    if (url.pathname.startsWith('/api/image/generate-scenes/status/') && request.method === 'GET') {
      const batchId = url.pathname.split('/').pop();
      return handleGenerateScenesStatus(request, env, batchId);
    }

    // 需要鉴权的 API
    if (request.method === 'POST' && url.pathname === '/api/upload') {
      return handleUploadAndParse(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/ingest') {
      return handleIngest(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/request') {
      return handleRequest(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/trigger-agent') {
      return handleTriggerAgent(request, env, ctx);
    }
    if (request.method === 'GET' && url.pathname === '/api/dashboard') {
      return handleDashboard(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/api/results') {
      return handleResults(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/results/clear-pending') {
      return handleClearPending(request, env);
    }
    if (request.method === 'GET' && url.pathname.startsWith('/api/results/')) {
      return handleResultDetail(request, env);
    }
    // 回调（Actions 调用，用 secret 验证）
    if (request.method === 'POST' && url.pathname === '/api/callback') {
      const { handleCallback } = await import('./api/callback.js');
      return handleCallback(request, env);
    }

    // 子域路由：*.z-jb.com → 子站页面
    const host = url.hostname.toLowerCase();
    // crave.z-jb.com → API + 前端
    if (host === 'crave.z-jb.com') {
      if (url.pathname.startsWith('/api/crave/')) {
        return handleCraveDashboard(request, env, url.pathname);
      }
      return env.ASSETS.fetch(new Request(`${url.origin}/crave.html`));
    }
    if (host.endsWith('.z-jb.com') && !ROOT_HOSTS.has(host)) {
      const subdomain = host.replace(/\.z-jb\.com$/, '');
      if (/^[a-z0-9_-]+$/.test(subdomain) && subdomain !== 'crave') {
        // 子站直接用主 app，投手登录后按权限看对应站数据
        return env.ASSETS.fetch(new Request(`${url.origin}/app.html`));
      }
    }

    // 根域 / → app.html
    if (url.pathname === '/') {
      return env.ASSETS.fetch(new Request(`${url.origin}/app.html`));
    }

    // 其他静态资源
    const assetResp = await env.ASSETS.fetch(request);
    if (assetResp.status === 404) {
      return env.ASSETS.fetch(new Request(`${url.origin}/app.html`));
    }
    return assetResp;
  },
};
