// src/index.js — Worker 入口
// 路由: API → 子域 → 静态资源

import { handleUpload } from './api/upload.js';
import { handleRequest } from './api/request.js';
import { handleAuth, handleLogout, verifySession } from './api/auth.js';
import { handleTriggerAgent } from './api/trigger-agent.js';
import { handleResults, handleResultDetail } from './api/results.js';
import { handleUploadAndParse, handleDashboard } from './api/parse-xlsx.js';
import { handleIngest } from './api/ingest.js';
import { handleAdminUsers, handleAdminUser, handleAdminLogs } from './api/admin.js';
import { handleRecommendations, handleRecommendationUpdate } from './api/recommendations.js';
import { handleKnowledge, handleKnowledgeToRule } from './api/knowledge.js';
import { handleAgentsStatus, handleAgentTrigger, handleCrossSiteSummary, handleAcceptData } from './api/agents.js';

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
    if (url.pathname.match(/^\/api\/knowledge\/\d+\/to-rule$/) && request.method === 'POST') {
      const id = url.pathname.split('/')[3];
      return handleKnowledgeToRule(request, env, id);
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
    // crave.z-jb.com → proxy GitHub Pages（保持 URL 不变）
    if (host === 'crave.z-jb.com') {
      const ghPath = url.pathname === '/' ? '/crave-AI/' : `/crave-AI${url.pathname}`;
      const ghUrl = `https://zhujiebing2020-lgtm.github.io${ghPath}${url.search}`;
      const ghResp = await fetch(ghUrl, {
        headers: { 'User-Agent': 'z-jb-proxy', 'Accept': request.headers.get('Accept') || '*/*' },
        redirect: 'follow',
      });
      const body = ghResp.body;
      const headers = new Headers(ghResp.headers);
      headers.delete('x-frame-options');
      // 注入返回总控台链接（仅 HTML）
      const ct = headers.get('content-type') || '';
      if (ct.includes('text/html')) {
        let html = await ghResp.text();
        const backLink = '<div style="position:fixed;top:0;left:0;right:0;z-index:9999;background:#1C1814;padding:6px 16px;font-size:12px;display:flex;justify-content:space-between;align-items:center"><a href="https://z-jb.com" style="color:#E8603A;text-decoration:none;font-weight:600">← 返回总控台</a><span style="color:#73685F">crave.z-jb.com</span></div>';
        html = html.replace('<body', '<body style="padding-top:32px"');
        html = html.replace('</body>', backLink + '</body>');
        return new Response(html, { status: ghResp.status, headers });
      }
      return new Response(body, { status: ghResp.status, headers });
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
