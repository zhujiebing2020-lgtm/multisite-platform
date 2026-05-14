// src/index.js — Worker 入口
// 路由: API → 子域 → 静态资源

import { handleUpload } from './api/upload.js';
import { handleRequest } from './api/request.js';
import { handleAuth, verifySession } from './api/auth.js';
import { handleTriggerAgent } from './api/trigger-agent.js';
import { handleResults, handleResultDetail } from './api/results.js';
import { handleUploadAndParse, handleDashboard } from './api/parse-xlsx.js';

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

    // 子域路由
    const host = url.hostname.toLowerCase();
    if (url.pathname === '/' && host.endsWith('.z-jb.com') && !ROOT_HOSTS.has(host)) {
      const subdomain = host.replace(/\.z-jb\.com$/, '');
      if (/^[a-z0-9_-]+$/.test(subdomain)) {
        const subUrl = new URL(`/site/${subdomain}.html`, url);
        const subResp = await env.ASSETS.fetch(new Request(subUrl, request));
        if (subResp.status === 200) return subResp;
      }
    }

    return env.ASSETS.fetch(request);
  },
};
