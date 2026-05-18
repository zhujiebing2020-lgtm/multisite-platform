// 触发链：数据写入后自动生成下游卡片
// daily_dashboard → action-pitcher 卡片
// intake → 更新 claim/dev-req 卡片

const TIER_THRESHOLDS = { S: 3, A: 5 }; // CPHQ ≤3=S, ≤5=A, >5=B, 0HVU+spend=R

export async function triggerDownstream(env, cardType) {
  if (cardType === 'daily_dashboard') {
    await generateActionCard(env);
  }
}

export async function triggerIntakeDownstream(env, intake) {
  await updateClaimCards(env, intake);
}

async function generateActionCard(env) {
  // 取最近7天 ad_daily 数据
  const { results: rows } = await env.DB.prepare(
    `SELECT group_name, owner, date, spend, hvu, cphq
     FROM ad_daily WHERE date >= date('now', '-7 days') ORDER BY date DESC`
  ).all();

  if (!rows.length) return;

  // 按组聚合
  const groups = {};
  for (const r of rows) {
    if (!groups[r.group_name]) groups[r.group_name] = { owner: r.owner, days: [], total_spend: 0, total_hvu: 0 };
    groups[r.group_name].days.push(r);
    groups[r.group_name].total_spend += r.spend || 0;
    groups[r.group_name].total_hvu += r.hvu || 0;
  }

  // 分层 + 按投手分组
  const byPitcher = {};
  for (const [name, g] of Object.entries(groups)) {
    const cphq = g.total_hvu > 0 ? g.total_spend / g.total_hvu : 999;
    let tier;
    if (g.total_hvu === 0 && g.total_spend > 5) tier = 'R';
    else if (cphq <= TIER_THRESHOLDS.S) tier = 'S';
    else if (cphq <= TIER_THRESHOLDS.A) tier = 'A';
    else tier = 'B';

    const owner = g.owner || 'unknown';
    if (!byPitcher[owner]) byPitcher[owner] = { continue: [], stop: [] };

    const entry = { group: name, cphq: `$${cphq.toFixed(2)}`, hvu: g.total_hvu, tier };
    if (tier === 'R') {
      byPitcher[owner].stop.push({ ...entry, action: '暂停', reason: `7天$${g.total_spend.toFixed(0)}花费·0HVU` });
    } else {
      byPitcher[owner].continue.push({ ...entry, budget: '维持', reason: `7天${g.total_hvu}HVU·CPHQ $${cphq.toFixed(2)}` });
    }
  }

  // 按 CPHQ 排序
  for (const p of Object.values(byPitcher)) {
    p.continue.sort((a, b) => parseFloat(a.cphq.slice(1)) - parseFloat(b.cphq.slice(1)));
  }

  const today = new Date().toISOString().slice(0, 10);
  const card = {
    meta: {
      card_id: `action-pitcher-${today}`,
      card_type: 'action_list',
      channel: 'facebook',
      title: `投手行动指令 · ${today}`,
      last_updated: today,
      data_date: today,
      target_role: ['投手'],
      rule_source: 'auto-trigger: daily_dashboard → action_list'
    },
    context: {
      constraint: '结算页0转化未修·策略基于HVU/CPHQ',
      strategy: '基于最近7天数据自动生成·S/A类维持·R类暂停',
      valid_until: '下次数据更新自动刷新'
    },
    actions_by_pitcher: byPitcher
  };

  await env.DB.prepare(
    `INSERT OR REPLACE INTO dashboard_cards (card_id, card_type, channel, data_date, payload, last_updated)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`
  ).bind(card.meta.card_id, 'action_list', 'facebook', today, JSON.stringify(card)).run();
}

async function updateClaimCards(env, intake) {
  if (!intake || !intake.must_fix_today) return;

  const today = intake.date || new Date().toISOString().slice(0, 10);

  for (const fix of intake.must_fix_today) {
    if (!fix.linked_claim) continue;

    // 读取现有 claim card
    const existing = await env.DB.prepare(
      'SELECT payload FROM dashboard_cards WHERE card_id = ?'
    ).bind(fix.linked_claim).first();

    if (existing) {
      const card = JSON.parse(existing.payload);
      // 追加最新证据到 signals
      card.signals = card.signals || [];
      const alreadyHas = card.signals.some(s => s.label && s.label.includes(today));
      if (!alreadyHas) {
        card.signals.push({
          label: `${today} 承接端报告`,
          value: fix.impact,
          source: intake.source_report || 'intake API'
        });
        card.meta.last_updated = today;
        await env.DB.prepare(
          `UPDATE dashboard_cards SET payload = ?, last_updated = datetime('now') WHERE card_id = ?`
        ).bind(JSON.stringify(card), fix.linked_claim).run();
      }
    }
  }
}
