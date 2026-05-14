// src/index.js — Worker 入口
// 路由策略:
//   1. POST /api/upload, /api/request → API 处理
//   2. 子域 {site}.z-jb.com → 重写到 /site/{site}.html(若存在;否则回总览)
//   3. 其他 → 静态资源(view/)
//
// 子域路由表(后续加站只改这一处):
//   z-jb.com / www.z-jb.com           → /index.html (站群总览)
//   elysianu.z-jb.com                  → /site/elysianu.html
//   (后续) {site}.z-jb.com             → /site/{site}.html
//   crave.z-jb.com 不走这里(独立 CNAME 到 GitHub Pages,见 project_zjb_domain_architecture.md)

import { handleUpload } from './api/upload.js';
import { handleRequest } from './api/request.js';

const ROOT_HOSTS = new Set(['z-jb.com', 'www.z-jb.com']);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // API 路由
    if (request.method === 'POST' && url.pathname === '/api/upload') {
      return handleUpload(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/request') {
      return handleRequest(request, env);
    }

    // 子域路由(仅根路径走子站视图;子路径正常)
    const host = url.hostname.toLowerCase();
    if (url.pathname === '/' && host.endsWith('.z-jb.com') && !ROOT_HOSTS.has(host)) {
      const subdomain = host.replace(/\.z-jb\.com$/, '');
      if (/^[a-z0-9_-]+$/.test(subdomain)) {
        const subUrl = new URL(`/site/${subdomain}.html`, url);
        const subResp = await env.ASSETS.fetch(new Request(subUrl, request));
        if (subResp.status === 200) return subResp;
        // 不存在则回退到总览
      }
    }

    return env.ASSETS.fetch(request);
  },
};
