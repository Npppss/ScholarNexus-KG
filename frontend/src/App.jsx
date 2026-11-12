import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import TopBar from './components/TopBar';
import Sidebar from './components/Sidebar';
import GraphView from './components/GraphView';
import DetailPanel from './components/DetailPanel';
import TimelineSlider from './components/TimelineSlider';

const RECENT_STORAGE_KEY = 'scholarnexus_recent_papers';
const READING_LIST_STORAGE_KEY = 'scholarnexus_reading_list';

function isArxivId(str) {
  const clean = String(str || '').trim().replace(/^arxiv:\s*/i, '');
  return /^\d{4}\.\d{4,5}(v\d+)?$/i.test(clean);
}

function normalizePaperId(val) {
  return String(val || '')
    .trim()
    .toLowerCase()
    .replace(/^arxiv:\s*/i, '');
}

function isSamePaper(item, target) {
  if (!item || !target) return false;
  const targetCandidates =
    typeof target === 'object'
      ? [target.paper_id, target.id, target.arxiv_id].filter(Boolean)
      : [target];

  const itemCandidates = [item.paper_id, item.id, item.arxiv_id].filter(Boolean);

  for (const t of targetCandidates) {
    const normT = normalizePaperId(t);
    for (const c of itemCandidates) {
      if (c === t || (normT && normalizePaperId(c) === normT)) {
        return true;
      }
    }
  }
  return false;
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [smartSearchResults, setSmartSearchResults] = useState([]);
  const [cognitiveResults, setCognitiveResults] = useState([]);
  const [openAlexResults, setOpenAlexResults] = useState([]);
  const [rawGraphData, setRawGraphData] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('Memproses...');
  const [toasts, setToasts] = useState([]);

  // Sprint 4: Kontrol keterbacaan graf, batas simpul, filter sitasi, label adaptif, & klasifikasi otomatis
  const [layoutMode, setLayoutMode] = useState('physics'); // 'physics' | 'chronological'
  const [labelMode, setLabelMode] = useState('adaptive'); // 'adaptive' | 'core' | 'all'
  const [maxNodesLimit, setMaxNodesLimit] = useState(35); // 25 | 35 | 50 | 0 (Semua)
  const [minCitationsFilter, setMinCitationsFilter] = useState(0); // 0 | 1 | 2 | 5
  const [autoClassify, setAutoClassify] = useState(true);
  const [batchAnalyzing, setBatchAnalyzing] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  const attemptedAutoIdsRef = useRef(new Set());
  const exportMenuRef = useRef(null);

  const [timelineYear, setTimelineYear] = useState(new Date().getFullYear());

  // Non-blocking Toast notification system
  const showToast = useCallback((message, type = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Tutup dropdown ekspor saat klik di luar
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target)) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Persisted recently viewed papers
  const [recentPapers, setRecentPapers] = useState(() => {
    try {
      const saved = localStorage.getItem(RECENT_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Persisted reading list (koleksi bacaan pribadi)
  const [readingList, setReadingList] = useState(() => {
    try {
      const saved = localStorage.getItem(READING_LIST_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(READING_LIST_STORAGE_KEY, JSON.stringify(readingList));
    } catch (e) {
      console.error('Failed to persist reading list:', e);
    }
  }, [readingList]);

  const handleToggleBookmark = useCallback(
    (paper) => {
      const id = paper.paper_id || paper.id || paper.arxiv_id;
      if (!id) return;
      setReadingList((prev) => {
        const exists = prev.some((item) => isSamePaper(item, paper));
        if (exists) {
          showToast('Dokumen dihapus dari Daftar Bacaan.', 'info');
          return prev.filter((item) => !isSamePaper(item, paper));
        } else {
          const cleanArxiv = paper.arxiv_id || (isArxivId(id) ? String(id).replace(/^arxiv:\s*/i, '') : null);
          const newItem = {
            paper_id: paper.paper_id || id,
            arxiv_id: cleanArxiv,
            title: paper.title || 'Untitled Paper',
            year: paper.year,
            authors: paper.authors || [],
            personality_tag: paper.personality_tag,
            status: 'unread',
            notes: '',
            added_at: new Date().toISOString(),
          };
          showToast('Dokumen disimpan ke Daftar Bacaan.', 'success');
          return [newItem, ...prev];
        }
      });
    },
    [showToast]
  );

  const handleUpdateReadingStatus = useCallback((paperId, newStatus) => {
    setReadingList((prev) =>
      prev.map((item) => (isSamePaper(item, paperId) ? { ...item, status: newStatus } : item))
    );
  }, []);

  const handleUpdateReadingNotes = useCallback((paperId, notes) => {
    setReadingList((prev) =>
      prev.map((item) => (isSamePaper(item, paperId) ? { ...item, notes } : item))
    );
  }, []);

  const handleRemoveFromReadingList = useCallback(
    (paperId) => {
      setReadingList((prev) => prev.filter((item) => !isSamePaper(item, paperId)));
      showToast('Dokumen dihapus dari daftar koleksi.', 'info');
    },
    [showToast]
  );

  const handleClearReadingList = useCallback(() => {
    setReadingList([]);
    showToast('Seluruh daftar koleksi bacaan telah dikosongkan.', 'info');
  }, [showToast]);

  const handleExportReadingListBibtex = useCallback(() => {
    if (readingList.length === 0) return;
    const entries = readingList.map((item) => {
      const id = item.arxiv_id || item.paper_id || 'ref';
      const cleanKey = String(id).replace(/[^a-zA-Z0-9]/g, '');
      const authors = item.authors && item.authors.length > 0 ? item.authors.join(' and ') : 'Anonymous';
      return `@article{${cleanKey},
  title={${item.title || 'Untitled'}},
  author={${authors}},
  year={${item.year || new Date().getFullYear()}},
  note={Status: ${item.status || 'unread'}${item.notes ? ` - Catatan: ${item.notes}` : ''}}
}`;
    });
    const blob = new Blob([entries.join('\n\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `koleksi-bacaan-${new Date().toISOString().slice(0, 10)}.bib`;
    a.click();
    showToast(`Berhasil mengekspor ${readingList.length} naskah ke format BibTeX.`, 'success');
  }, [readingList, showToast]);

  const addRecentPaper = useCallback((id, title) => {
    if (!id) return;
    const cleanId = id.trim().replace(/^arxiv:\s*/i, '');
    setRecentPapers((prev) => {
      const filtered = prev.filter((p) => p.id !== cleanId);
      const isRawIdTitle =
        !title || title === cleanId || title.startsWith('ArXiv') || /^\d{4}\.\d{4,5}/.test(title);
      const displayTitle = isRawIdTitle ? `Paper ${cleanId}` : title;
      const updated = [{ id: cleanId, title: displayTitle }, ...filtered].slice(0, 8);
      try {
        localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(updated));
      } catch (e) {
        console.error(e);
      }
      return updated;
    });
  }, []);

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      setHealth(data);
    } catch {
      setHealth({ status: 'offline' });
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/graph/stats');
      const data = await res.json();
      setStats(data?.graph || null);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchHealth();
    fetchStats();

    const urlParams = new URLSearchParams(window.location.search);
    const vizId = urlParams.get('viz_id');
    if (vizId) {
      handleVisualize(vizId);
    }

    const interval = setInterval(() => {
      fetchHealth();
      fetchStats();
    }, 20000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 1. ArXiv Global Search
  const handleSearch = async (query) => {
    if (!query) return;
    setLoading(true);
    setLoadingText('Mencari di katalog ArXiv...');
    try {
      const res = await fetch('/api/arxiv/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, max_results: 8 }),
      });
      const data = await res.json();
      const papers = data.papers || [];
      setSearchResults(papers);
      if (papers.length === 0) {
        showToast(`Tidak ditemukan artikel di ArXiv untuk "${query}".`, 'warning');
      }
    } catch (err) {
      showToast('Gagal melakukan pencarian: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // 2. AI Smart Discovery (GraphRAG)
  const handleSmartSearch = async (query) => {
    if (!query) return;
    setLoading(true);
    setLoadingText('Menjalankan AI GraphRAG semantic matching...');
    try {
      const res = await fetch('/api/search/smart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 8, limit: 8 }),
      });
      const data = await res.json();
      const results = data.results || [];
      setSmartSearchResults(results);
      if (results.length === 0) {
        showToast(`Topik "${query}" belum tersimpan di graf lokal. Coba cari di Katalog ArXiv.`, 'info');
      }
    } catch (err) {
      showToast('Smart Search Gagal: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // 2b. OpenAlex Global Search
  const handleOpenAlexSearch = async (query) => {
    if (!query) return;
    setLoading(true);
    setLoadingText('Mencari di katalog global OpenAlex (250+ juta karya ilmiah)...');
    try {
      const res = await fetch(`/api/scholar/openalex/search?query=${encodeURIComponent(query)}&limit=8`);
      const data = await res.json();
      const papers = data.papers || [];
      setOpenAlexResults(papers);
      if (papers.length === 0) {
        showToast(`Tidak ditemukan artikel di OpenAlex untuk "${query}".`, 'warning');
      } else {
        showToast(`Ditemukan ${papers.length} artikel dari OpenAlex.`, 'success');
      }
    } catch (err) {
      showToast('Pencarian OpenAlex Gagal: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleImportOpenAlex = async (paper) => {
    setLoading(true);
    setLoadingText(`Mengimpor "${(paper.title || 'dokumen').slice(0, 30)}..." ke graf...`);
    try {
      const res = await fetch('/api/scholar/openalex/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(paper),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || 'Gagal mengimpor');

      showToast(`Berhasil mengimpor: ${paper.title || 'Dokumen OpenAlex'}`, 'success');
      fetchStats();

      const importedId = data.paper?.paper_id || paper.arxiv_id || paper.paper_id;
      if (importedId) {
        await handleExplorePaper(importedId, paper.title);
      }
      setSelectedNode({
        ...paper,
        id: importedId,
        paper_id: importedId,
        personality_tag: data.paper?.personality_tag || paper.personality_tag,
      });
    } catch (err) {
      showToast('Gagal mengimpor dokumen: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // 3. Cognitive / Associative Search (Spreading Activation)
  const handleCognitiveSearch = async (paperId, profile = 'balanced') => {
    if (!paperId) return;
    setLoading(true);
    setLoadingText('Mengaktifkan jalur pemikiran asosiatif graf...');
    setCognitiveResults([]);
    try {
      const url = `/api/cognitive-search/${encodeURIComponent(paperId.trim())}?profile=${encodeURIComponent(profile)}`;
      const res = await fetch(url, { method: 'POST' });
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        const body = await res.text();
        throw new Error(`Backend non-JSON (${res.status}): ${body.slice(0, 100)}`);
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);

      if (data.discoveries && data.discoveries.length > 0) {
        setCognitiveResults(data.discoveries);
        if (data.graph) {
          attemptedAutoIdsRef.current.clear();
          setRawGraphData(data.graph);
          const years = data.graph.nodes.map((n) => n.year).filter(Boolean);
          if (years.length > 0) setTimelineYear(Math.max(...years));
        }
        showToast(`Ditemukan ${data.discoveries.length} koneksi asosiatif.`, 'success');
      } else {
        showToast(`Tidak ditemukan asosiasi untuk paper: ${paperId}. Pastikan paper sudah ada di graf.`, 'warning');
      }
    } catch (err) {
      showToast('Asosiatif Search Gagal: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // 4. Unified Explore: Ingest to Graph & Render Graph in ONE click!
  const handleExplorePaper = async (paperId, title) => {
    if (!paperId) return;
    const cleanId = paperId.trim().replace(/^arxiv:\s*/i, '');
    setLoading(true);
    setLoadingText(`Mengambil & memetakan silsilah ${cleanId}...`);
    setSelectedNode(null);

    try {
      const isArxiv = /^\d{4}\.\d{4,5}(v\d+)?$/i.test(cleanId);
      if (isArxiv) {
        try {
          await fetch('/api/arxiv/fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ arxiv_ids: [cleanId], auto_fetch_references: true }),
          });
        } catch (fetchErr) {
          console.warn('Auto-fetch warning:', fetchErr);
        }
      }

      const res = await fetch(`/api/graph/lineage/${encodeURIComponent(cleanId)}?direction=both&depth=3`);
      const data = await res.json();

      if (!data.nodes || data.nodes.length === 0) {
        showToast(`Graf silsilah untuk paper ${cleanId} tidak memiliki node.`, 'warning');
      } else {
        attemptedAutoIdsRef.current.clear();
        setRawGraphData(data);

        const rootNode = data.nodes.find(
          (n) =>
            (n.arxiv_id && n.arxiv_id === cleanId) ||
            (n.paper_id && n.paper_id === cleanId) ||
            (n.id && n.id === cleanId) ||
            n.depth === 0 ||
            n.is_seed
        );
        const resolvedTitle =
          rootNode && rootNode.title && !rootNode.title.startsWith('ArXiv') && rootNode.title !== 'Unknown Title'
            ? rootNode.title
            : title && !title.startsWith('ArXiv') && title !== cleanId
            ? title
            : rootNode?.title || cleanId;

        addRecentPaper(cleanId, resolvedTitle);

        const years = data.nodes.map((n) => n.year).filter(Boolean);
        if (years.length > 0) {
          setTimelineYear(Math.max(...years));
        }
        showToast(`Silsilah berhasil dimuat: ${data.nodes.length} simpul terpetakan.`, 'success');
      }
      fetchStats();
    } catch (err) {
      showToast('Gagal memvisualisasikan silsilah: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleVisualize = async (arxivId) => {
    handleExplorePaper(arxivId, arxivId);
  };

  const handleUploadPdf = async (file) => {
    if (!file) return;
    setLoading(true);
    setLoadingText('Mengekstrak PDF, teks, & menganalisis kepribadian ilmiah...');
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/papers/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || 'Upload gagal');

      fetchStats();
      showToast(`Berhasil mengunggah dokumen: ${data.paper_id}`, 'success');
      if (data.paper_id) {
        handleExplorePaper(data.paper_id, file.name.replace(/\.pdf$/i, ''));
      }
    } catch (err) {
      showToast('Gagal mengunggah PDF: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleNodeClick = useCallback((nodeData) => {
    setSelectedNode(nodeData);
  }, []);

  const handleExpandNode = async (arxivId) => {
    if (!arxivId || !rawGraphData) return;
    setLoading(true);
    setLoadingText('Memperluas cabang silsilah...');
    try {
      const cleanId = arxivId.trim().replace(/^arxiv:\s*/i, '');
      const res = await fetch(`/api/graph/lineage/${cleanId}?direction=both&depth=1`);
      const newData = await res.json();

      if (!newData.nodes || newData.nodes.length === 0) {
        showToast(`Tidak ada cabang baru untuk diperluas dari ${cleanId}.`, 'info');
        return;
      }

      setRawGraphData((prev) => {
        const existingNodeIds = new Set(prev.nodes.map((n) => n.paper_id || n.id));
        const newNodes = newData.nodes.filter((n) => !existingNodeIds.has(n.paper_id || n.id));

        const existingEdges = new Set(prev.edges.map((e) => `${e.from}-${e.to}`));
        const newEdges = newData.edges.filter((e) => !existingEdges.has(`${e.from}-${e.to}`));

        if (newNodes.length === 0) {
          showToast('Seluruh referensi paper ini sudah ditampilkan di graf.', 'info');
        } else {
          showToast(`Berhasil menambahkan ${newNodes.length} simpul referensi baru.`, 'success');
        }

        return {
          ...prev,
          nodes: [...prev.nodes, ...newNodes],
          edges: [...prev.edges, ...newEdges],
        };
      });
    } catch (err) {
      showToast('Error memperluas simpul: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Pemfilteran Graf berdasarkan Linimasa, Sitasi/Koneksi Minimum, dan Batas Maksimum Simpul
  const { minYear, maxYear, totalRawNodes, filteredGraphData } = useMemo(() => {
    if (!rawGraphData || !rawGraphData.nodes) {
      return { minYear: 0, maxYear: 0, totalRawNodes: 0, filteredGraphData: null };
    }

    const allNodes = rawGraphData.nodes;
    const allEdges = rawGraphData.edges || [];

    // Hitung derajat koneksi dalam graf penuh
    const totalDegMap = {};
    const inDegMap = {};
    allNodes.forEach((n) => {
      const id = n.id || n.paper_id;
      totalDegMap[id] = 0;
      inDegMap[id] = 0;
    });
    allEdges.forEach((e) => {
      const u = e.from || e.source;
      const v = e.to || e.target;
      if (totalDegMap[u] !== undefined) totalDegMap[u] += 1;
      if (totalDegMap[v] !== undefined) totalDegMap[v] += 1;
      if (inDegMap[v] !== undefined) inDegMap[v] += 1;
    });

    const years = allNodes.map((n) => n.year).filter(Boolean);
    const min = years.length > 0 ? Math.min(...years) : 0;
    const max = years.length > 0 ? Math.max(...years) : 0;

    const selectedId = selectedNode ? selectedNode.id || selectedNode.paper_id : null;

    // 1. Filter berdasarkan tahun linimasa & ambang sitasi/koneksi minimum
    let candidates = allNodes.filter((n) => {
      const id = n.id || n.paper_id;
      const isRoot = n.depth === 0 || n.is_seed;
      const isSelected = id === selectedId;

      if (n.year && n.year > timelineYear && !isRoot) return false;
      if (isRoot || isSelected) return true;

      if (minCitationsFilter > 0) {
        const citCount = Math.max(Number(n.citation_count || 0), inDegMap[id] || 0);
        const degCount = totalDegMap[id] || 0;
        if (minCitationsFilter === 2) {
          // Mode Inti Silsilah: simpul yang dikutip >= 2 kali atau menghubungkan >= 2 makalah
          return citCount >= 2 || degCount >= 2;
        }
        return citCount >= minCitationsFilter || degCount >= minCitationsFilter + 1;
      }
      return true;
    });

    // 2. Urutkan berdasarkan tingkat kepentingan ilmiah agar pemangkasan maxNodesLimit selalu mempertahankan simpul utama
    candidates = [...candidates].sort((a, b) => {
      const idA = a.id || a.paper_id;
      const idB = b.id || b.paper_id;
      const isRootA = a.depth === 0 || a.is_seed ? 1 : 0;
      const isRootB = b.depth === 0 || b.is_seed ? 1 : 0;
      if (isRootA !== isRootB) return isRootB - isRootA;

      const isSelA = idA === selectedId ? 1 : 0;
      const isSelB = idB === selectedId ? 1 : 0;
      if (isSelA !== isSelB) return isSelB - isSelA;

      const scoreA =
        (totalDegMap[idA] || 0) * 15 +
        Number(a.citation_count || 0) * 4 +
        (a.personality_tag ? 20 : 0) +
        (a.activation_energy || 0) * 50;
      const scoreB =
        (totalDegMap[idB] || 0) * 15 +
        Number(b.citation_count || 0) * 4 +
        (b.personality_tag ? 20 : 0) +
        (b.activation_energy || 0) * 50;

      if (scoreB !== scoreA) return scoreB - scoreA;
      return (Number(b.year) || 0) - (Number(a.year) || 0);
    });

    if (maxNodesLimit > 0 && candidates.length > maxNodesLimit) {
      candidates = candidates.slice(0, maxNodesLimit);
    }

    const validNodeIds = new Set(candidates.map((n) => n.id || n.paper_id));
    const filteredEdges = allEdges.filter(
      (e) => validNodeIds.has(e.from || e.source) && validNodeIds.has(e.to || e.target)
    );

    return {
      minYear: min,
      maxYear: max,
      totalRawNodes: allNodes.length,
      filteredGraphData: { nodes: candidates, edges: filteredEdges },
    };
  }, [rawGraphData, timelineYear, minCitationsFilter, maxNodesLimit, selectedNode]);

  // Statistik klasifikasi simpul pada tampilan aktif
  const classificationStats = useMemo(() => {
    const visibleNodes = filteredGraphData?.nodes || [];
    const total = visibleNodes.length;
    const tagged = visibleNodes.filter((n) => Boolean(n.personality_tag)).length;
    const untagged = visibleNodes.filter(
      (n) => !n.personality_tag && (n.paper_id || n.id || n.arxiv_id)
    );
    const percent = total > 0 ? Math.round((tagged / total) * 100) : 100;
    return { total, tagged, untagged, percent };
  }, [filteredGraphData]);

  // Fungsi eksekusi batch klasifikasi (digunakan oleh mode otomatis maupun tombol manual)
  const runClassificationBatch = useCallback(
    async (targetNodes, isManual = false) => {
      if (batchAnalyzing || !targetNodes || targetNodes.length === 0) return;

      const targetIds = targetNodes
        .slice(0, 6)
        .map((n) => n.paper_id || n.id || n.arxiv_id)
        .filter(Boolean);

      if (targetIds.length === 0) return;

      targetIds.forEach((id) => attemptedAutoIdsRef.current.add(id));
      setBatchAnalyzing(true);
      if (isManual) {
        showToast(`Menganalisis peran ilmiah untuk ${targetIds.length} simpul...`, 'info');
      }

      try {
        const res = await fetch('/api/graph/batch-analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ paper_ids: targetIds, max_papers: 6 }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.message || 'Analisis massal gagal');

        if (data.results && data.results.length > 0) {
          const resultMap = {};
          data.results.forEach((r) => {
            if (r.status === 'success' && r.personality_tag) {
              if (r.paper_id) resultMap[r.paper_id] = r;
              if (r.requested_id) resultMap[r.requested_id] = r;
            }
          });

          if (Object.keys(resultMap).length > 0) {
            setRawGraphData((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                nodes: prev.nodes.map((n) => {
                  const pid = n.paper_id || n.id;
                  const aid = n.arxiv_id;
                  const matched = resultMap[pid] || (aid ? resultMap[aid] : null);
                  if (matched) {
                    return {
                      ...n,
                      personality_tag: matched.personality_tag,
                      confidence_score: matched.confidence_score,
                      reasoning: matched.reasoning || n.reasoning,
                    };
                  }
                  return n;
                }),
              };
            });

            // Perbarui pula selectedNode jika sedang dibuka di DetailPanel
            setSelectedNode((prev) => {
              if (!prev) return prev;
              const pid = prev.paper_id || prev.id;
              const matched = resultMap[pid] || (prev.arxiv_id ? resultMap[prev.arxiv_id] : null);
              if (matched) {
                return {
                  ...prev,
                  personality_tag: matched.personality_tag,
                  confidence_score: matched.confidence_score,
                  reasoning: matched.reasoning || prev.reasoning,
                };
              }
              return prev;
            });

            fetchStats();
            if (isManual) {
              showToast(`Klasifikasi selesai: ${data.succeeded} simpul diperbarui.`, 'success');
            }
          }
        }
      } catch (err) {
        if (isManual) {
          showToast('Gagal menjalankan klasifikasi: ' + err.message, 'error');
        }
      } finally {
        setBatchAnalyzing(false);
      }
    },
    [batchAnalyzing, showToast]
  );

  // Worker Klasifikasi Otomatis Latar Belakang (berjalan bertahap saat graf memiliki simpul belum terklasifikasi)
  useEffect(() => {
    if (!autoClassify || batchAnalyzing || loading) return;

    const pendingNodes = classificationStats.untagged.filter((n) => {
      const id = n.paper_id || n.id || n.arxiv_id;
      return id && !attemptedAutoIdsRef.current.has(id);
    });

    if (pendingNodes.length === 0) return;

    const timer = setTimeout(() => {
      runClassificationBatch(pendingNodes, false);
    }, 650);

    return () => clearTimeout(timer);
  }, [autoClassify, batchAnalyzing, loading, classificationStats.untagged, runClassificationBatch]);

  const handleManualBatchAnalyze = () => {
    if (classificationStats.untagged.length === 0) {
      showToast('Seluruh simpul pada tampilan ini sudah memiliki klasifikasi peran ilmiah.', 'info');
      return;
    }
    // Reset daftar percobaan agar simpul yang tersisa dapat dianalisis ulang
    attemptedAutoIdsRef.current.clear();
    setAutoClassify(true);
    runClassificationBatch(classificationStats.untagged, true);
  };

  const handleExportPNG = () => {
    setExportMenuOpen(false);
    const canvas = document.querySelector('.vis-network canvas');
    if (!canvas) return;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = canvas.width;
    tempCanvas.height = canvas.height;
    const ctx = tempCanvas.getContext('2d');

    ctx.fillStyle = '#0e1116';
    ctx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
    ctx.drawImage(canvas, 0, 0);

    const url = tempCanvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = url;
    a.download = `graph-${rawGraphData?.root || 'export'}.png`;
    a.click();
    showToast('Gambar graf berhasil diunduh.', 'success');
  };

  const handleExportBibtex = async () => {
    setExportMenuOpen(false);
    if (!rawGraphData?.root) return;
    try {
      const res = await fetch(`/api/graph/bibtex/${rawGraphData.root}`);
      const text = await res.text();
      const blob = new Blob([text], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `references-${rawGraphData.root}.bib`;
      a.click();
      showToast('Berkas BibTeX berhasil diekspor.', 'success');
    } catch (err) {
      showToast('Gagal mengekspor BibTeX: ' + err.message, 'error');
    }
  };

  const handleShareLink = () => {
    setExportMenuOpen(false);
    if (!rawGraphData?.root) return;
    const shareUrl = `${window.location.origin}${window.location.pathname}?viz_id=${rawGraphData.root}`;
    navigator.clipboard.writeText(shareUrl).then(() => {
      showToast('Tautan silsilah disalin ke papan klip.', 'success');
    });
  };

  const handleGeneratePDF = () => {
    setExportMenuOpen(false);
    if (!filteredGraphData) return;
    const nodes = filteredGraphData.nodes;
    let html = `<html><head><title>Research Lineage Report</title>
      <style>
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px; color: #24292f; background: #fff; line-height: 1.5; }
        h1 { color: #0969da; border-bottom: 2px solid #eaecef; padding-bottom: 10px; font-size: 24px; }
        h2 { margin-top: 30px; font-size: 18px; color: #1f2328; }
        .paper { margin-bottom: 15px; padding: 15px; border: 1px solid #d0d7de; border-radius: 6px; }
        .tag { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 11px; color: #fff; font-weight: bold; margin-bottom: 8px;}
        .PIONEER { background-color: #8957e5; }
        .OPTIMIZER { background-color: #238636; }
        .BRIDGE { background-color: #d29922; }
        .UNTAGGED { background-color: #57606a; }
      </style>
    </head><body>`;

    html += `<h1>Research Lineage Report: ${rawGraphData.root}</h1>`;
    html += `<p>Total Paper dalam Silsilah Graf: <strong>${nodes.length}</strong></p>`;

    const byTag = nodes.reduce((acc, n) => {
      const tag = n.personality_tag || 'UNTAGGED';
      if (!acc[tag]) acc[tag] = [];
      acc[tag].push(n);
      return acc;
    }, {});

    for (const [tag, group] of Object.entries(byTag).sort()) {
      html += `<h2>${tag} Papers (${group.length})</h2>`;
      group.forEach((n) => {
        html += `<div class="paper">
          <div class="tag ${tag}">${tag}</div>
          <div style="font-size: 15px; font-weight: 600;">${n.title || 'Unknown Title'}</div>
          <div style="font-size: 12px; color: #57606a; margin-top: 4px;">ID: ${n.arxiv_id || n.paper_id || 'N/A'} | Tahun: ${n.year || 'N/A'}</div>
          ${n.reasoning ? `<div style="font-size: 12px; border-left: 3px solid #d0d7de; padding-left: 10px; margin-top: 8px; color: #424a53;"><em>${n.reasoning}</em></div>` : ''}
        </div>`;
      });
    }
    html += `</body></html>`;

    const printWindow = window.open('', '_blank');
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
    }, 800);
  };

  return (
    <div className="app-layout">
      <TopBar health={health} stats={stats} />

      <div className="main-container">
        <Sidebar
          onSearch={handleSearch}
          searchResults={searchResults}
          onSmartSearch={handleSmartSearch}
          smartSearchResults={smartSearchResults}
          onCognitiveSearch={handleCognitiveSearch}
          cognitiveResults={cognitiveResults}
          onOpenAlexSearch={handleOpenAlexSearch}
          openAlexResults={openAlexResults}
          onImportOpenAlex={handleImportOpenAlex}
          onExplorePaper={handleExplorePaper}
          onUploadPdf={handleUploadPdf}
          recentPapers={recentPapers}
          onSelectRecent={handleExplorePaper}
          readingList={readingList}
          onToggleBookmark={handleToggleBookmark}
          onUpdateReadingStatus={handleUpdateReadingStatus}
          onUpdateReadingNotes={handleUpdateReadingNotes}
          onRemoveFromReadingList={handleRemoveFromReadingList}
          onClearReadingList={handleClearReadingList}
          onExportReadingListBibtex={handleExportReadingListBibtex}
          showToast={showToast}
        />

        <main className={`graph-layout ${selectedNode ? 'detail-panel-open' : ''}`}>
          {/* ── Bilah Kontrol Kanvas Terpadu (Responsif & Bebas Tumpang Tindih) ── */}
          {rawGraphData && rawGraphData.nodes && rawGraphData.nodes.length > 0 && (
            <div className="canvas-control-bar">
              <div className="toolbar-group-left">
                {/* Mode Tata Letak */}
                <div className="segmented-control">
                  <button
                    className={`segmented-btn ${layoutMode === 'physics' ? 'active' : ''}`}
                    onClick={() => setLayoutMode('physics')}
                    title="Tata letak bebas berbasis fisika kluster"
                  >
                    Fisika Bebas
                  </button>
                  <button
                    className={`segmented-btn ${layoutMode === 'chronological' ? 'active' : ''}`}
                    onClick={() => setLayoutMode('chronological')}
                    title="Tata letak berurutan berdasarkan garis waktu tahun"
                  >
                    Garis Waktu
                  </button>
                </div>

                <div className="toolbar-divider" />

                {/* Kontrol Batas Jumlah Simpul */}
                <div className="toolbar-filter-item" title="Batas maksimum simpul yang ditampilkan berdasarkan tingkat kepentingan">
                  <span className="toolbar-filter-label">Simpul:</span>
                  <select
                    className="toolbar-select"
                    value={maxNodesLimit}
                    onChange={(e) => setMaxNodesLimit(Number(e.target.value))}
                  >
                    <option value={20}>Maks 20 ({Math.min(20, totalRawNodes)}/{totalRawNodes})</option>
                    <option value={35}>Maks 35 ({Math.min(35, totalRawNodes)}/{totalRawNodes})</option>
                    <option value={50}>Maks 50 ({Math.min(50, totalRawNodes)}/{totalRawNodes})</option>
                    <option value={0}>Semua ({totalRawNodes})</option>
                  </select>
                </div>

                {/* Kontrol Filter Sitasi / Koneksi Minimum */}
                <div className="toolbar-filter-item" title="Saring simpul berdasarkan jumlah sitasi atau koneksi minimum">
                  <span className="toolbar-filter-label">Filter:</span>
                  <select
                    className="toolbar-select"
                    value={minCitationsFilter}
                    onChange={(e) => setMinCitationsFilter(Number(e.target.value))}
                  >
                    <option value={0}>Semua Sitasi</option>
                    <option value={1}>Min. 1 Sitasi</option>
                    <option value={2}>Inti (Koneksi &ge; 2)</option>
                    <option value={5}>Sitasi Tinggi (&ge; 5)</option>
                  </select>
                </div>

                {/* Kontrol Kepadatan Label (Level of Detail) */}
                <div className="toolbar-filter-item" title="Atur kepadatan tampilan label judul pada graf">
                  <span className="toolbar-filter-label">Label:</span>
                  <select
                    className="toolbar-select"
                    value={labelMode}
                    onChange={(e) => setLabelMode(e.target.value)}
                  >
                    <option value="adaptive">Adaptif (Zoom)</option>
                    <option value="core">Hanya Simpul Inti</option>
                    <option value="all">Tampilkan Semua</option>
                  </select>
                </div>
              </div>

              <div className="toolbar-group-right">
                {/* Indikator Progres Klasifikasi Otomatis AI */}
                <div
                  className={`ai-progress-pill ${batchAnalyzing ? 'analyzing' : ''} ${
                    classificationStats.untagged.length === 0 ? 'complete' : ''
                  }`}
                  title="Progres klasifikasi otomatis peran ilmiah (Pioneer, Optimizer, Bridge)"
                >
                  {batchAnalyzing && <span className="spinner-xs" />}
                  <div className="ai-progress-info">
                    <span className="ai-progress-text">
                      Klasifikasi AI: <strong>{classificationStats.tagged}</strong>/{classificationStats.total} ({classificationStats.percent}%)
                    </span>
                    <div className="ai-mini-track">
                      <div
                        className="ai-mini-fill"
                        style={{ width: `${classificationStats.percent}%` }}
                      />
                    </div>
                  </div>
                  {classificationStats.untagged.length > 0 && (
                    <button
                      className="ai-toggle-btn"
                      onClick={() => {
                        if (autoClassify) {
                          setAutoClassify(false);
                        } else {
                          handleManualBatchAnalyze();
                        }
                      }}
                    >
                      {autoClassify ? 'Jeda' : 'Lanjutkan'}
                    </button>
                  )}
                </div>

                {/* Menu Ekspor & Bagikan yang Ringkas */}
                <div className="export-dropdown-wrapper" ref={exportMenuRef}>
                  <button
                    className="btn btn-toolbar-action"
                    onClick={() => setExportMenuOpen((prev) => !prev)}
                  >
                    <span>Ekspor &amp; Tautan</span>
                    <span className="caret-down">&#9662;</span>
                  </button>

                  {exportMenuOpen && (
                    <div className="toolbar-dropdown-menu">
                      <button className="dropdown-item" onClick={handleShareLink}>
                        Salin Tautan Silsilah
                      </button>
                      <button className="dropdown-item" onClick={handleExportPNG}>
                        Unduh Gambar Graf (PNG)
                      </button>
                      <button className="dropdown-item" onClick={handleExportBibtex}>
                        Ekspor Sitasi Graf (BibTeX)
                      </button>
                      <button className="dropdown-item" onClick={handleGeneratePDF}>
                        Cetak Laporan Silsilah (PDF)
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <GraphView
            graphData={filteredGraphData}
            selectedNode={selectedNode}
            onNodeClick={handleNodeClick}
            onExpandNode={handleExpandNode}
            onSelectExample={handleExplorePaper}
            layoutMode={layoutMode}
            onLayoutModeChange={setLayoutMode}
            labelMode={labelMode}
          />

          <TimelineSlider
            minYear={minYear}
            maxYear={maxYear}
            currentYear={timelineYear}
            onChange={setTimelineYear}
          />
        </main>

        <DetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          onExpand={(id) => {
            setSelectedNode(null);
            handleExplorePaper(id, id);
          }}
          onExpandNode={handleExpandNode}
          showToast={showToast}
          onSelectPaper={(p) => {
            const targetId = p.paper_id || p.id || p.arxiv_id;
            const foundNode = rawGraphData?.nodes?.find(
              (n) =>
                (n.paper_id || n.id || n.arxiv_id) === targetId ||
                (p.arxiv_id && n.arxiv_id === p.arxiv_id)
            );
            if (foundNode) {
              setSelectedNode(foundNode);
              showToast(`Memilih dokumen dari relasi: ${foundNode.title || targetId}`, 'info');
            } else {
              setSelectedNode({ ...p, id: targetId });
              showToast(`Membuka metadata dokumen: ${p.title || targetId}`, 'info');
            }
          }}
          readingList={readingList}
          onToggleBookmark={handleToggleBookmark}
          onUpdateReadingStatus={handleUpdateReadingStatus}
          onAnalyzed={(data) => {
            setRawGraphData((prev) =>
              prev
                ? {
                    ...prev,
                    nodes: prev.nodes.map((n) =>
                      (n.paper_id || n.id) === data.paper_id
                        ? {
                            ...n,
                            personality_tag: data.personality_tag,
                            confidence_score: data.confidence_score,
                            reasoning: data.reasoning,
                          }
                        : n
                    ),
                  }
                : prev
            );
            showToast(
              `Analisis selesai: ${data.personality_tag || 'Tagged'} (${Math.round(
                (data.confidence_score || 0) * 100
              )}% Confidence)`,
              'success'
            );
          }}
        />
      </div>

      {loading && (
        <div className="loading-overlay">
          <div className="spinner" style={{ marginBottom: 12, width: 24, height: 24 }} />
          <div>{loadingText}</div>
        </div>
      )}

      {/* ── Toast Notifications Container ─────────────────────────────────── */}
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map((t) => (
            <div key={t.id} className={`toast toast-${t.type}`}>
              <div className="toast-message">{t.message}</div>
              <button className="toast-close" onClick={() => removeToast(t.id)}>
                &times;
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
