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
          onFetchToGraph={handleFetchToGraph}
          onVisualize={handleVisualize}
        />
        
        <main className="graph-layout">
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
