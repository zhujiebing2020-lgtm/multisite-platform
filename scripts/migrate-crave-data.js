#!/usr/bin/env node
// 迁移 crave-AI repo 数据到 z-jb.com Worker D1
// 用法: node scripts/migrate-crave-data.js

const fs = require('fs');
const path = require('path');

const CRAVE_REPO = path.resolve(__dirname, '../../crave-AI');
const API_BASE = process.env.API_BASE || 'https://crave.z-jb.com';

async function main() {
  const payload = { cards: {}, intake: [] };

  // 1. 读取 CARD_DATA from index.html
  const html = fs.readFileSync(path.join(CRAVE_REPO, 'index.html'), 'utf8');
  const cdStart = html.indexOf('const CARD_DATA = {') + 18;
  const cdSub = html.substring(cdStart);
  let depth = 0, cdEnd = 0;
  for (let i = 0; i < cdSub.length; i++) {
    if (cdSub[i] === '{') depth++;
    if (cdSub[i] === '}') depth--;
    if (depth === 0) { cdEnd = i + 1; break; }
  }
  payload.cards = JSON.parse(cdSub.substring(0, cdEnd));
  console.log(`Cards: ${Object.keys(payload.cards).length}`);

  // 2. 读取 intake JSONs
  const intakeDir = path.join(CRAVE_REPO, 'data/intake');
  for (const f of fs.readdirSync(intakeDir).filter(f => f.endsWith('.json') && f !== 'README.md')) {
    const data = JSON.parse(fs.readFileSync(path.join(intakeDir, f), 'utf8'));
    payload.intake.push(data);
  }
  console.log(`Intake reports: ${payload.intake.length}`);

  // 3. POST to sync endpoint
  console.log(`\nPOSTing to ${API_BASE}/api/crave/sync ...`);
  const resp = await fetch(`${API_BASE}/api/crave/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = await resp.json();
  console.log('Result:', JSON.stringify(result, null, 2));
}

main().catch(e => { console.error(e); process.exit(1); });
