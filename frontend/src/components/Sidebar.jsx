import { useState } from 'react';

// Serendipity color interpolation for associative search
function getSerendipityColor(score, maxScore) {
  const t = Math.min(1, score / (maxScore || 1));
  const r = Math.round(58 + t * 152);
  const g = Math.round(166 - t * 100);
  const b = Math.round(255);
  return `rgb(${r},${g},${b})`;
}

// Check if string looks like an arXiv ID (e.g. "1706.03762", "arxiv:1706.03762", "2005.14165v2")
export function isArxivId(str) {
  if (!str) return false;
  const clean = str.trim().replace(/^arxiv:\s*/i, '');
  return /^\d{4}\.\d{4,5}(v\d+)?$/i.test(clean);
}

export function cleanArxivId(str) {
  if (!str) return '';
  return str.trim().replace(/^arxiv:\s*/i, '');
}

export default function Sidebar({
  onSearch,
  onSmartSearch,
  onCognitiveSearch,
  onOpenAlexSearch,
  onImportOpenAlex,
  onExplorePaper,
  onUploadPdf,
  searchResults = [],
  smartSearchResults = [],
  cognitiveResults = [],
  openAlexResults = [],
  recentPapers = [],
  onSelectRecent,
  readingList = [],
  onToggleBookmark,
  onUpdateReadingStatus,
  onUpdateReadingNotes,
  onRemoveFromReadingList,
  onClearReadingList,
  onExportReadingListBibtex,
  showToast
}) {
  const [activeTab, setActiveTab] = useState('search'); // 'search' | 'collection' | 'upload'
  const [searchMode, setSearchMode] = useState('catalog'); // 'catalog' | 'openalex' | 'smart' | 'associative'
  const [query, setQuery] = useState('');
  const [lastSubmittedQuery, setLastSubmittedQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [collectionFilter, setCollectionFilter] = useState('all'); // 'all' | 'unread' | 'reading' | 'completed'

  const isIdInput = isArxivId(query);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setLastSubmittedQuery(q);

    if (isIdInput) {
      onExplorePaper(cleanArxivId(q), `ArXiv ${cleanArxivId(q)}`);
      return;
    }

    if (searchMode === 'catalog') {
      onSearch(q);
    } else if (searchMode === 'openalex') {
      onOpenAlexSearch(q);
    } else if (searchMode === 'smart') {
      onSmartSearch(q);
    } else if (searchMode === 'associative') {
      onCognitiveSearch(q, 'balanced');
    }
  };

  const handleFallbackToCatalog = (targetQuery) => {
    setSearchMode('catalog');
    const q = targetQuery || query || lastSubmittedQuery;
    if (q) {
      onSearch(q);
    }
  };

  const filteredReadingList = readingList.filter(item => {
    if (collectionFilter === 'all') return true;
    return (item.status || 'unread') === collectionFilter;
  });

  return (
    <div className="sidebar-layout">
      {/* ── Tab Switcher: Cari Riset vs Koleksi Bacaan vs Unggah PDF ──────── */}
      <div className="sidebar-tabs">
        <button 
          className={`sidebar-tab ${activeTab === 'search' ? 'active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          Pencarian & Silsilah
        </button>
        <button 
          className={`sidebar-tab ${activeTab === 'collection' ? 'active' : ''}`}
          onClick={() => setActiveTab('collection')}
        >
          Koleksi
          {readingList.length > 0 && (
            <span className="tab-counter-badge">{readingList.length}</span>
          )}
        </button>
        <button 
          className={`sidebar-tab ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          Unggah Dokumen
        </button>
      </div>

      {/* ── TAB 1: PENCARIAN & SILSILAH ──────────────────────────────────── */}
      {activeTab === 'search' && (
        <>
          {/* Universal Search Bar */}
          <div className="sidebar-section">
            <div className="sidebar-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Pencarian Literatur</span>
              {isIdInput && <span className="id-detected-badge">ArXiv ID Terdeteksi</span>}
            </div>

            <form onSubmit={handleSubmit} className="form-group">
              <div className="universal-search-wrapper">
                <input 
                  className="input-field universal-search-input"
                  type="text" 
                  placeholder={
                    searchMode === 'associative' 
                      ? "Masukkan Paper ID untuk eksplorasi..."
                      : searchMode === 'openalex'
                        ? "Cari jutaan naskah global (OpenAlex)..."
                        : "Topik riset, judul, atau ArXiv ID (1706.03762)..."
                  }
                  value={query} 
                  onChange={(e) => setQuery(e.target.value)} 
                />
              </div>

              {/* Search Mode Pills */}
              <div className="search-mode-pills" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <button
                  type="button"
                  className={`mode-pill ${searchMode === 'catalog' ? 'active' : ''}`}
                  onClick={() => setSearchMode('catalog')}
                  title="Pencarian katalog ArXiv langsung"
                >
                  ArXiv
                </button>
                <button
                  type="button"
                  className={`mode-pill ${searchMode === 'openalex' ? 'active' : ''}`}
                  onClick={() => setSearchMode('openalex')}
                  title="Pencarian katalog global OpenAlex (250+ juta karya)"
                >
                  OpenAlex
                </button>
                <button
                  type="button"
                  className={`mode-pill ${searchMode === 'smart' ? 'active' : ''}`}
                  onClick={() => setSearchMode('smart')}
                  title="Pencarian semantik cerdas + graph ranking"
                >
                  Smart Graph
                </button>
                <button
                  type="button"
                  className={`mode-pill ${searchMode === 'associative' ? 'active' : ''}`}
                  onClick={() => setSearchMode('associative')}
                  title="Eksplorasi asosiatif ide tersembunyi"
                >
                  Asosiatif
                </button>
              </div>

              <button 
                type="submit" 
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '4px' }}
              >
                {isIdInput 
                  ? 'Buka Silsilah Graf' 
                  : searchMode === 'catalog' 
                    ? 'Cari Literatur' 
                    : searchMode === 'openalex'
                      ? 'Cari di OpenAlex Global'
                      : searchMode === 'smart' 
                        ? 'Temukan Paper Terkait' 
                        : 'Aktifkan Jalur Asosiatif'}
              </button>
            </form>
          </div>

          {/* Riwayat Eksplorasi Cepat */}
          {recentPapers && recentPapers.length > 0 && (
            <div className="sidebar-section recent-section">
              <div className="sidebar-title">Riwayat Penelusuran</div>
              <div className="recent-list">
                {recentPapers.slice(0, 5).map((p, idx) => (
                  <button 
                    key={idx} 
                    className="recent-chip"
                    onClick={() => onSelectRecent(p.id, p.title)}
                    title={p.title}
                  >
                    <span className="recent-bullet">&bull;</span>
                    <span className="recent-text">{p.title || p.id}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Hasil Pencarian: ArXiv Catalog */}
          {searchMode === 'catalog' && searchResults && searchResults.length > 0 && (
            <div className="sidebar-section results-container">
              <div className="sidebar-title">
                Hasil Pencarian ArXiv ({searchResults.length})
              </div>
              {searchResults.map(p => (
                <div key={p.arxiv_id} className="result-card simplified-card">
                  <div className="result-card-title">{p.title}</div>
                  <div className="result-card-meta">
                    <span className="meta-badge">{p.arxiv_id}</span>
                    <span>Tahun: {p.year || 'N/A'}</span>
                  </div>
                  {p.summary && (
                    <div className="result-snippet">
                      {p.summary.slice(0, 140)}…
                    </div>
                  )}
                  <button 
                    className="btn btn-primary btn-explore"
                    onClick={() => onExplorePaper(p.arxiv_id, p.title)}
                  >
                    Eksplorasi Silsilah
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Hasil Pencarian: OpenAlex Global Catalog */}
          {searchMode === 'openalex' && openAlexResults && openAlexResults.length > 0 && (
            <div className="sidebar-section results-container">
              <div className="sidebar-title">
                Hasil OpenAlex Global ({openAlexResults.length})
              </div>
              {openAlexResults.map((p, idx) => (
                <div key={idx} className="result-card simplified-card openalex-card">
                  <div className="result-card-title">{p.title}</div>
                  <div className="result-card-meta">
                    <span className="meta-badge">Tahun: {p.year || 'N/A'}</span>
                    <span className="openalex-citations-badge">{p.citation_count || 0} Sitasi Global</span>
                  </div>
                  {p.authors?.length > 0 && (
                    <div className="result-snippet" style={{ fontStyle: 'normal' }}>
                      Penulis: {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? ' et al.' : ''}
                    </div>
                  )}
                  {p.abstract && (
                    <div className="result-snippet">
                      {p.abstract.slice(0, 130)}…
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                    <button 
                      className="btn btn-primary btn-explore"
                      style={{ flex: 1 }}
                      onClick={() => onImportOpenAlex(p)}
                    >
                      Impor & Visualisasikan
                    </button>
                    {p.pdf_url && (
                      <a 
                        href={p.pdf_url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="btn btn-ghost btn-sm"
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 8px', textDecoration: 'none' }}
                        title="Unduh PDF Open Access"
                      >
                        PDF
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Hasil Pencarian: AI Smart Discovery (GraphRAG) */}
          {searchMode === 'smart' && (
            <>
              {smartSearchResults && smartSearchResults.length > 0 ? (
                <div className="sidebar-section results-container">
                  <div className="sidebar-title">
                    Rekomendasi AI Graph ({smartSearchResults.length})
                  </div>
                  {smartSearchResults.map(p => (
                    <div key={p.paper_id || p.arxiv_id} className="result-card simplified-card smart-card">
                      <div className="result-card-title">{p.title}</div>
                      <div className="result-card-meta">
                        <span className="meta-badge">arxiv:{p.arxiv_id || 'ID'}</span>
                        <span>Sitasi: {p.citation_count || 0}</span>
                      </div>
                      <div className="smart-badge-reason">
                        {p.hop_distance === 0 
                          ? 'Kesesuaian semantik langsung tingkat tinggi' 
                          : `Terhubung melalui ${p.hop_distance} jalur sitasi`}
                      </div>
                      <button 
                        className="btn btn-primary btn-explore"
                        onClick={() => onExplorePaper(p.arxiv_id || p.paper_id, p.title)}
                      >
                        Visualisasi Silsilah
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="sidebar-section">
                  <div className="search-fallback-banner">
                    <div className="fallback-title">Belum Tersimpan di Graf Lokal</div>
                    <div className="fallback-desc">
                      Makalah dengan kata kunci ini belum ada di basis data graf lokal.
                    </div>
                    <div className="fallback-hint-box">
                      <span>Cari langsung ke katalog global:</span>
                      <button 
                        className="link-btn-highlight"
                        onClick={() => handleFallbackToCatalog(query || lastSubmittedQuery)}
                      >
                        Beralih ke Pencarian ArXiv Global &rarr;
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Hasil Pencarian: Associative Search */}
          {searchMode === 'associative' && cognitiveResults && cognitiveResults.length > 0 && (
            <div className="sidebar-section results-container">
              <div className="sidebar-title">
                Koneksi Asosiatif ({cognitiveResults.length})
              </div>
              {cognitiveResults.map(p => (
                <div key={p.paper_id} className="result-card simplified-card associative-card">
                  <div className="result-card-title">{p.title}</div>
                  <div className="result-card-meta">
                    <span className="meta-badge" style={{ borderColor: getSerendipityColor(p.serendipity_score, 1) }}>
                      Energi: {(p.activation_energy || 0).toFixed(2)}
                    </span>
                    <span>Tahun: {p.year || 'N/A'}</span>
                  </div>
                  <div className="associative-badge-reason">
                    {p.serendipity_reason || `Terhubung via ${p.depth || 1} lompatan asosiatif`}
                  </div>
                  <button 
                    className="btn btn-primary btn-explore"
                    onClick={() => onExplorePaper(p.arxiv_id || p.paper_id, p.title)}
                  >
                    Eksplorasi Jalur Ini
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── TAB 2: DAFTAR KOLEKSI BACAAN ─────────────────────────────────── */}
      {activeTab === 'collection' && (
        <div className="collection-view">
          <div className="collection-header">
            <div className="sidebar-title" style={{ marginBottom: 0 }}>
              Daftar Bacaan ({readingList.length})
            </div>
            <div className="collection-actions">
              <button 
                className="btn btn-ghost btn-sm"
                onClick={onExportReadingListBibtex}
                disabled={readingList.length === 0}
                title="Ekspor seluruh naskah tersimpan ke file BibTeX"
              >
                BibTeX
              </button>
              {readingList.length > 0 && (
                <button 
                  className="btn btn-ghost btn-sm btn-danger"
                  onClick={onClearReadingList}
                  title="Kosongkan seluruh daftar bacaan"
                >
                  Kosongkan
                </button>
              )}
            </div>
          </div>

          {/* Status Filters */}
          <div className="collection-filter-pills">
            <button 
              className={`filter-pill ${collectionFilter === 'all' ? 'active' : ''}`}
              onClick={() => setCollectionFilter('all')}
            >
              Semua ({readingList.length})
            </button>
            <button 
              className={`filter-pill ${collectionFilter === 'unread' ? 'active' : ''}`}
              onClick={() => setCollectionFilter('unread')}
            >
              Belum ({readingList.filter(i => (i.status || 'unread') === 'unread').length})
            </button>
            <button 
              className={`filter-pill ${collectionFilter === 'reading' ? 'active' : ''}`}
              onClick={() => setCollectionFilter('reading')}
            >
              Dibaca ({readingList.filter(i => i.status === 'reading').length})
            </button>
            <button 
              className={`filter-pill ${collectionFilter === 'completed' ? 'active' : ''}`}
              onClick={() => setCollectionFilter('completed')}
            >
              Selesai ({readingList.filter(i => i.status === 'completed').length})
            </button>
          </div>

          {filteredReadingList.length > 0 ? (
            <div className="collection-list">
              {filteredReadingList.map((item) => {
                const targetId = item.arxiv_id || item.paper_id || item.id;
                return (
                  <div key={targetId} className="collection-card">
                    <div className="collection-card-top">
                      <span className={`status-badge status-${item.status || 'unread'}`}>
                        {item.status === 'completed' 
                          ? 'Selesai Dibaca' 
                          : item.status === 'reading' 
                            ? 'Sedang Dibaca' 
                            : 'Belum Dibaca'}
                      </span>
                      <span className="collection-year">{item.year || 'N/A'}</span>
                    </div>
                    <div className="collection-card-title">{item.title}</div>
                    
                    {/* Status Selector */}
                    <div className="collection-status-select-row">
                      <span className="status-label">Status Bacaan:</span>
                      <select 
                        className="status-select"
                        value={item.status || 'unread'}
                        onChange={(e) => onUpdateReadingStatus(targetId, e.target.value)}
                      >
                        <option value="unread">Belum Dibaca</option>
                        <option value="reading">Sedang Dibaca</option>
                        <option value="completed">Selesai Dibaca</option>
                      </select>
                    </div>

                    {/* Quick Notes Memo */}
                    <input 
                      type="text"
                      className="collection-notes-input"
                      placeholder="Catatan riset pribadi..."
                      value={item.notes || ''}
                      onChange={(e) => onUpdateReadingNotes(targetId, e.target.value)}
                    />

                    <div className="collection-card-actions">
                      <button 
                        className="btn btn-primary btn-sm"
                        style={{ flex: 1, fontSize: '11px' }}
                        onClick={() => onExplorePaper(targetId, item.title)}
                      >
                        Buka di Graf
                      </button>
                      <button 
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: '11px' }}
                        onClick={() => onSelectRecent(targetId, item.title)}
                      >
                        Detail
                      </button>
                      <button 
                        className="btn btn-ghost btn-sm btn-remove"
                        style={{ fontSize: '11px', color: '#ff7b72' }}
                        onClick={() => onRemoveFromReadingList(targetId)}
                        title="Hapus dari daftar bacaan"
                      >
                        Hapus
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="collection-empty">
              <div className="collection-empty-title">Koleksi Masih Kosong</div>
              <p className="collection-empty-desc">
                Buka metadata naskah apa pun dan klik tombol "Simpan ke Daftar Bacaan" untuk menandai artikel riset yang ingin dipelajari.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 3: UNGGAH DOKUMEN (PDF) ─────────────────────────────────── */}
      {activeTab === 'upload' && (
        <div className="sidebar-section">
          <div className="sidebar-title">Unggah Dokumen (PDF)</div>
          
          <div className="upload-guide-box" style={{ marginBottom: 16 }}>
            <div>
              Unggah file PDF jurnal atau pra-cetak untuk diekstraksi ke dalam graf.
              Model penalaran akan mengklasifikasikan kepribadian ilmiahnya secara otomatis.
            </div>
          </div>

          <div className="file-drop-area">
            <input 
              type="file" 
              accept=".pdf" 
              className="file-input"
              onChange={(e) => setSelectedFile(e.target.files[0])} 
            />
            <div className="file-label">
              {selectedFile ? (
                <span className="file-name">{selectedFile.name}</span>
              ) : (
                'Klik atau seret file PDF ke sini'
              )}
            </div>
          </div>

          <button 
            className="btn btn-primary" 
            style={{ width: '100%', marginTop: 16 }}
            disabled={!selectedFile}
            onClick={() => {
              if (selectedFile) {
                onUploadPdf(selectedFile);
                setSelectedFile(null);
              }
            }}
          >
            Ekstraksi & Analisis PDF
          </button>
        </div>
      )}
    </div>
  );
}
