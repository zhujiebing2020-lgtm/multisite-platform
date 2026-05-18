// src/api/fetch-scene.js — Cloudflare Browser Rendering 渲染 SPA 提取剧情

import { verifySession } from './auth.js';
import puppeteer from '@cloudflare/puppeteer';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

export async function handleFetchScene(request, env) {
  const user = await verifySession(request, env);
  if (!user) return json({ error: '未登录' }, 401);

  const { url } = await request.json().catch(() => ({}));
  if (!url || !url.includes('creviatech.com')) {
    return json({ error: '仅支持 creviatech.com 页面' }, 400);
  }

  let browser;
  try {
    browser = await puppeteer.launch(env.BROWSER);
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 });
    // 点击年龄验证按钮（如果存在）
    await page.waitForSelector('button', { timeout: 5000 }).catch(() => {});
    const clicked = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')];
      const ageBtn = btns.find(b => /YES|是|确认|I AM/i.test(b.textContent));
      if (ageBtn) { ageBtn.click(); return true; }
      return false;
    });
    // 等待 SPA 数据加载完成
    await page.waitForFunction(() => {
      return document.body.innerText.includes('Story Synopsis') || document.querySelector('h1')?.textContent?.length > 5;
    }, { timeout: 15000 }).catch(() => {});

    const data = await page.evaluate(() => {
      const ogTitle = document.querySelector('meta[property="og:title"]');
      const title = ogTitle ? ogTitle.content.replace(/^CRAVE AI\s*[-–]\s*/, '').trim() : (document.querySelector('h1')?.textContent || '').trim();

      const synopsisEl = [...document.querySelectorAll('p')].find(p => p.previousElementSibling?.textContent?.includes('Story Synopsis'));
      const synopsis = synopsisEl ? synopsisEl.textContent.trim() : '';

      const tagEls = document.querySelectorAll('span');
      const tags = [...tagEls].filter(s => s.textContent.startsWith('#')).map(s => s.textContent.replace('#', '').trim());

      const ogImage = document.querySelector('meta[property="og:image"]');
      const coverImage = ogImage ? ogImage.content : '';

      return { title, synopsis, tags, coverImage };
    });

    await browser.close();

    if (!data.title && !data.synopsis) {
      return json({ error: '未能从页面中提取剧情数据' });
    }

    return json({ ...data, url });
  } catch (e) {
    if (browser) await browser.close().catch(() => {});
    return json({ error: '渲染失败：' + e.message });
  }
}
