import { useEffect, useState } from 'react';

// ── Personality definitions ──────────────────────────────────────────────────
const PERSONALITIES = {
  PIONEER: {
    code: 'PIONEER',
    label: 'The Pioneer',
    cls: 'pioneer',
    desc: 'Memperkenalkan paradigma atau metodologi baru yang fundamental.',
  },
  OPTIMIZER: {
    code: 'OPTIMIZER',
    label: 'The Optimizer',
    cls: 'optimizer',
    desc: 'Meningkatkan efisiensi, akurasi, atau performa dari metode yang ada.',
  },
  BRIDGE: {
    code: 'BRIDGE',
    label: 'The Bridge',
    cls: 'bridge',
    desc: 'Menghubungkan dua domain riset atau disiplin ilmu yang berbeda.',
  },
};

const ABSTRACT_PREVIEW_CHARS = 280;

function formatAuthors(authors, style = 'apa') {
  if (!authors || !authors.length) return 'Anonymous';
  if (style === 'apa') {
    if (authors.length === 1) return authors[0];
    if (authors.length === 2) return `${authors[0]} & ${authors[1]}`;
    return `${authors[0]} et al.`;
  }
  if (style === 'ieee') {
    if (authors.length === 1) return authors[0];
    return `${authors[0]} et al.`;
  }
  return authors.join(' and ');
}

export default function DetailPanel({ 
  node, 
  onClose, 
  onExpand, 
  onExpandNode, 
  onAnalyzed,
  showToast,
  onSelectPaper,
  readingList = [],
  onToggleBookmark,
  onUpdateReadingStatus
}) {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'ai' | 'citations' | 'relations'
  const [details, setDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState(null);
  const [abstractOpen, setAbstractOpen] = useState(false);
  const [citeFormat, setCiteFormat] = useState('apa'); // 'apa' | 'ieee' | 'bibtex'
  const [copiedCitation, setCopiedCitation] = useState(false);

  // External citation metrics from OpenAlex and Semantic Scholar
  const [externalMetrics, setExternalMetrics] = useState(null);
  const [loadingExtMetrics, setLoadingExtMetrics] = useState(false);

  const paperId = node?.paper_id || node?.id || node?.arxiv_id;

  useEffect(() => {
    setDetails(null);
    setAnalyzeError(null);
    setAbstractOpen(false);
    setCopiedCitation(false);
    setExternalMetrics(null);
    if (!paperId) return;

    const controller = new AbortController();
    setLoadingDetails(true);
    fetch(`/api/graph/paper/${encodeURIComponent(paperId)}/details`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setDetails(data))
      .catch((err) => {
        if (err.name !== 'AbortError') console.error('Failed to load paper details', err);
      })
      .finally(() => setLoadingDetails(false));

    // Fetch external metrics from OpenAlex & Semantic Scholar
    const lookupId = node?.arxiv_id || paperId;
    if (lookupId && !lookupId.startsWith('openalex:')) {
      setLoadingExtMetrics(true);
      fetch(`/api/scholar/paper/${encodeURIComponent(lookupId)}/external-metrics`, { signal: controller.signal })
        .then((res) => (res.ok ? res.json() : null))
        .then((ext) => ext && setExternalMetrics(ext))
        .catch(() => {})
        .finally(() => setLoadingExtMetrics(false));
    }

    return () => controller.abort();
  }, [paperId]);

  if (!node) return null;

  const paper = { ...node, ...(details || {}) };
  const tag = paper.personality_tag?.toUpperCase();
  const persona = tag ? PERSONALITIES[tag] : null;
  const confidencePct = Math.round((Number(paper.confidence_score) || 0) * 100);
  const metrics = details?.metrics;
  const abstract = paper.abstract || '';
  const abstractIsLong = abstract.length > ABSTRACT_PREVIEW_CHARS;

  const citingPapers = paper.citing_papers || [];
  const citedReferences = paper.cited_references || [];
  const totalRelations = citingPapers.length + citedReferences.length;

  const normId = (v) => String(v || '').trim().toLowerCase().replace(/^arxiv:\s*/i, '');
  const bookmarkedItem = readingList?.find((i) => {
    const itemIds = [i.paper_id, i.id, i.arxiv_id].filter(Boolean).map(normId);
    const targetIds = [paperId, paper.paper_id, paper.id, paper.arxiv_id].filter(Boolean).map(normId);
    return itemIds.some((id) => id && targetIds.includes(id));
  });
  const isBookmarked = Boolean(bookmarkedItem);

  const getCitationText = () => {
    const title = paper.title || 'Untitled';
    const year = paper.year || new Date().getFullYear();
    const id = paper.arxiv_id || paper.paper_id || 'unknown';
    const authors = paper.authors || [];

    if (citeFormat === 'apa') {
      return `${formatAuthors(authors, 'apa')} (${year}). ${title}. arXiv:${id}.`;
    }
    if (citeFormat === 'ieee') {
      return `${formatAuthors(authors, 'ieee')}, "${title}," arXiv preprint arXiv:${id}, ${year}.`;
    }
    if (citeFormat === 'bibtex') {
      const citeKey = (authors[0]?.split(' ').pop() || 'paper').toLowerCase() + year + (id.split('.')[0] || '');
      return `@article{${citeKey},
  title={${title}},
  author={${formatAuthors(authors, 'bibtex')}},
  journal={arXiv preprint arXiv:${id}},
  year={${year}}
}`;
    }
    return '';
  };

  const handleCopyCitation = () => {
    const text = getCitationText();
    navigator.clipboard.writeText(text).then(() => {
      setCopiedCitation(true);
      if (showToast) {
        showToast(`Sitasi format ${citeFormat.toUpperCase()} disalin ke papan klip.`, 'success');
      }
      setTimeout(() => setCopiedCitation(false), 2000);
    });
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await fetch(`/api/graph/paper/${encodeURIComponent(paperId)}/analyze`, {
        method: 'POST',
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Analysis failed (HTTP ${res.status})`);
      setDetails(data);
      onAnalyzed?.(data);
    } catch (err) {
      setAnalyzeError(err.message);
      if (showToast) {
        showToast(`Analisis gagal: ${err.message}`, 'error');
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const handleExpandBranch = () => {
    const targetId = paper.arxiv_id || paper.paper_id;
    if (onExpandNode && targetId) {
      if (showToast) {
        showToast(`Memperluas cabang referensi untuk ${paper.title || targetId}...`, 'info');
      }
      onExpandNode(targetId);
    }
  };

  const renderPersonalityBadge = (pTag) => {
    const normalizedTag = (pTag || '').toUpperCase();
    if (normalizedTag === 'PIONEER') {
      return <span className="relation-tag relation-pioneer">PIONEER</span>;
    }
    if (normalizedTag === 'OPTIMIZER') {
      return <span className="relation-tag relation-optimizer">OPTIMIZER</span>;
    }
    if (normalizedTag === 'BRIDGE') {
      return <span className="relation-tag relation-bridge">BRIDGE</span>;
    }
    return <span className="relation-tag relation-untagged">UNTAGGED</span>;
  };

  return (
    <div className={`detail-panel ${node ? 'open' : ''}`}>
      <div className="detail-header">
        <h3>Metadata Dokumen Ilmiah</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button 
            className={`btn-bookmark ${isBookmarked ? 'active' : ''}`}
            onClick={() => onToggleBookmark?.(paper)}
            title={isBookmarked ? 'Hapus dari Daftar Bacaan' : 'Simpan ke Daftar Bacaan'}
          >
            {isBookmarked ? 'Tersimpan di Koleksi' : '+ Simpan ke Koleksi'}
          </button>
          <button className="close-btn" onClick={onClose} title="Tutup Panel">&times;</button>
        </div>
      </div>

      {/* ── Status Bacaan bila sudah disimpan ──────────────────────────────── */}
      {isBookmarked && (
        <div className="detail-reading-status-bar">
          <span className="reading-status-label">Status Bacaan:</span>
          <select 
            className="detail-status-select"
            value={bookmarkedItem?.status || 'unread'}
            onChange={(e) => onUpdateReadingStatus?.(paperId, e.target.value)}
          >
            <option value="unread">Belum Dibaca</option>
            <option value="reading">Sedang Dibaca</option>
            <option value="completed">Selesai Dibaca</option>
          </select>
        </div>
      )}

      {/* ── Tab Bar Navigation ────────────────────────────────────────────── */}
      <div className="detail-tabs">
        <button 
          className={`detail-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Ringkasan
        </button>
        <button 
          className={`detail-tab ${activeTab === 'ai' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai')}
        >
          Analisis AI
        </button>
        <button 
          className={`detail-tab ${activeTab === 'citations' ? 'active' : ''}`}
          onClick={() => setActiveTab('citations')}
        >
          Sitasi & Silsilah
        </button>
        <button 
          className={`detail-tab ${activeTab === 'relations' ? 'active' : ''}`}
          onClick={() => setActiveTab('relations')}
        >
          Relasi Graf
          {totalRelations > 0 && <span className="detail-tab-badge">{totalRelations}</span>}
        </button>
      </div>

      <div className="detail-body">
        <h2 className="detail-title">{paper.title || 'Unknown Title'}</h2>
        <div className="detail-subtitle">
          {paper.year || 'N/A'}
          {paper.venue ? ` · ${paper.venue}` : ''}
          {paper.arxiv_id ? (
            <>
              {' · '}
              <a href={`https://arxiv.org/abs/${paper.arxiv_id}`} target="_blank" rel="noopener noreferrer">
                arXiv:{paper.arxiv_id}
              </a>
            </>
          ) : null}
        </div>

        {/* ── TAB 1: RINGKASAN (OVERVIEW) ─────────────────────────────────── */}
        {activeTab === 'overview' && (
          <>
            <section className="intel-card">
              <div className="intel-card-title">Ringkasan Eksekutif (TL;DR)</div>

              {paper.problem_statement || paper.key_contribution ? (
                <div className="tldr-grid">
                  {paper.problem_statement && (
                    <div>
                      <div className="intel-label">Masalah Utama (Problem Statement)</div>
                      <p>{paper.problem_statement}</p>
                    </div>
                  )}
                  {paper.key_contribution && (
                    <div>
                      <div className="intel-label">Kontribusi Kunci (Key Contribution)</div>
                      <p>{paper.key_contribution}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="muted">
                  {persona
                    ? 'Ringkasan belum tersedia. Klik Analisis Ulang di tab Analisis AI.'
                    : 'Ringkasan problem & kontribusi akan diekstrak secara otomatis saat analisis dijalankan.'}
                </p>
              )}

              <div className="intel-label" style={{ marginTop: 14 }}>Abstrak Lengkap</div>
              {loadingDetails && !details ? (
                <div className="skeleton" />
              ) : abstract ? (
                <>
                  <p className={`abstract ${abstractOpen ? 'open' : ''}`}>
                    {abstractOpen || !abstractIsLong ? abstract : `${abstract.slice(0, ABSTRACT_PREVIEW_CHARS)}…`}
                  </p>
                  {abstractIsLong && (
                    <button className="link-btn" onClick={() => setAbstractOpen((v) => !v)}>
                      {abstractOpen ? 'Tampilkan lebih sedikit [-]' : 'Baca selengkapnya [+]'}
                    </button>
                  )}
                </>
              ) : (
                <p className="muted">
                  Abstrak belum tersimpan. Akan diambil secara otomatis saat analisis.
                </p>
              )}
            </section>

            <div className="detail-section">
              <div className="detail-label">Penulis (Authors)</div>
              <div className="detail-value">
                {paper.authors?.length ? paper.authors.join(', ') : 'N/A'}
              </div>
            </div>

            {paper.topics?.length > 0 && (
              <div className="detail-section">
                <div className="detail-label">Kategori / Topik</div>
                <div className="topic-pills">
                  {paper.topics.map((t) => (
                    <span key={t} className="topic-pill">{t}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── TAB 2: ANALISIS AI (GEMINI REASONING) ────────────────────────── */}
        {activeTab === 'ai' && (
          <section className={`intel-card persona-card ${persona ? `persona-${persona.cls}` : 'persona-untagged'}`}>
            <div className="intel-card-title">Klasifikasi Peran Ilmiah (Personality)</div>

            {persona ? (
              <>
                <div className="persona-head">
                  <span className="persona-code-badge">{persona.code}</span>
                  <div>
                    <div className="persona-label">{persona.label}</div>
                    <div className="persona-desc">{persona.desc}</div>
                  </div>
                </div>

                <div className="confidence-row">
                  <span>Tingkat Keyakinan (Confidence)</span>
                  <span className="confidence-value">{confidencePct}%</span>
                </div>
                <div className="confidence-track">
                  <div className="confidence-fill" style={{ width: `${confidencePct}%` }} />
                </div>

                {paper.reasoning && (
                  <div className="justification">
                    <div className="intel-label">Justifikasi Ilmiah Gemini Reasoning</div>
                    <p>{paper.reasoning}</p>
                  </div>
                )}

                {paper.evidence_quotes?.length > 0 && (
                  <div className="evidence">
                    <div className="intel-label">Kutipan Bukti dari Naskah</div>
                    {paper.evidence_quotes.map((q, i) => (
                      <blockquote key={i}>"{q}"</blockquote>
                    ))}
                  </div>
                )}

                <button className="btn btn-ghost btn-sm" onClick={handleAnalyze} disabled={analyzing} style={{ marginTop: 10 }}>
                  {analyzing ? 'Sedang menganalisis ulang…' : 'Analisis Ulang (Gemini)'}
                </button>
              </>
            ) : (
              <>
                <div className="persona-head">
                  <span className="persona-code-badge">UNTAGGED</span>
                  <div>
                    <div className="persona-label">Belum Diklasifikasi</div>
                    <div className="persona-desc">
                      Jalankan analisis Gemini Reasoning untuk mengevaluasi peran metodologis paper dalam silsilah riset.
                    </div>
                  </div>
                </div>
                <button className="btn btn-analyze" onClick={handleAnalyze} disabled={analyzing}>
                  {analyzing ? (
                    <>
                      <span className="spinner" /> Sedang menganalisis…
                    </>
                  ) : (
                    'Analisis Peran Riset (Gemini Reasoning)'
                  )}
                </button>
                {analyzing && (
                  <div className="hint">Model reasoning sedang mengevaluasi kontribusi metodologis...</div>
                )}
              </>
            )}

            {analyzeError && <div className="error-box">Kesalahan: {analyzeError}</div>}
          </section>
        )}

        {/* ── TAB 3: SITASI & METRIK SILSILAH ──────────────────────────────── */}
        {activeTab === 'citations' && (
          <>
            <section className="intel-card citation-card">
              <div className="intel-card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Format Sitasi Standar</span>
                <div className="cite-format-pills">
                  <button 
                    className={`cite-pill ${citeFormat === 'apa' ? 'active' : ''}`}
                    onClick={() => setCiteFormat('apa')}
                  >
                    APA
                  </button>
                  <button 
                    className={`cite-pill ${citeFormat === 'ieee' ? 'active' : ''}`}
                    onClick={() => setCiteFormat('ieee')}
                  >
                    IEEE
                  </button>
                  <button 
                    className={`cite-pill ${citeFormat === 'bibtex' ? 'active' : ''}`}
                    onClick={() => setCiteFormat('bibtex')}
                  >
                    BibTeX
                  </button>
                </div>
              </div>
              <div className="citation-preview-box">
                <code>{getCitationText()}</code>
              </div>
              <button 
                className={`btn btn-copy-citation ${copiedCitation ? 'copied' : ''}`}
                onClick={handleCopyCitation}
              >
                {copiedCitation ? 'Tersalin ke Clipboard' : 'Salin Format Sitasi'}
              </button>
            </section>

            {/* Metrik Sitasi Global & Akses Terbuka (OpenAlex & Semantic Scholar) */}
            <section className="intel-card external-metrics-card">
              <div className="intel-card-title">Metrik Sitasi Global (OpenAlex & Semantic Scholar)</div>
              {loadingExtMetrics ? (
                <div className="skeleton" />
              ) : externalMetrics ? (
                <div className="external-metrics-content">
                  <div className="metric-grid">
                    <div className="metric">
                      <div className="metric-value">
                        {externalMetrics.openalex?.global_citation_count != null 
                          ? Number(externalMetrics.openalex.global_citation_count).toLocaleString('id-ID')
                          : 'N/A'}
                      </div>
                      <div className="metric-label">Sitasi Global (OpenAlex)</div>
                    </div>
                    <div className="metric">
                      <div className="metric-value">
                        {externalMetrics.semantic_scholar?.citations_found ?? 'N/A'}
                      </div>
                      <div className="metric-label">Koneksi S2 Scholar</div>
                    </div>
                  </div>

                  <div className="external-links-row" style={{ marginTop: '10px', display: 'flex', gap: '8px' }}>
                    {externalMetrics.openalex?.doi && (
                      <a 
                        href={`https://doi.org/${externalMetrics.openalex.doi.replace('https://doi.org/', '')}`} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="btn btn-ghost btn-sm"
                        style={{ flex: 1, textAlign: 'center', textDecoration: 'none', fontSize: '11px' }}
                      >
                        DOI Penerbit
                      </a>
                    )}
                    {externalMetrics.openalex?.pdf_url && (
                      <a 
                        href={externalMetrics.openalex.pdf_url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="btn btn-primary btn-sm"
                        style={{ flex: 1, textAlign: 'center', textDecoration: 'none', fontSize: '11px' }}
                      >
                        PDF Open Access
                      </a>
                    )}
                  </div>
                </div>
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  Data sitasi global OpenAlex tidak ditemukan untuk naskah ini.
                </p>
              )}
            </section>

            <section className="intel-card">
              <div className="intel-card-title">Metrik Silsilah Graf</div>
              {metrics ? (
                <>
                  <div className="metric-grid">
                    <div className="metric">
                      <div className="metric-value">{metrics.in_graph_citations}</div>
                      <div className="metric-label">In-Graph Citations</div>
                    </div>
                    <div className="metric">
                      <div className="metric-value">{metrics.references_count}</div>
                      <div className="metric-label">Mapped References</div>
                    </div>
                  </div>
                  <div className={`role-pill role-${metrics.lineage_role_key}`}>
                    <div>
                      <div className="role-name">{metrics.lineage_role}</div>
                      <div className="role-desc">{metrics.lineage_role_desc}</div>
                    </div>
                  </div>

                  {metrics.references_count > 0 && (
                    <button 
                      className="btn btn-ghost btn-sm"
                      style={{ width: '100%', marginTop: '10px', fontSize: '11px' }}
                      onClick={handleExpandBranch}
                      title="Tampilkan cabang referensi paper ini ke dalam graf"
                    >
                      Perluas Cabang Referensi ke Graf
                    </button>
                  )}
                </>
              ) : loadingDetails ? (
                <div className="skeleton" />
              ) : (
                <p className="muted">Metrik silsilah sedang dimuat...</p>
              )}
            </section>
          </>
        )}

        {/* ── TAB 4: RELASI GRAF (DIKUTIP & MENGUTIP) ──────────────────────── */}
        {activeTab === 'relations' && (
          <div className="relations-tab-content">
            {/* Section: Dikutip Oleh */}
            <div className="relation-group">
              <div className="relation-group-header">
                <span className="relation-group-title">Dikutip Oleh di Graf</span>
                <span className="relation-count-badge">{citingPapers.length} paper</span>
              </div>
              <p className="relation-group-desc">
                Paper di dalam basis data graf yang mencantumkan naskah ini sebagai rujukan:
              </p>

              {citingPapers.length > 0 ? (
                <div className="relation-list">
                  {citingPapers.map((cp) => (
                    <div 
                      key={cp.paper_id || cp.arxiv_id} 
                      className="relation-card"
                      onClick={() => onSelectPaper?.(cp)}
                      title="Klik untuk memilih dan melihat detail dokumen ini"
                    >
                      <div className="relation-card-top">
                        {renderPersonalityBadge(cp.personality_tag)}
                        <span className="relation-year">{cp.year || 'N/A'}</span>
                      </div>
                      <div className="relation-card-title">{cp.title || 'Untitled'}</div>
                      <div className="relation-card-meta">
                        {cp.arxiv_id ? `arXiv:${cp.arxiv_id}` : cp.paper_id}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="relation-empty">
                  Belum ada dokumen di dalam graf yang mencatat sitasi terhadap naskah ini.
                </div>
              )}
            </div>

            {/* Section: Mengutip (Daftar Referensi) */}
            <div className="relation-group" style={{ marginTop: 18 }}>
              <div className="relation-group-header">
                <span className="relation-group-title">Mengutip (Referensi Terpetakan)</span>
                <span className="relation-count-badge">{citedReferences.length} referensi</span>
              </div>
              <p className="relation-group-desc">
                Dokumen rujukan yang mendasari metodologi naskah ini:
              </p>

              {citedReferences.length > 0 && (
                <button 
                  className="btn btn-ghost btn-sm"
                  style={{ width: '100%', marginBottom: 10, fontSize: '11px' }}
                  onClick={handleExpandBranch}
                  title="Tambahkan seluruh simpul referensi ini ke kanvas graf"
                >
                  Perluas Semua Referensi ke Graf
                </button>
              )}

              {citedReferences.length > 0 ? (
                <div className="relation-list">
                  {citedReferences.map((ref) => (
                    <div 
                      key={ref.paper_id || ref.arxiv_id} 
                      className="relation-card"
                      onClick={() => onSelectPaper?.(ref)}
                      title="Klik untuk memilih dan melihat detail dokumen ini"
                    >
                      <div className="relation-card-top">
                        {renderPersonalityBadge(ref.personality_tag)}
                        <span className="relation-year">{ref.year || 'N/A'}</span>
                      </div>
                      <div className="relation-card-title">{ref.title || 'Untitled'}</div>
                      <div className="relation-card-meta">
                        {ref.arxiv_id ? `arXiv:${ref.arxiv_id}` : ref.paper_id}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="relation-empty">
                  Belum ada referensi yang terhubung di graf. Klik "Jelajahi Silsilah Dokumen" untuk mengekstraksi pohon sitasinya.
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="detail-footer">
        {paper.arxiv_id ? (
          <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => onExpand(paper.arxiv_id)}>
            Jelajahi Silsilah Dokumen
          </button>
        ) : (
          <div style={{ color: 'var(--text-secondary)', fontSize: '12px', textAlign: 'center' }}>
            ID tidak tersedia untuk ekspansi.
          </div>
        )}
      </div>
    </div>
  );
}
