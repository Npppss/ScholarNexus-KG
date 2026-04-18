import { useEffect, useRef, useState } from 'react';
import { Network } from 'vis-network';

export default function GraphView({ graphData, onNodeClick, onExpandNode }) {
  const containerRef = useRef(null);
  const networkRef = useRef(null);
  const [activeFilter, setActiveFilter] = useState(null);

  useEffect(() => {
    if (!containerRef.current || !graphData || !graphData.nodes) return;

    const nodes = graphData.nodes.map((n) => {
      let nodeColor = { background: '#1f6feb', border: '#1f6feb' }; // Default / Stub node
      
      const tag = n.personality_tag?.toUpperCase();
      const isCognitiveMode = n.activation_energy !== undefined;

      if (isCognitiveMode) {
        // Activation energy heat gradient: cool blue → hot magenta
        const energy = n.activation_energy || 0;
        const r = Math.round(58 + energy * 200);
        const g = Math.round(100 * (1 - energy));
        const b = Math.round(200 + energy * 55);
        const color = `rgb(${Math.min(255,r)},${Math.max(0,g)},${Math.min(255,b)})`;
        nodeColor = { background: color, border: n.is_seed ? '#ffffff' : color };
      } else {
        if (tag === 'PIONEER') nodeColor = { background: '#8957e5', border: '#8957e5' };
        if (tag === 'OPTIMIZER') nodeColor = { background: '#238636', border: '#238636' };
        if (tag === 'BRIDGE') nodeColor = { background: '#d29922', border: '#d29922' };
      }

      const isRoot = n.depth === 0 || n.is_seed;
      const isUntagged = !tag;
      const dimmed = activeFilter && (
        (activeFilter === 'UNTAGGED' && !isUntagged) || 
        (activeFilter !== 'UNTAGGED' && tag !== activeFilter)
      ) && !isRoot;
      
      const nodeOpacity = dimmed ? 0.15 : 1.0;
      
      return {
        id: n.id || n.paper_id,
        label: (n.label || n.title || 'Unknown').substring(0, 40) + '...',
        title: isCognitiveMode
          ? `Title: ${n.title}\nYear: ${n.year}\nEnergy: ${(n.activation_energy || 0).toFixed(3)}\nSerendipity: ${(n.serendipity_score || 0).toFixed(3)}\nDepth: ${n.depth} hops`
          : `Title: ${n.title}\nYear: ${n.year}\nArXiv: ${n.arxiv_id}\nTag: ${tag || 'None'}`,
        color: { ...nodeColor, opacity: nodeOpacity },
        size: isRoot ? 24 : (isCognitiveMode ? 10 + Math.pow(n.activation_energy || 0, 0.5) * 20 : 12),
        shadow: (isCognitiveMode && (n.activation_energy || 0) > 0.2) ? {
          enabled: true,
          color: nodeColor.background,
          size: 15 * (n.activation_energy || 0.2),
          x: 0, y: 0
        } : false,
        font: { 
          color: dimmed ? '#30363d' : '#c9d1d9', 
          size: isRoot ? 14 : 11,
          strokeWidth: isRoot ? 2 : 0,
          strokeColor: '#0e1116'
        },
        borderWidth: isRoot ? 3 : (isCognitiveMode && n.activation_energy > 0.4 ? 2 : 1),
        rawData: n
      };
    });

    const edges = (graphData.edges || []).map((e) => {
      const isActivationFlow = e.rel_type === 'activation_flow';
      const isCitation = e.rel_type !== 'similar_to';
      
      if (isActivationFlow) {
        return {
          from: e.from || e.source,
          to: e.to || e.target,
          arrows: 'to',
          color: { color: '#ff61e6', opacity: 0.9 }, // Hot glow outline
          width: 2.5,
          dashes: [4, 4],
          smooth: { type: 'continuous' },
          shadow: { enabled: true, color: '#ff61e6', size: 10, x: 0, y: 0 }
        };
      }

      return {
        from: e.from || e.source,
        to: e.to || e.target,
        arrows: 'to',
        color: { 
          color: isCitation ? '#58a6ff' : '#f0883e',
          opacity: 0.7 
        },
        width: isCitation ? 1.5 : 1,
        dashes: isCitation ? false : [5, 5],
        smooth: { type: 'continuous' },
        hoverWidth: 1.5
      };
    });

    const data = { nodes, edges };
    const options = {
      nodes: {
        shape: 'dot',
      },
      physics: {
        barnesHut: {
          gravitationalConstant: -3500,
          springLength: 200,
          springConstant: 0.02,
          damping: 0.12
        },
        stabilization: {
          iterations: 200
        }
      },
      interaction: {
        hover: true,
        tooltipDelay: 150,
      }
    };

    networkRef.current = new Network(containerRef.current, data, options);

    // AI Adaptive Label Visibility
    networkRef.current.on('zoom', () => {
      const scale = networkRef.current.getScale();
      const visNodes = networkRef.current.body.data.nodes;
      
      const updates = [];
      visNodes.forEach((node) => {
        let fontSize = 11;
        const isRoot = node.rawData?.depth === 0 || node.rawData?.is_seed;
        
        // Lowered threshold so labels don't disappear too easily when auto-fitted
        if (scale < 0.3) {
          fontSize = 0;
        } else if (scale < 0.5) {
          fontSize = isRoot ? 14 : 0;
        } else {
          fontSize = isRoot ? 14 : 11;
        }
        
        const currentSize = node.font ? node.font.size : 11;
        if (currentSize !== fontSize) {
            updates.push({ id: node.id, font: { ...node.font, size: fontSize } });
        }
      });
      
      if (updates.length > 0) {
          visNodes.update(updates);
      }
    });

    networkRef.current.on('oncontext', (params) => {
      params.event.preventDefault();
      if (params.nodes.length > 0 && onExpandNode) {
        const nodeId = params.nodes[0];
        const clickedNode = data.nodes.find(n => n.id === nodeId);
        if (clickedNode && clickedNode.rawData && clickedNode.rawData.arxiv_id) {
          onExpandNode(clickedNode.rawData.arxiv_id);
        }
      }
    });

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
  }, [graphData, onNodeClick, activeFilter]);

  return (
    <div className="graph-layout" style={{ flex: 1, position: 'relative', width: '100%', height: '100%' }}>
      <div className="graph-canvas-wrapper" style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }} ref={containerRef}></div>
      
      {(!graphData || !graphData.nodes || graphData.nodes.length === 0) && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: 'var(--text-secondary)' }}>
          No data mapped. Input ArXiv ID to render lineage.
        </div>
      )}

      {graphData && graphData.nodes && graphData.nodes.length > 0 && (
        <div className="graph-legend" style={{ pointerEvents: 'auto' }}>
          <div 
            className="legend-row" 
            onClick={() => setActiveFilter(activeFilter === 'PIONEER' ? null : 'PIONEER')}
            style={{ cursor: 'pointer', opacity: activeFilter && activeFilter !== 'PIONEER' ? 0.4 : 1, transition: 'opacity 0.2s' }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--pioneer-color)' }}></div>
            Pioneer (New Paradigm)
          </div>
          <div 
            className="legend-row" 
            onClick={() => setActiveFilter(activeFilter === 'OPTIMIZER' ? null : 'OPTIMIZER')}
            style={{ cursor: 'pointer', opacity: activeFilter && activeFilter !== 'OPTIMIZER' ? 0.4 : 1, transition: 'opacity 0.2s' }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--optimizer-color)' }}></div>
            Optimizer (Improvement)
          </div>
          <div 
            className="legend-row" 
            onClick={() => setActiveFilter(activeFilter === 'BRIDGE' ? null : 'BRIDGE')}
            style={{ cursor: 'pointer', opacity: activeFilter && activeFilter !== 'BRIDGE' ? 0.4 : 1, transition: 'opacity 0.2s' }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--bridge-color)' }}></div>
            Bridge (Cross-Domain)
          </div>
          <div 
            className="legend-row" 
            onClick={() => setActiveFilter(activeFilter === 'UNTAGGED' ? null : 'UNTAGGED')}
            style={{ cursor: 'pointer', opacity: activeFilter && activeFilter !== 'UNTAGGED' ? 0.4 : 1, transition: 'opacity 0.2s' }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--accent-primary)' }}></div>
            Untagged Stub
          </div>
        </div>
      )}
    </div>
  );
}
