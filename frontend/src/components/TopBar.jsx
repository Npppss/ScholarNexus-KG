export default function TopBar({ health, stats }) {
  const isHealthy = health?.status === "healthy";
  const totalPapers = stats?.total_papers || 0;
  const totalCitations = stats?.total_citations || 0;
  
  return (
    <div className="topbar">
      <div className="topbar-brand-group">
        <svg className="topbar-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" />
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
        <div>
          <div className="topbar-brand">ScholarNexus KG</div>
          <div className="topbar-tagline">Scientific Knowledge Graph & Literature Review</div>
        </div>
      </div>
      
      <div className="topbar-stats">
        <div className="stat-pill" title="Total dokumen dalam graf">
          <span className="stat-label">Paper:</span>
          <span className="stat-number">{totalPapers}</span>
        </div>
        <div className="stat-pill" title="Total relasi sitasi terpetakan">
          <span className="stat-label">Sitasi:</span>
          <span className="stat-number">{totalCitations}</span>
        </div>
        <div className="status-indicator" title={isHealthy ? 'Sistem Terhubung' : 'Sistem Terputus'}>
          <span className={`status-dot ${isHealthy ? 'healthy' : 'offline'}`}></span>
          <span className="status-text">{isHealthy ? 'Online' : 'Offline'}</span>
        </div>
      </div>
    </div>
  );
}
