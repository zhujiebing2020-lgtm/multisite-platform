// src/index.js — Worker 入口
// 路由: API → 子域 → 静态资源

import { handleUpload } from './api/upload.js';
import { handleRequest } from './api/request.js';
import { handleAuth, verifySession } from './api/auth.js';
import { handleTriggerAgent } from './api/trigger-agent.js';
import { handleResults, handleResultDetail } from './api/results.js';
import { handleUploadAndParse, handleDashboard } from './api/parse-xlsx.js';
import { handleIngest } from './api/ingest.js';

const ROOT_HOSTS = new Set(['z-jb.com', 'www.z-jb.com']);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 公开 API：登录
    if (request.method === 'POST' && url.pathname === '/api/auth') {
      return handleAuth(request, env);
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
      return handleTriggerAgent(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/api/dashboard') {
      return handleDashboard(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/api/results') {
      return handleResults(request, env);
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
    // crave.z-jb.com → 重定向到 GitHub Pages
    if (host === 'crave.z-jb.com') {
      if (url.pathname === '/') {
        return Response.redirect('https://zhujiebing2020-lgtm.github.io/crave-AI/', 302);
      }
      return Response.redirect(`https://zhujiebing2020-lgtm.github.io/crave-AI${url.pathname}`, 302);
    }
    if (host.endsWith('.z-jb.com') && !ROOT_HOSTS.has(host)) {
      const subdomain = host.replace(/\.z-jb\.com$/, '');
      if (/^[a-z0-9_-]+$/.test(subdomain) && url.pathname === '/') {
        return env.ASSETS.fetch(new Request(`${url.origin}/site/${subdomain}.html`));
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
