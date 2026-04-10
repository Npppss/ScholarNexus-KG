import { useEffect, useRef } from 'react';
import { Network } from 'vis-network';

export default function GraphView({ graphData, onNodeClick }) {
  const containerRef = useRef(null);
  const networkRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !graphData || !graphData.nodes) return;

    const nodes = graphData.nodes.map((n) => {
      let nodeColor = { background: '#1f6feb', border: '#1f6feb' }; // Default / Stub node
      
      const tag = n.personality_tag?.toUpperCase();
      if (tag === 'PIONEER') nodeColor = { background: '#8957e5', border: '#8957e5' };
      if (tag === 'OPTIMIZER') nodeColor = { background: '#238636', border: '#238636' };
      if (tag === 'BRIDGE') nodeColor = { background: '#d29922', border: '#d29922' };

      const isRoot = n.depth === 0;

      return {
        id: n.id || n.paper_id,
        label: (n.label || n.title || 'Unknown').substring(0, 40) + '...',
        title: `Title: ${n.title}\nYear: ${n.year}\nArXiv: ${n.arxiv_id}\nTag: ${tag || 'None'}`,
        color: nodeColor,
        size: isRoot ? 24 : 12,
        font: { 
          color: '#c9d1d9', 
          size: isRoot ? 14 : 11,
          strokeWidth: isRoot ? 2 : 0,
          strokeColor: '#0e1116'
        },
        borderWidth: isRoot ? 3 : 1,
        rawData: n
      };
    });

    const edges = (graphData.edges || []).map((e) => ({
      from: e.from || e.source,
      to: e.to || e.target,
      arrows: 'to',
      color: { color: '#30363d', opacity: 0.8 },
      width: 1,
      smooth: { type: 'continuous' },
      hoverWidth: 1.5
    }));

    const data = { nodes, edges };
    const options = {
      nodes: {
        shape: 'dot',
      },
      physics: {
        barnesHut: {
          gravitationalConstant: -1800,
          springLength: 120,
          springConstant: 0.04
        }
      },
      interaction: {
        hover: true,
        tooltipDelay: 150,
      }
    };

    networkRef.current = new Network(containerRef.current, data, options);

    networkRef.current.on('click', (params) => {
      if (params.nodes.length > 0 && onNodeClick) {
        const nodeId = params.nodes[0];
        const clickedNode = data.nodes.find(n => n.id === nodeId);
        if (clickedNode && clickedNode.rawData) {
          onNodeClick(clickedNode.rawData);
        }
      } else {
        if (onNodeClick) onNodeClick(null);
      }
    });

    return () => {
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, [graphData, onNodeClick]);

  return (
    <div className="graph-layout" style={{ flex: 1, position: 'relative', width: '100%', height: '100%' }}>
      <div className="graph-canvas-wrapper" style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }} ref={containerRef}></div>
      
      {(!graphData || !graphData.nodes || graphData.nodes.length === 0) && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: 'var(--text-secondary)' }}>
          No data mapped. Input ArXiv ID to render lineage.
        </div>
      )}

      {graphData && graphData.nodes && graphData.nodes.length > 0 && (
        <div className="graph-legend">
          <div className="legend-row">
            <div className="legend-dot" style={{ backgroundColor: 'var(--pioneer-color)' }}></div>
            Pioneer (New Paradigm)
          </div>
          <div className="legend-row">
            <div className="legend-dot" style={{ backgroundColor: 'var(--optimizer-color)' }}></div>
            Optimizer (Improvement)
          </div>
          <div className="legend-row">
            <div className="legend-dot" style={{ backgroundColor: 'var(--bridge-color)' }}></div>
            Bridge (Cross-Domain)
          </div>
          <div className="legend-row">
            <div className="legend-dot" style={{ backgroundColor: 'var(--accent-primary)' }}></div>
            Untagged Stub
          </div>
        </div>
      )}
    </div>
  );
}
