import { useState } from 'react';

export default function Sidebar({ onSearch, onFetchToGraph, onUploadPdf, onVisualize, searchResults, onSmartSearch, smartSearchResults }) {
  const [query, setQuery] = useState('');
  const [smartQuery, setSmartQuery] = useState('');
  const [arxivId, setArxivId] = useState('');
  const [visualizeId, setVisualizeId] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

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

      {/* 1b. Smart Discovery (GraphRAG) */}
      <div className="sidebar-section">
        <div className="sidebar-title">GraphRAG Smart Discovery</div>
        <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '8px' }}>
          Discover AI-curated papers combining semantic meaning & citation paths.
        </div>
        <div className="form-group">
          <input 
            className="input-field"
            type="text" 
            placeholder="e.g. transformers context rules" 
            value={smartQuery} 
            onChange={(e) => setSmartQuery(e.target.value)} 
          />
          <button className="btn btn-primary" onClick={() => onSmartSearch(smartQuery)}>Discover</button>
        </div>
        
        {smartSearchResults && smartSearchResults.length > 0 && (
          <div style={{ marginTop: '16px' }}>
            <div className="sidebar-title" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>AI Ranked Results</div>
            {smartSearchResults.map(p => (
              <div key={p.paper_id} className="result-card" style={{ borderLeft: '3px solid #8b5cf6' }}>
                <div className="result-card-title">{p.title}</div>
                <div className="result-card-meta">
                  Score: {p.final_score.toFixed(2)} | Citations: {p.citation_count} | Sim: {p.vector_similarity.toFixed(2)}
                </div>
                <button 
                  className="btn" 
                  style={{ width: '100%', padding: '4px', fontSize: '11px', marginTop: '6px' }}
                  onClick={() => {
                     setVisualizeId(p.paper_id ?? p.arxiv_id);
                     onVisualize(p.paper_id ?? p.arxiv_id);
                  }}
                >
                  Visualize Lineage ({p.year ?? 'Unknown'})
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

      {/* 3. Upload PDF Paper */}
      <div className="sidebar-section">
        <div className="sidebar-title">Upload PDF Paper</div>
        <div className="form-group">
          <input 
            className="input-field"
            type="file" 
            accept="application/pdf"
            onChange={(e) => setSelectedFile(e.target.files[0])} 
          />
          <button className="btn" onClick={() => {
            if (selectedFile) {
              onUploadPdf(selectedFile);
            } else {
              alert("Please select a PDF file first");
            }
          }}>
            Upload & Ingest
          </button>
        </div>
      </div>

      {/* 4. Visualization */}
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
