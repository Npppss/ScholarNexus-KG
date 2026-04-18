export default function DetailPanel({ node, onClose, onExpand }) {
  if (!node) return null;

  const tagLower = node.personality_tag?.toLowerCase() || '';
  const tagClass = tagLower ? `tag-${tagLower}` : '';

  return (
    <div className={`detail-panel ${node ? 'open' : ''}`}>
      <div className="detail-header">
        <h3>Node Metadata</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="detail-body">
        <h2 style={{ fontSize: '16px', lineHeight: '1.4', marginBottom: '16px' }}>
          {node.title || 'Unknown Title'}
        </h2>
        
        {node.personality_tag ? (
          <div className={`tag-badge ${tagClass}`}>
            {node.personality_tag.toUpperCase()}
          </div>
        ) : (
          <div className="tag-badge">UNTAGGED</div>
        )}

        <div className="detail-section">
          <div className="detail-label">ArXiv ID</div>
          <div className="detail-value">{node.arxiv_id || 'N/A'}</div>
        </div>

        <div className="detail-section">
          <div className="detail-label">Publication Year</div>
          <div className="detail-value">{node.year || 'N/A'}</div>
        </div>

        <div className="detail-section">
          <div className="detail-label">Authors</div>
          <div className="detail-value">{node.authors ? node.authors.join(', ') : 'N/A'}</div>
        </div>

        <div className="detail-section">
          <div className="detail-label">Source Link</div>
          <div className="detail-value">
            {node.arxiv_id ? (
              <a href={`https://arxiv.org/abs/${node.arxiv_id}`} target="_blank" rel="noopener noreferrer" style={{color: '#58a6ff', textDecoration: 'underline'}}>
                View on ArXiv
              </a>
            ) : 'N/A'}
          </div>
        </div>

        {node.reasoning && (
          <div className="detail-section" style={{ marginTop: '24px' }}>
            <div className="detail-label">Classification Reasoning</div>
            <div className="detail-reasoning">"{node.reasoning}"</div>
          </div>
        )}
      </div>
      
      <div className="detail-footer">
        {node.arxiv_id ? (
           <button 
              className="btn btn-primary" 
              style={{ width: '100%' }}
              onClick={() => onExpand(node.arxiv_id)}
            >
              Expand Lineage
           </button>
        ) : (
          <div style={{ color: 'var(--text-secondary)', fontSize: '12px', textAlign: 'center' }}>
            ArXiv ID unavailable for expansion.
          </div>
        )}
      </div>
    </div>
  );
}
