export default function TopBar({ health, stats }) {
  const isHealthy = health?.status === "healthy";
  
  return (
    <div className="topbar">
      <div className="topbar-brand">
        ScholarNexus-KG
      </div>
      
      <div className="topbar-stats">
        <span>Nodes: {stats?.total_papers || 0}</span>
        <span>Edges: {stats?.total_citations + stats?.similarity_edges || stats?.total_citations || 0}</span>
        <div className="status-indicator">
          <span>API</span>
          <span className={`status-dot ${isHealthy ? 'healthy' : 'offline'}`} title={health?.status || 'offline'}></span>
        </div>
      </div>
    </div>
  );
}
