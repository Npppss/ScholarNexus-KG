import { useState, useEffect, useCallback, useMemo } from 'react';
import TopBar from './components/TopBar';
import Sidebar from './components/Sidebar';
import GraphView from './components/GraphView';
import DetailPanel from './components/DetailPanel';
import TimelineSlider from './components/TimelineSlider';

export default function App() {
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [smartSearchResults, setSmartSearchResults] = useState([]);
  const [rawGraphData, setRawGraphData] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const [timelineYear, setTimelineYear] = useState(new Date().getFullYear());

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      setHealth(data);
    } catch (err) {
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
    
    // Check for viz_id in URL for Share Links
    const urlParams = new URLSearchParams(window.location.search);
    const vizId = urlParams.get('viz_id');
    if (vizId) {
      handleVisualize(vizId);
    }

    const interval = setInterval(() => {
      fetchHealth();
      fetchStats();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleSearch = async (query) => {
    if (!query) return;
    setLoading(true);
    try {
      const res = await fetch('/api/arxiv/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, max_results: 5 })
      });
      const data = await res.json();
      setSearchResults(data.papers || []);
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSmartSearch = async (query) => {
    if (!query) return;
    setLoading(true);
    try {
      const res = await fetch('/api/search/smart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5, limit: 5 })
      });
      const data = await res.json();
      setSmartSearchResults(data.results || []);
    } catch (err) {
      alert("Smart Search Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFetchToGraph = async (arxivId) => {
    if (!arxivId) return;
    setLoading(true);
    try {
      const res = await fetch('/api/arxiv/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ arxiv_ids: [arxivId], auto_fetch_references: true })
      });
      await res.json();
      fetchStats();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadPdf = async (file) => {
    if (!file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch('/api/papers/upload', {
        method: 'POST',
        // Do not set Content-Type header manually when using FormData
        body: formData
      });
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || "Upload failed");
      }
      alert(`Success! Node created: ${data.paper_id} (Personality: ${data.personality_tag})`);
      fetchStats();
      if (data.paper_id) {
         handleVisualize(data.paper_id);
      }
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVisualize = async (arxivId) => {
    if (!arxivId) return;
    const cleanId = arxivId.trim();
    if (!cleanId) return;
    
    setLoading(true);
    setSelectedNode(null);
    try {
      const res = await fetch(`/api/graph/lineage/${cleanId}?direction=both&depth=3`);
      const data = await res.json();
      
      if (!data.nodes || data.nodes.length === 0) {
        alert(`No data found in Graph DB for ArXiv ID: ${cleanId}. Make sure you ingested it first.`);
      }
      
      setRawGraphData(data);
      
      // Calculate max year for timeline
      if (data && data.nodes && data.nodes.length > 0) {
        const years = data.nodes.map(n => n.year).filter(y => y);
        if (years.length > 0) {
          setTimelineYear(Math.max(...years));
        }
      }
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleNodeClick = useCallback((nodeData) => {
    setSelectedNode(nodeData);
  }, []);

  const handleExportPNG = () => {
    const canvas = document.querySelector('.vis-network canvas');
    if (!canvas) return;
    
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = canvas.width;
    tempCanvas.height = canvas.height;
    const ctx = tempCanvas.getContext('2d');
    
    // Fill background with app bg color so it's not transparent
    ctx.fillStyle = '#0e1116'; 
    ctx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
    ctx.drawImage(canvas, 0, 0);
    
    const url = tempCanvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = url;
    a.download = `graph-${rawGraphData?.root || 'export'}.png`;
    a.click();
  };

  const handleExportBibtex = async () => {
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
    } catch (err) {
      alert("Error exporting BibTeX: " + err.message);
    }
  };

  const handleShareLink = () => {
    if (!rawGraphData?.root) return;
    const shareUrl = `${window.location.origin}${window.location.pathname}?viz_id=${rawGraphData.root}`;
    navigator.clipboard.writeText(shareUrl).then(() => {
      alert("Share Link copied to clipboard!");
    });
  };

  const handleGeneratePDF = () => {
    if (!filteredGraphData) return;
    const nodes = filteredGraphData.nodes;
    let html = `<html><head><title>Research Lineage Report</title>
      <style>
        body { font-family: 'Inter', sans-serif; padding: 40px; color: #24292f; background: #fff; }
        h1 { color: #0969da; border-bottom: 2px solid #eaecef; padding-bottom: 10px; }
        h2 { margin-top: 30px; font-size: 20px; }
        .paper { margin-bottom: 15px; padding: 15px; border: 1px solid #d0d7de; border-radius: 6px; }
        .tag { display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 11px; color: #fff; font-weight: bold; margin-bottom: 8px;}
        .PIONEER { background-color: #8957e5; }
        .OPTIMIZER { background-color: #238636; }
        .BRIDGE { background-color: #d29922; }
        .UNTAGGED { background-color: #57606a; }
      </style>
    </head><body>`;
    
    html += `<h1>Research Lineage Report: ${rawGraphData.root}</h1>`;
    html += `<p>Total Papers in Lineage: <strong>${nodes.length}</strong></p>`;
    
    const byTag = nodes.reduce((acc, n) => {
      const tag = n.personality_tag || 'UNTAGGED';
      if (!acc[tag]) acc[tag] = [];
      acc[tag].push(n);
      return acc;
    }, {});
    
    for (const [tag, group] of Object.entries(byTag).sort()) {
      html += `<h2>${tag} Papers (${group.length})</h2>`;
      group.forEach(n => {
        html += `<div class="paper">
          <div class="tag ${tag}">${tag}</div>
          <div style="font-size: 16px; font-weight: 600;">${n.title || 'Unknown Title'}</div>
          <div style="font-size: 13px; color: #57606a; margin-top: 4px;">ArXiv ID: ${n.arxiv_id || 'N/A'} | Year: ${n.year || 'N/A'}</div>
          ${n.reasoning ? `<div style="font-size: 13px; border-left: 3px solid #d0d7de; padding-left: 10px; margin-top: 8px;"><em>${n.reasoning}</em></div>` : ''}
        </div>`;
      });
    }
    html += `</body></html>`;
    
    const printWindow = window.open('', '_blank');
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => { printWindow.print(); }, 800);
  };

  const { minYear, maxYear, filteredGraphData } = useMemo(() => {
    if (!rawGraphData || !rawGraphData.nodes) {
      return { minYear: 0, maxYear: 0, filteredGraphData: null };
    }

    const years = rawGraphData.nodes.map(n => n.year).filter(y => y);
    const min = years.length > 0 ? Math.min(...years) : 0;
    const max = years.length > 0 ? Math.max(...years) : 0;

    const filteredNodes = rawGraphData.nodes.filter(n => !n.year || n.year <= timelineYear);
    const validNodeIds = new Set(filteredNodes.map(n => n.id || n.paper_id));
    const filteredEdges = (rawGraphData.edges || []).filter(
      e => validNodeIds.has(e.from || e.source) && validNodeIds.has(e.to || e.target)
    );

    return {
      minYear: min,
      maxYear: max,
      filteredGraphData: { nodes: filteredNodes, edges: filteredEdges }
    };
  }, [rawGraphData, timelineYear]);

  return (
    <div className="app-layout">
      <TopBar health={health} stats={stats} />
      
      <div className="main-container">
        <Sidebar 
          onSearch={handleSearch} 
          searchResults={searchResults}
          onSmartSearch={handleSmartSearch}
          smartSearchResults={smartSearchResults}
          onFetchToGraph={handleFetchToGraph}
          onUploadPdf={handleUploadPdf}
          onVisualize={handleVisualize}
        />
        
        <main className="graph-layout">
          {rawGraphData && (
            <div className="actions-toolbar" style={{ position: 'absolute', top: 16, right: 16, zIndex: 10, display: 'flex', gap: '8px', background: 'var(--bg-surface)', padding: '6px', borderRadius: '8px', border: '1px solid var(--border-color)', boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}>
              <button className="btn" style={{ fontSize: '11px', padding: '6px 12px' }} onClick={handleExportPNG}>📸 PNG</button>
              <button className="btn" style={{ fontSize: '11px', padding: '6px 12px' }} onClick={handleExportBibtex}>📚 BibTeX</button>
              <button className="btn" style={{ fontSize: '11px', padding: '6px 12px' }} onClick={handleGeneratePDF}>📄 PDF Report</button>
              <button className="btn btn-primary" style={{ fontSize: '11px', padding: '6px 12px' }} onClick={handleShareLink}>🔗 Share Link</button>
            </div>
          )}

          <GraphView 
            graphData={filteredGraphData} 
            onNodeClick={handleNodeClick} 
          />
          
          <TimelineSlider 
            minYear={minYear} 
            maxYear={maxYear}
            currentYear={timelineYear}
            onChange={setTimelineYear}
          />

          <DetailPanel 
            node={selectedNode} 
            onClose={() => setSelectedNode(null)} 
            onExpand={(id) => {
              setSelectedNode(null);
              handleVisualize(id);
            }} 
          />
        </main>
      </div>

      {loading && (
        <div className="loading-overlay">
          <div>Processing request...</div>
        </div>
      )}
    </div>
  );
}
