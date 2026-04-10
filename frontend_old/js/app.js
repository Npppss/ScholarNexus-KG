// frontend/js/app.js
import { KGGraph }     from './graph.js';
import { initUpload }  from './upload.js';
import { getGraphStats, getSimilar } from './api.js';

// ── State ─────────────────────────────────────────────────────────────────
let graph         = null;
let selectedPaper = null;

// ── Bootstrap ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  graph = new KGGraph(
    document.getElementById('kg-graph'),
    onNodeSelected
  );

  initUpload(
    document.getElementById('upload-zone'),
    onUploadSuccess,
    onUploadError
  );

  // Filter pills
  document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      graph.setFilter(pill.dataset.tag);
    });
  });

  // Search
  document.getElementById('search-input').addEventListener('input', e => {
    graph.search(e.target.value);
  });

  // Lineage direction toggle
  document.querySelectorAll('.direction-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!selectedPaper?.arxiv_id) return;
      document.querySelectorAll('.direction-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      graph.clear();
      graph.loadLineage(selectedPaper.arxiv_id, btn.dataset.dir, 3);
    });
  });

  // Load initial stats
  updateStatsBar();
});

// ── Callbacks ─────────────────────────────────────────────────────────────
function onNodeSelected(paper) {
  selectedPaper = paper;
  updateDetailPanel(paper);
}

async function onUploadSuccess(result) {
  showToast(`"${result.title}" berhasil diproses — ${result.personality_tag}`, 'success');
  graph.clear();
  await graph.loadLineage(result.arxiv_id || result.paper_id, 'ancestors', 3);
  updateStatsBar();
}

function onUploadError(msg) {
  showToast(msg, 'error');
}

// ── Detail Panel ──────────────────────────────────────────────────────────
function updateDetailPanel(paper) {
  const panel = document.getElementById('detail-panel');
  if (!paper) {
    panel.innerHTML = '<p class="empty-hint">Klik node untuk melihat detail</p>';
    return;
  }

  const tag      = paper.personality_tag || 'STUB';
  const tagClass = { PIONEER:'badge-pioneer', OPTIMIZER:'badge-optimizer', BRIDGE:'badge-bridge', STUB:'badge-stub' };

  panel.innerHTML = `
    <div class="detail-header">
      <span class="badge ${tagClass[tag]}">${tag}</span>
      <p class="paper-title">${paper.title}</p>
    </div>

    <div class="detail-meta">
      <div class="meta-row"><span>Year</span><strong>${paper.year || '—'}</strong></div>
      <div class="meta-row"><span>Category</span><strong>${paper.primary_category || '—'}</strong></div>
      <div class="meta-row"><span>ArXiv</span>
        <a href="https://arxiv.org/abs/${paper.arxiv_id}" target="_blank">${paper.arxiv_id || '—'}</a>
      </div>
      ${paper.confidence_score
        ? `<div class="meta-row"><span>Confidence</span>
           <strong>${Math.round(paper.confidence_score * 100)}%</strong></div>`
        : ''}
    </div>

    ${paper.reasoning ? `
      <div class="detail-section">LLM reasoning</div>
      <p class="reasoning-text">${paper.reasoning}</p>
    ` : ''}

    <div class="detail-actions">
      <button onclick="expandLineage('${paper.arxiv_id}')">
        Expand lineage ↗
      </button>
      <button onclick="loadSimilar('${paper.paper_id}')">
        Temukan paper mirip ↗
      </button>
    </div>
  `;
}

// ── Global action handlers (dipanggil dari HTML) ──────────────────────────
window.expandLineage = async (arxivId) => {
  if (!arxivId) return;
  showToast('Mengekspansi lineage…', 'info');
  await graph.loadLineage(arxivId, 'ancestors', 2);
  updateStatsBar();
};

window.loadSimilar = async (paperId) => {
  showToast('Mencari paper serupa…', 'info');
  const result = await getSimilar(paperId, 8, 0.78);
  // Inject similarity edges ke graph
  graph._ingestData(
    result.similar.map(p => ({ ...p, paper_id: p.paper_id })),
    result.similar.map(p => ({ source: paperId, target: p.paper_id, type: 'SIMILAR_TO' }))
  );
};

// ── Status Bar ────────────────────────────────────────────────────────────
async function updateStatsBar() {
  try {
    const stats = await getGraphStats();
    document.getElementById('stat-papers').textContent   = stats.graph.total_papers;
    document.getElementById('stat-tagged').textContent   = stats.graph.tagged_papers;
    document.getElementById('stat-citations').textContent = stats.graph.total_citations;
    document.getElementById('stat-similar').textContent  = stats.graph.similarity_edges;
  } catch (_) {}
}

// ── Toast ─────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add('visible'), 10);
  setTimeout(() => { toast.classList.remove('visible'); setTimeout(() => toast.remove(), 300); }, 3000);
}