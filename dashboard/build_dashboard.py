"""Builds dashboard/index.html by embedding the actual detection results,
audit trail, and evaluation report as inline JSON -- so the dashboard is
always in sync with a real detector run, not mocked demo data."""
import json

from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DASHBOARD_DIR = Path(__file__).resolve().parent

with open(str(DATA_DIR / "detection_results.json")) as f:
    detection = json.load(f)
with open(str(DATA_DIR / "audit_trail.json")) as f:
    audit = json.load(f)
with open(str(DATA_DIR / "evaluation_report.json")) as f:
    evaluation = json.load(f)
with open(str(DATA_DIR / "rings_meta.json")) as f:
    rings_meta = json.load(f)

DATA_JSON = json.dumps({
    "detection": detection,
    "audit": audit,
    "evaluation": evaluation,
    "rings_meta": rings_meta,
}, separators=(",", ":"))

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RingFence — Collusion Detection Console</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0B0F14;
    --panel: #131A21;
    --panel-2: #0F151B;
    --border: #232C35;
    --text: #DCE4EA;
    --muted: #7C8A96;
    --amber: #E8A33D;
    --amber-dim: #E8A33D22;
    --cyan: #57B6D9;
    --cyan-dim: #57B6D922;
    --teal: #35B88A;
    --teal-dim: #35B88A22;
    --rose: #D9707A;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  .mono { font-family: 'IBM Plex Mono', monospace; }
  .display { font-family: 'Space Grotesk', sans-serif; }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 28px;
    border-bottom: 1px solid var(--border);
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand-mark {
    width: 22px; height: 22px;
    border: 2px solid var(--amber);
    border-radius: 50%;
    position: relative;
  }
  .brand-mark::after {
    content: '';
    position: absolute; inset: 5px;
    border: 2px solid var(--cyan);
    border-radius: 50%;
  }
  .brand-name { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 16px; letter-spacing: 0.2px; }
  .status-pill {
    display: flex; align-items: center; gap: 7px;
    font-size: 12.5px; color: var(--muted);
    padding: 5px 12px; border: 1px solid var(--border); border-radius: 100px;
  }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 8px var(--teal); }

  .hero {
    padding: 36px 28px 28px;
    border-bottom: 1px solid var(--border);
  }
  .hero-head { max-width: 620px; margin-bottom: 26px; }
  .hero-head h1 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 26px; font-weight: 600; margin: 0 0 8px;
  }
  .hero-head p { color: var(--muted); margin: 0; font-size: 14px; }

  .kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  .kpi { background: var(--panel); padding: 16px 18px; }
  .kpi-label { color: var(--muted); font-size: 11.5px; text-transform: none; margin-bottom: 8px; }
  .kpi-value { font-family: 'Space Grotesk', sans-serif; font-size: 26px; font-weight: 600; }
  .kpi-value.amber { color: var(--amber); }
  .kpi-value.teal { color: var(--teal); }
  .kpi-sub { font-size: 11.5px; color: var(--muted); margin-top: 4px; }

  .main {
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 0;
    min-height: 560px;
  }
  .queue {
    border-right: 1px solid var(--border);
    padding: 20px 0;
  }
  .queue-head { padding: 0 20px 14px; display: flex; align-items: center; justify-content: space-between; }
  .queue-head h2 { font-family: 'Space Grotesk', sans-serif; font-size: 14px; font-weight: 600; margin: 0; }
  .queue-head span { color: var(--muted); font-size: 12px; }

  .cluster-item {
    padding: 13px 20px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .cluster-item:hover { background: var(--panel-2); }
  .cluster-item.active { background: var(--panel-2); border-left: 2px solid var(--amber); padding-left: 18px; }
  .cluster-item-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
  .cluster-id { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--muted); }
  .risk-badge {
    font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 13px;
    padding: 2px 9px; border-radius: 5px;
  }
  .risk-badge.flagged { background: var(--amber-dim); color: var(--amber); }
  .risk-badge.clear { background: var(--teal-dim); color: var(--teal); }
  .cluster-item-meta { color: var(--muted); font-size: 12px; }

  .detail { padding: 24px 28px; }
  .detail-empty { color: var(--muted); padding: 60px 20px; text-align: center; }

  .detail-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }
  .detail-title { font-family: 'Space Grotesk', sans-serif; font-size: 19px; font-weight: 600; margin: 0 0 6px; }
  .detail-sub { color: var(--muted); font-size: 13px; }
  .action-tag {
    font-family: 'IBM Plex Mono', monospace; font-size: 11.5px;
    padding: 5px 11px; border-radius: 5px; white-space: nowrap;
  }
  .action-tag.review { background: var(--amber-dim); color: var(--amber); border: 1px solid #E8A33D44; }
  .action-tag.none { background: var(--teal-dim); color: var(--teal); border: 1px solid #35B88A44; }

  .signals { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
  .signal-card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
  .signal-label { font-size: 11px; color: var(--muted); margin-bottom: 8px; }
  .signal-bar-bg { height: 5px; background: var(--panel-2); border-radius: 3px; overflow: hidden; margin-bottom: 7px; }
  .signal-bar { height: 100%; background: var(--cyan); border-radius: 3px; }
  .signal-value { font-family: 'Space Grotesk', sans-serif; font-size: 15px; font-weight: 600; }

  .section-label { font-size: 12px; color: var(--muted); margin: 22px 0 10px; display:flex; align-items:center; gap: 8px;}
  .section-label::after { content: ''; flex: 1; height: 1px; background: var(--border); }

  .evidence-list { display: flex; flex-direction: column; gap: 6px; }
  .evidence-item {
    font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--text);
    background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 12px;
  }
  .evidence-item .res { color: var(--cyan); }

  .graph-wrap { display: flex; justify-content: center; padding: 10px 0 4px; }

  footer {
    padding: 16px 28px; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 12px; display: flex; justify-content: space-between;
  }

  @media (max-width: 860px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
    .main { grid-template-columns: 1fr; }
    .queue { border-right: none; border-bottom: 1px solid var(--border); }
    .signals { grid-template-columns: repeat(2, 1fr); }
  }
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="brand-mark"></div>
    <div class="brand-name">RingFence</div>
  </div>
  <div class="status-pill"><span class="dot"></span> Monitoring &nbsp;·&nbsp; defense-only</div>
</div>

<div class="hero">
  <div class="hero-head">
    <h1>Collusion ring detection console</h1>
    <p>Graph-based detection of coordinated buyer and merchant fraud rings. Every flag is explainable, bounded to a review action, and backed by an audit trail — nothing here auto-blocks a real account.</p>
  </div>
  <div class="kpi-row" id="kpiRow"></div>
</div>

<div class="main">
  <div class="queue">
    <div class="queue-head">
      <h2>Cluster queue</h2>
      <span id="queueCount"></span>
    </div>
    <div id="clusterList"></div>
  </div>
  <div class="detail" id="detailPanel">
    <div class="detail-empty">Select a cluster to view its risk breakdown and audit trail.</div>
  </div>
</div>

<footer>
  <span>RingFence · AI Risk Manager track</span>
  <span id="evalSummary" class="mono"></span>
</footer>

<script>
const DATA = __DATA_JSON__;
const clusters = DATA.detection.clusters.slice().sort((a,b) => b.risk_score - a.risk_score);
const auditByCluster = Object.fromEntries(DATA.audit.map(a => [a.cluster_id, a]));
const evalR = DATA.evaluation;

function fmtPct(x) { return (x*100).toFixed(1) + '%'; }

// ---- KPI row ----
const kpiRow = document.getElementById('kpiRow');
const kpis = [
  { label: 'Transactions scanned', value: DATA.detection.run_meta.total_transactions.toLocaleString(), sub: 'held-out test run' },
  { label: 'Clusters flagged', value: DATA.detection.run_meta.clusters_flagged, sub: `of ${DATA.detection.run_meta.total_clusters_found} candidate clusters`, cls: 'amber' },
  { label: 'Precision', value: fmtPct(evalR.transaction_level.precision), sub: `${evalR.transaction_level.false_positives} false positives`, cls: 'teal' },
  { label: 'Recall', value: fmtPct(evalR.transaction_level.recall), sub: `${evalR.ring_level.rings_caught}/${evalR.ring_level.true_rings_embedded} rings caught` },
  { label: 'Net value protected', value: '₹' + evalR.cost_analysis_inr.net_value_of_running_detector.toLocaleString('en-IN'), sub: 'vs. false-positive cost' },
];
kpiRow.innerHTML = kpis.map(k => `
  <div class="kpi">
    <div class="kpi-label">${k.label}</div>
    <div class="kpi-value ${k.cls||''}">${k.value}</div>
    <div class="kpi-sub">${k.sub}</div>
  </div>
`).join('');

// ---- Queue ----
document.getElementById('queueCount').textContent = clusters.length + ' clusters';
const listEl = document.getElementById('clusterList');
listEl.innerHTML = clusters.map(c => `
  <div class="cluster-item" data-id="${c.cluster_id}">
    <div class="cluster-item-top">
      <span class="cluster-id">${c.cluster_id}</span>
      <span class="risk-badge ${c.flagged ? 'flagged' : 'clear'}">${c.risk_score.toFixed(0)}</span>
    </div>
    <div class="cluster-item-meta">${c.n_merchants} merchants · ${c.n_buyers} buyers · ${c.n_transactions} txns</div>
  </div>
`).join('');

// ---- Detail panel ----
const detailPanel = document.getElementById('detailPanel');

function renderGraph(cluster) {
  const audit = auditByCluster[cluster.cluster_id];
  const merchants = audit.entities_involved.merchants;
  const buyers = audit.entities_involved.buyers;
  const nodes = [
    ...merchants.map(id => ({ id, kind: 'merchant' })),
    ...buyers.map(id => ({ id, kind: 'buyer' })),
  ];
  const W = 560, H = 220, cx = W/2, cy = H/2, R = 85;
  const n = Math.max(nodes.length, 1);
  const pos = {};
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI/2;
    pos[node.id] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
  });
  let edges = '';
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i+1; j < nodes.length; j++) {
      const a = pos[nodes[i].id], b = pos[nodes[j].id];
      edges += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#57B6D9" stroke-opacity="0.18" stroke-width="1.5"/>`;
    }
  }
  const dots = nodes.map(node => {
    const p = pos[node.id];
    const color = node.kind === 'merchant' ? '#E8A33D' : '#57B6D9';
    const label = node.id.split('_')[1].slice(0,4);
    return `<circle cx="${p.x}" cy="${p.y}" r="9" fill="${color}" fill-opacity="0.85"/>
            <text x="${p.x}" y="${p.y+22}" text-anchor="middle" font-family="IBM Plex Mono" font-size="9.5" fill="#7C8A96">${label}</text>`;
  }).join('');
  return `<svg width="${W}" height="${H+16}" viewBox="0 0 ${W} ${H+16}">${edges}${dots}</svg>`;
}

function selectCluster(id) {
  const cluster = clusters.find(c => c.cluster_id === id);
  const audit = auditByCluster[id];
  document.querySelectorAll('.cluster-item').forEach(el => el.classList.toggle('active', el.dataset.id === id));

  const signals = cluster.signals;
  const signalMeta = [
    { key: 'resource_reuse_score', label: 'Resource reuse' },
    { key: 'velocity_score', label: 'Velocity (burst)' },
    { key: 'structuring_score', label: 'Amount structuring' },
    { key: 'refund_score', label: 'Refund rate lift' },
  ];

  const evidenceHtml = (audit.evidence || []).slice(0, 8).map(e => {
    const [resPart, rest] = e.split(' shared by ');
    return `<div class="evidence-item"><span class="res">${resPart}</span> shared by ${rest}</div>`;
  }).join('') || '<div class="evidence-item">No direct shared-resource evidence recorded.</div>';

  detailPanel.innerHTML = `
    <div class="detail-top">
      <div>
        <div class="detail-title">${cluster.cluster_id}</div>
        <div class="detail-sub">${cluster.n_merchants} merchants · ${cluster.n_buyers} buyers · ${cluster.n_transactions} transactions · risk score ${cluster.risk_score.toFixed(1)}/100</div>
      </div>
      <div class="action-tag ${cluster.flagged ? 'review' : 'none'}">${cluster.action}</div>
    </div>

    <div class="signals">
      ${signalMeta.map(s => `
        <div class="signal-card">
          <div class="signal-label">${s.label}</div>
          <div class="signal-bar-bg"><div class="signal-bar" style="width:${Math.min(signals[s.key],100)}%"></div></div>
          <div class="signal-value">${signals[s.key].toFixed(0)}</div>
        </div>
      `).join('')}
    </div>

    <div class="section-label">Shared-resource graph</div>
    <div class="graph-wrap">${renderGraph(cluster)}</div>

    <div class="section-label">Audit evidence (why this cluster was ${cluster.flagged ? 'flagged' : 'not flagged'})</div>
    <div class="evidence-list">${evidenceHtml}</div>
  `;
}

listEl.addEventListener('click', (e) => {
  const item = e.target.closest('.cluster-item');
  if (item) selectCluster(item.dataset.id);
});

if (clusters.length) selectCluster(clusters[0].cluster_id);

// ---- Footer ----
document.getElementById('evalSummary').textContent =
  `precision ${fmtPct(evalR.transaction_level.precision)} · recall ${fmtPct(evalR.transaction_level.recall)} · f1 ${evalR.transaction_level.f1.toFixed(3)}`;
</script>
</body>
</html>
"""

HTML = HTML.replace("__DATA_JSON__", DATA_JSON)

with open(str(DASHBOARD_DIR / "index.html"), "w") as f:
    f.write(HTML)

DOCS_DIR = DASHBOARD_DIR.parent / "docs"
DOCS_DIR.mkdir(exist_ok=True)
with open(str(DOCS_DIR / "index.html"), "w") as f:
    f.write(HTML)
(DOCS_DIR / ".nojekyll").touch()

print(f"Dashboard written: {len(HTML):,} bytes")
print(f"Also synced to {DOCS_DIR / 'index.html'} for GitHub Pages")
