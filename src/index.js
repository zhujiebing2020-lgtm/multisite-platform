// src/index.js — Worker 入口
// 路由 /api/upload 和 /api/request 到处理函数，其余走静态资源

import { handleUpload } from './api/upload.js';
import { handleRequest } from './api/request.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/api/upload') {
      return handleUpload(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/request') {
      return handleRequest(request, env);
    }

    return env.ASSETS.fetch(request);
  },
};
