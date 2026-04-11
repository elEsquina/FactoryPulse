'use strict';

const API = '/api/v1';
const state = {
  dashboard: null,
  factoryFloor: null,
  risk: [],
  products: [],
};

const SUGGESTIONS = [
  'Which products are assigned to plant 1903?',
  'Which products are most similar to AT5X5K?',
  'Which products show underperformance risk?',
  'Compare group A and group M operational performance.',
  'Total delivery for subgroup ATN in units.',
];

const GROUP_COLORS = ['#6ba6ea', '#4a8fdf', '#8abaf0', '#5b95df', '#9bc4f3'];

window.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  initChips();
  bindEvents();
  await refreshAll();

  setInterval(() => {
    refreshAll().catch((err) => console.error('refresh failed', err));
  }, 90_000);
});

function bindEvents() {
  document.getElementById('refresh-all')?.addEventListener('click', refreshAll);
  document.getElementById('refresh-risk')?.addEventListener('click', async () => {
    await loadRisk();
    renderRiskTable();
    renderRiskProfile();
  });
  document.getElementById('product-filter')?.addEventListener('input', (event) => {
    renderProductList(event.target.value || '');
  });
  document.getElementById('send-btn')?.addEventListener('click', runCopilot);
  document.getElementById('copilot-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      runCopilot();
    }
  });
}

function initTabs() {
  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.target;
      document.querySelectorAll('.tab').forEach((node) => node.classList.toggle('active', node === tab));
      document.querySelectorAll('.panel').forEach((panel) => panel.classList.toggle('active', panel.id === `panel-${target}`));
    });
  });
}

function initChips() {
  const chips = document.getElementById('chips');
  if (!chips) return;
  chips.innerHTML = SUGGESTIONS.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join('');
  chips.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const input = document.getElementById('copilot-input');
      if (input) input.value = chip.textContent || '';
    });
  });
}

async function refreshAll() {
  await Promise.all([loadDashboard(), loadFactoryFloor(), loadRisk(), loadProducts()]);
  renderKPIs();
  renderFlowChart();
  renderGroupDonut();
  renderTopDeliveryBars();
  renderPlantLoad();
  renderStoragePressure();
  renderRiskTable();
  renderRiskProfile();
  renderProductList('');
}

async function loadDashboard() {
  state.dashboard = await apiFetch(`${API}/analytics/dashboard`);
}

async function loadFactoryFloor() {
  state.factoryFloor = await apiFetch(`${API}/analytics/factory-floor?plant_limit=12&storage_limit=12`);
}

async function loadRisk() {
  state.risk = await apiFetch(`${API}/analytics/risk?limit=25`);
}

async function loadProducts() {
  state.products = await apiFetch(`${API}/products?limit=250`);
}

function renderKPIs() {
  const kpi = state.dashboard?.kpi || {};
  animateNumber('kpi-products', kpi.products || 0);
  animateNumber('kpi-plants', kpi.plants || 0);
  animateNumber('kpi-storages', kpi.storages || 0);
  animateNumber('kpi-risk', kpi.at_risk_products || 0);
}

function renderFlowChart() {
  const svg = document.getElementById('flow-chart');
  if (!svg) return;

  const rows = state.dashboard?.monthly_flow || [];
  const grouped = new Map();
  rows.forEach((row) => {
    if (!grouped.has(row.date)) grouped.set(row.date, { production: 0, delivery: 0 });
    grouped.get(row.date)[row.metric] = Number(row.total || 0);
  });

  const series = [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  if (!series.length) {
    svg.innerHTML = '<text x="20" y="30" fill="#9aabbe">No trend data available</text>';
    return;
  }

  const width = 700;
  const height = 320;
  const pad = 34;
  const max = Math.max(...series.map(([, v]) => Math.max(v.production, v.delivery)), 1);

  const px = (i) => pad + (i / Math.max(series.length - 1, 1)) * (width - pad * 2);
  const py = (v) => height - pad - (v / max) * (height - pad * 2);

  const delivery = series.map(([, v], i) => `${px(i)},${py(v.delivery)}`).join(' ');
  const production = series.map(([, v], i) => `${px(i)},${py(v.production)}`).join(' ');

  svg.innerHTML = `
    <defs>
      <linearGradient id="line-del" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#2f7fd3"/>
        <stop offset="100%" stop-color="#6aa3e4"/>
      </linearGradient>
      <linearGradient id="line-prod" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#1f5fa8"/>
        <stop offset="100%" stop-color="#4f96dc"/>
      </linearGradient>
    </defs>
    <polyline points="${delivery}" fill="none" stroke="url(#line-del)" stroke-width="3"></polyline>
    <polyline points="${production}" fill="none" stroke="url(#line-prod)" stroke-width="3"></polyline>
    <text x="26" y="22" fill="#2f7fd3" font-size="12">Delivery</text>
    <text x="94" y="22" fill="#1f5fa8" font-size="12">Production</text>
  `;
}

function renderGroupDonut() {
  const donut = document.getElementById('group-donut');
  const legend = document.getElementById('group-legend');
  if (!donut || !legend) return;

  const groups = state.dashboard?.groups || [];
  const total = groups.reduce((sum, g) => sum + Number(g.count || 0), 0) || 1;

  const cx = 120;
  const cy = 120;
  const r = 78;
  const stroke = 22;
  let angle = -Math.PI / 2;

  const arcs = [];
  const rows = [];

  groups.forEach((g, i) => {
    const value = Number(g.count || 0);
    const delta = (value / total) * Math.PI * 2;
    const color = GROUP_COLORS[i % GROUP_COLORS.length];
    arcs.push(arcPath(cx, cy, r, angle, angle + delta, stroke, color));
    rows.push(`<div class="legend-item"><span><span class="swatch" style="background:${color}"></span>Group ${esc(g.group || '?')}</span><strong>${num(value)}</strong></div>`);
    angle += delta;
  });

  donut.innerHTML = `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#2f3a49" stroke-width="${stroke}"></circle>
    ${arcs.join('')}
    <text x="${cx}" y="${cy - 2}" text-anchor="middle" fill="#e7edf6" font-size="18" font-weight="800">${num(total)}</text>
    <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="#9aabbe" font-size="12">Products</text>
  `;
  legend.innerHTML = rows.join('');
}

function arcPath(cx, cy, r, start, end, strokeWidth, color) {
  const x1 = cx + Math.cos(start) * r;
  const y1 = cy + Math.sin(start) * r;
  const x2 = cx + Math.cos(end) * r;
  const y2 = cy + Math.sin(end) * r;
  const largeArc = end - start > Math.PI ? 1 : 0;
  return `<path d="M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round"></path>`;
}

function renderTopDeliveryBars() {
  const holder = document.getElementById('delivery-bars');
  if (!holder) return;

  const rows = state.dashboard?.top_delivery || [];
  if (!rows.length) {
    holder.innerHTML = '<div>No delivery data available.</div>';
    return;
  }

  const max = Math.max(...rows.map((r) => Number(r.delivery_units || 0)), 1);
  holder.innerHTML = rows.map((r) => {
    const width = (Number(r.delivery_units || 0) / max) * 100;
    return `
      <div class="bar-row">
        <div>${esc(r.code)}</div>
        <div class="track"><div class="fill" data-width="${width}"></div></div>
        <div>${num(r.delivery_units)}</div>
      </div>
    `;
  }).join('');
  animateFill(holder);
}

function renderPlantLoad() {
  const holder = document.getElementById('plant-load');
  if (!holder) return;

  const rows = state.factoryFloor?.plant_load || [];
  if (!rows.length) {
    holder.innerHTML = '<div>No plant data available.</div>';
    return;
  }

  const max = Math.max(...rows.map((r) => Number(r.assigned_products || 0)), 1);
  holder.innerHTML = rows.map((r) => {
    const width = (Number(r.assigned_products || 0) / max) * 100;
    const ratio = Number(r.delivery_production_ratio || 0) * 100;
    const color = ratio < 60 ? '#c8454f' : ratio < 85 ? '#cc8a00' : '#1e8e5a';
    return `
      <div class="stack-item">
        <div class="stack-head"><strong>Plant ${esc(r.plant_id)}</strong><span>${num(r.assigned_products)} products</span></div>
        <div class="track"><div class="fill" data-width="${width}"></div></div>
        <div style="margin-top:6px;color:#9aabbe">Fulfillment ratio: <strong style="color:${color}">${ratio.toFixed(1)}%</strong></div>
      </div>
    `;
  }).join('');
  animateFill(holder);
}

function renderStoragePressure() {
  const holder = document.getElementById('storage-heat');
  if (!holder) return;

  const rows = state.factoryFloor?.storage_load || [];
  if (!rows.length) {
    holder.innerHTML = '<div>No storage data available.</div>';
    return;
  }

  const max = Math.max(...rows.map((r) => Number(r.products || 0)), 1);
  holder.innerHTML = rows.map((r) => {
    const width = (Number(r.products || 0) / max) * 100;
    return `
      <div class="stack-item">
        <div class="stack-head"><strong>Storage ${esc(r.storage_id)}</strong><span>${num(r.products)} products</span></div>
        <div class="track"><div class="fill" data-width="${width}" style="background:#4f96dc"></div></div>
      </div>
    `;
  }).join('');
  animateFill(holder);
}

function renderRiskTable() {
  const body = document.getElementById('risk-table');
  if (!body) return;

  if (!state.risk.length) {
    body.innerHTML = '<tr><td colspan="4">No risk records available.</td></tr>';
    return;
  }

  body.innerHTML = state.risk.map((r) => {
    const cls = String(r.risk_level || 'LOW').toLowerCase();
    return `
      <tr>
        <td>${esc(r.code)}</td>
        <td>${esc(r.grp || '-')}</td>
        <td>${pct(r.fulfillment_ratio)}</td>
        <td><span class="risk-badge risk-${cls}">${esc(r.risk_level || 'LOW')}</span></td>
      </tr>
    `;
  }).join('');
}

function renderRiskProfile() {
  const svg = document.getElementById('risk-radar');
  if (!svg) return;

  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  state.risk.forEach((r) => {
    const key = String(r.risk_level || 'LOW').toUpperCase();
    if (counts[key] !== undefined) counts[key] += 1;
  });

  const values = [counts.HIGH, counts.MEDIUM, counts.LOW];
  const labels = ['HIGH', 'MEDIUM', 'LOW'];
  const colors = ['#c8454f', '#cc8a00', '#1e8e5a'];
  const max = Math.max(...values, 1);

  const baseY = 215;
  const bars = values.map((v, i) => {
    const h = (v / max) * 140;
    const x = 70 + i * 145;
    return `
      <rect x="${x}" y="${baseY - h}" width="85" height="${h}" fill="${colors[i]}" rx="8"></rect>
      <text x="${x + 42}" y="${baseY + 18}" text-anchor="middle" fill="#9aabbe" font-size="12">${labels[i]}</text>
      <text x="${x + 42}" y="${baseY - h - 8}" text-anchor="middle" fill="#e7edf6" font-size="13">${v}</text>
    `;
  }).join('');

  svg.innerHTML = `<line x1="50" y1="215" x2="470" y2="215" stroke="#2f3a49"></line>${bars}`;
}

function renderProductList(filterText) {
  const list = document.getElementById('product-list');
  if (!list) return;

  const q = String(filterText || '').toLowerCase().trim();
  const items = !q
    ? state.products
    : state.products.filter((p) => (p.code || '').toLowerCase().includes(q) || (p.grp || '').toLowerCase().includes(q));

  if (!items.length) {
    list.innerHTML = '<div class="product-item">No matching products</div>';
    return;
  }

  list.innerHTML = items.map((p) => `
    <div class="product-item" data-code="${esc(p.code)}">
      <strong>${esc(p.code)}</strong><br>
      <span>Group ${esc(p.grp || '-')} · Subgroup ${esc(p.subgroup || '-')}</span>
    </div>
  `).join('');

  list.querySelectorAll('.product-item').forEach((el) => {
    el.addEventListener('click', async () => {
      const code = el.dataset.code;
      if (!code) return;
      await renderProductDetail(code);
    });
  });
}

async function renderProductDetail(code) {
  const pane = document.getElementById('product-detail');
  if (!pane) return;
  pane.textContent = `Loading ${code}...`;

  try {
    const p = await apiFetch(`${API}/products/${encodeURIComponent(code)}`);
    const related = (p.related_products || []).map((r) => `${esc(r.peer_code)} (${num(r.shared_links)} links)`).join('<br>') || 'None';

    pane.innerHTML = `
      <strong style="color:#8abaf0">${esc(p.code)}</strong><br>
      Group ${esc(p.grp)} · Subgroup ${esc(p.subgroup)}<br>
      Plants: ${esc((p.plants || []).join(', ') || 'none')}<br>
      Storages: ${esc((p.storages || []).join(', ') || 'none')}<br>
      Avg Delivery: ${num(p.avg_delivery)}<br>
      Avg Production: ${num(p.avg_production)}<br>
      Avg Sales Order: ${num(p.avg_sales_order)}<br>
      Observation Count: ${num(p.observation_count)}<br><br>
      <strong>Related Products</strong><br>${related}
    `;
  } catch (err) {
    pane.textContent = `Failed to load product: ${err.message}`;
  }
}

async function runCopilot() {
  const input = document.getElementById('copilot-input');
  if (!input) return;
  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  appendBubble('user', question);
  const pending = appendBubble('ai', 'Analyzing your question...');

  try {
    const result = await apiFetch(`${API}/copilot/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    pending.remove();
    appendBubble('ai', esc(result.answer), {
      strategy: result.strategy,
      reason: result.route_reason,
      cypher: result.cypher,
    });
  } catch (err) {
    pending.remove();
    appendBubble('ai', `Request failed: ${esc(err.message)}`);
  }
}

function appendBubble(role, text, meta = null) {
  const box = document.getElementById('chat-box');
  if (!box) return document.createElement('div');

  const div = document.createElement('div');
  div.className = `bubble ${role}`;
  div.innerHTML = `<div>${String(text).replace(/\n/g, '<br>')}</div>`;

  if (meta) {
    const info = [];
    if (meta.strategy) info.push(`<span class="strategy-tag">${esc(meta.strategy)}</span>`);
    if (meta.reason) info.push(`<div>${esc(meta.reason)}</div>`);
    if (meta.cypher) info.push(`<div><strong>Cypher:</strong> <code>${esc(meta.cypher)}</code></div>`);

    const m = document.createElement('div');
    m.className = 'meta';
    m.innerHTML = info.join('');
    div.appendChild(m);
  }

  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function animateFill(root) {
  requestAnimationFrame(() => {
    root.querySelectorAll('.fill').forEach((el) => {
      el.style.width = `${el.dataset.width}%`;
    });
  });
}

function animateNumber(id, target) {
  const node = document.getElementById(id);
  if (!node) return;

  const from = Number(node.textContent.replace(/,/g, '') || 0);
  const to = Number(target || 0);
  const start = performance.now();
  const duration = 700;

  function tick(now) {
    const p = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    node.textContent = Math.round(from + (to - from) * eased).toLocaleString();
    if (p < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

async function apiFetch(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);

  let response;
  try {
    response = await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      // ignore
    }
    throw new Error(detail);
  }

  return response.json();
}

function num(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function pct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
