import { useState } from 'react';

export default function Sidebar({ onSearch, onFetchToGraph, onVisualize, searchResults }) {
  const [query, setQuery] = useState('');
  const [arxivId, setArxivId] = useState('');
  const [visualizeId, setVisualizeId] = useState('');

  return (
    <div className="sidebar-layout">
      {/* 1. Paper Search */}
      <div className="sidebar-section">
        <div className="sidebar-title">ArXiv Catalog Search</div>
        <div className="form-group">
          <input 
            className="input-field"
            type="text" 
            placeholder="e.g. Knowledge Graph" 
            value={query} 
            onChange={(e) => setQuery(e.target.value)} 
          />
          <button className="btn btn-primary" onClick={() => onSearch(query)}>Search Catalog</button>
        </div>
        
        {searchResults && searchResults.length > 0 && (
          <div style={{ marginTop: '16px' }}>
            <div className="sidebar-title" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Results</div>
            {searchResults.map(p => (
              <div key={p.arxiv_id} className="result-card">
                <div className="result-card-title">{p.title}</div>
                <div className="result-card-meta">ID: {p.arxiv_id} | Year: {p.year}</div>
                <button 
                  className="btn" 
                  style={{ width: '100%', padding: '4px', fontSize: '11px' }}
                  onClick={() => setArxivId(p.arxiv_id)}
                >
                  Select ID
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Save Process */}
      <div className="sidebar-section">
        <div className="sidebar-title">Save to Graph Database</div>
        <div className="form-group">
          <input 
            className="input-field"
            type="text" 
            placeholder="ArXiv ID..." 
            value={arxivId} 
            onChange={(e) => setArxivId(e.target.value)} 
          />
          <button className="btn" onClick={() => {
            onFetchToGraph(arxivId);
            setVisualizeId(arxivId);
          }}>
            Ingest Paper
          </button>
        </div>
      </div>

      {/* 3. Visualization */}
      <div className="sidebar-section">
        <div className="sidebar-title">Lineage Visualization</div>
        <div className="form-group">
          <input 
            className="input-field"
            type="text" 
            placeholder="Available ArXiv ID..." 
            value={visualizeId} 
            onChange={(e) => setVisualizeId(e.target.value)} 
          />
          <button className="btn btn-primary" onClick={() => onVisualize(visualizeId)}>
            Render Graph
          </button>
        </div>
      </div>
    </div>
  );
}
