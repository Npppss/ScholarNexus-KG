import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Network } from 'vis-network';

// Hitung batas minimum zoom out dinamis berdasarkan jumlah node
function getDynamicMinScale(nodeCount) {
  if (nodeCount <= 12) return 0.70;
  if (nodeCount <= 30) return 0.50;
  if (nodeCount <= 60) return 0.38;
  if (nodeCount <= 120) return 0.28;
  if (nodeCount <= 250) return 0.20;
  return 0.15;
}

const MAX_SCALE = 2.4;

// Potong teks judul pada batas kata agar rapi dan tambahkan tahun jika muat
function formatNodeLabel(title, year, maxLen = 32) {
  const raw = (title || 'Untitled').trim();
  let shortened = raw;
  if (raw.length > maxLen) {
    const sliced = raw.slice(0, maxLen);
    const lastSpace = sliced.lastIndexOf(' ');
    shortened = (lastSpace > maxLen * 0.6 ? sliced.slice(0, lastSpace) : sliced) + '…';
  }
  if (year && Number(year) > 1900) {
    return `${shortened} (${year})`;
  }
  return shortened;
}

// Cari jalur terpendek antara focusId dan rootId menggunakan BFS
function findShortestPathToRoot(focusId, rootId, edges) {
  if (!focusId || !rootId || focusId === rootId) {
    return { pathNodes: new Set([focusId].filter(Boolean)), pathEdges: new Set() };
  }

  const adj = new Map();
  edges.forEach((e) => {
    const u = e.from || e.source;
    const v = e.to || e.target;
    const edgeId = `${u}__${v}__${e.rel_type || 'cites'}`;
    if (!adj.has(u)) adj.set(u, []);
    if (!adj.has(v)) adj.set(v, []);
    adj.get(u).push({ neighbor: v, edgeId });
    adj.get(v).push({ neighbor: u, edgeId });
  });

  const queue = [focusId];
  const visited = new Set([focusId]);
  const parentMap = new Map(); // node -> { prevNode, edgeId }

  while (queue.length > 0) {
    const curr = queue.shift();
    if (curr === rootId) break;
    const neighbors = adj.get(curr) || [];
    for (const { neighbor, edgeId } of neighbors) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        parentMap.set(neighbor, { prevNode: curr, edgeId });
        queue.push(neighbor);
      }
    }
  }

  const pathNodes = new Set([focusId]);
  const pathEdges = new Set();

  if (parentMap.has(rootId)) {
    let curr = rootId;
    while (curr && curr !== focusId) {
      pathNodes.add(curr);
      const step = parentMap.get(curr);
      if (step) {
        pathEdges.add(step.edgeId);
        curr = step.prevNode;
      } else {
        break;
      }
    }
    pathNodes.add(focusId);
  }

  return { pathNodes, pathEdges };
}

export default function GraphView({
  graphData,
  selectedNode,
  onNodeClick,
  onExpandNode,
  onSelectExample,
  layoutMode = 'physics',
  onLayoutModeChange,
  labelMode = 'adaptive',
}) {
  const containerRef = useRef(null);
  const networkRef = useRef(null);
  const isClampingRef = useRef(false);
  const graphDataRef = useRef(graphData);
  graphDataRef.current = graphData;

  const [activeFilter, setActiveFilter] = useState(null);
  const [hoveredNodeId, setHoveredNodeId] = useState(null);
  const [currentScale, setCurrentScale] = useState(0.75);

  const nodeCount = graphData?.nodes?.length || 0;
  const dynamicMinScale = getDynamicMinScale(nodeCount);
  const selectedNodeId = selectedNode ? (selectedNode.id || selectedNode.paper_id) : null;

  // Hitung distribusi peran untuk ditampilkan pada legenda
  const roleCounts = useMemo(() => {
    const counts = { PIONEER: 0, OPTIMIZER: 0, BRIDGE: 0, UNTAGGED: 0 };
    if (!graphData?.nodes) return counts;
    graphData.nodes.forEach((n) => {
      const t = n.personality_tag?.toUpperCase();
      if (t === 'PIONEER') counts.PIONEER += 1;
      else if (t === 'OPTIMIZER') counts.OPTIMIZER += 1;
      else if (t === 'BRIDGE') counts.BRIDGE += 1;
      else counts.UNTAGGED += 1;
    });
    return counts;
  }, [graphData]);

  // Hitung derajat koneksi, skor kepentingan (importance rank), dan himpunan sorotan jalur
  const graphMetrics = useMemo(() => {
    if (!graphData?.nodes) {
      return { degreeMap: {}, importanceRankMap: {}, rootNodeId: null };
    }

    const degreeMap = {};
    const inDegreeMap = {};
    graphData.nodes.forEach((n) => {
      const id = n.id || n.paper_id;
      degreeMap[id] = 0;
      inDegreeMap[id] = 0;
    });

    (graphData.edges || []).forEach((e) => {
      const u = e.from || e.source;
      const v = e.to || e.target;
      if (degreeMap[u] !== undefined) degreeMap[u] += 1;
      if (degreeMap[v] !== undefined) degreeMap[v] += 1;
      if (inDegreeMap[v] !== undefined) inDegreeMap[v] += 1;
    });

    let rootNodeId = null;
    const scoredNodes = graphData.nodes.map((n) => {
      const id = n.id || n.paper_id;
      const isRoot = n.depth === 0 || n.is_seed;
      if (isRoot && !rootNodeId) rootNodeId = id;

      const deg = degreeMap[id] || 0;
      const inDeg = inDegreeMap[id] || 0;
      const globalCit = Number(n.citation_count || 0);
      const tag = n.personality_tag?.toUpperCase();
      const tagBonus = tag === 'PIONEER' ? 35 : tag ? 25 : 0;
      const energyBonus = (n.activation_energy || 0) * 60;

      const score =
        (isRoot ? 1000 : 0) +
        deg * 18 +
        inDeg * 12 +
        Math.min(120, globalCit * 4) +
        tagBonus +
        energyBonus;

      return { id, score };
    });

    scoredNodes.sort((a, b) => b.score - a.score);
    const importanceRankMap = {};
    scoredNodes.forEach((item, idx) => {
      importanceRankMap[item.id] = idx;
    });

    return { degreeMap, inDegreeMap, importanceRankMap, rootNodeId };
  }, [graphData]);

  // Kunci topologi: hanya re-inisialisasi vis-network jika himpunan ID node/edge atau layoutMode berubah
  const topologyKey = useMemo(() => {
    if (!graphData || !graphData.nodes || graphData.nodes.length === 0) return 'empty';
    const nIds = graphData.nodes.map((n) => n.id || n.paper_id).sort().join(',');
    const eIds = (graphData.edges || [])
      .map((e) => `${e.from || e.source}->${e.to || e.target}`)
      .sort()
      .join(',');
    return `${layoutMode}::${nIds}::${eIds}`;
  }, [graphData, layoutMode]);

  // Fungsi pembangun gaya visual node & edge (mendukung pembaruan in-place)
  const computeVisualElements = useCallback(
    (includePositions = false) => {
      if (!graphData || !graphData.nodes) return { nodes: [], edges: [], distinctYears: [], yearXPositions: {} };

      const { degreeMap, importanceRankMap, rootNodeId } = graphMetrics;
      const focusId = selectedNodeId || hoveredNodeId;

      // Hitung himpunan sorotan jalur (spotlight) bila ada simpul yang dipilih atau di-hover
      const spotlightNodes = new Set();
      const spotlightEdges = new Set();

      if (focusId) {
        spotlightNodes.add(focusId);
        (graphData.edges || []).forEach((e) => {
          const u = e.from || e.source;
          const v = e.to || e.target;
          const edgeId = `${u}__${v}__${e.rel_type || 'cites'}`;
          if (u === focusId || v === focusId) {
            spotlightNodes.add(u);
            spotlightNodes.add(v);
            spotlightEdges.add(edgeId);
          }
        });

        // Tambahkan jalur silsilah terpendek menuju simpul akar (root)
        if (rootNodeId && focusId !== rootNodeId) {
          const { pathNodes, pathEdges } = findShortestPathToRoot(focusId, rootNodeId, graphData.edges || []);
          pathNodes.forEach((nid) => spotlightNodes.add(nid));
          pathEdges.forEach((eid) => spotlightEdges.add(eid));
        }
      }

      // Persiapan koordinat kronologis bila diperlukan
      const validYears = graphData.nodes
        .map((n) => Number(n.year))
        .filter((y) => !isNaN(y) && y > 1900);
      const distinctYears = [...new Set(validYears)].sort((a, b) => a - b);
      const fallbackYear = distinctYears[0] || 2020;

      const yearXPositions = {};
      let currentX = 0;
      distinctYears.forEach((yr, idx) => {
        if (idx === 0) {
          yearXPositions[yr] = 0;
        } else {
          const prevYr = distinctYears[idx - 1];
          const gapYears = yr - prevYr;
          const spacing = 320 + Math.min(100, (gapYears - 1) * 25);
          currentX += spacing;
          yearXPositions[yr] = currentX;
        }
      });

      const nodesByYear = {};
      if (includePositions && layoutMode === 'chronological') {
        graphData.nodes.forEach((n) => {
          const y = Number(n.year) && n.year > 1900 ? Number(n.year) : fallbackYear;
          if (!nodesByYear[y]) nodesByYear[y] = [];
          nodesByYear[y].push(n);
        });
      }

      const styledNodes = graphData.nodes.map((n) => {
        const id = n.id || n.paper_id;
        const tag = n.personality_tag?.toUpperCase();
        const isCognitiveMode = n.activation_energy !== undefined;
        const isRoot = n.depth === 0 || n.is_seed;
        const isSelected = id === selectedNodeId;
        const isHovered = id === hoveredNodeId;
        const isFocused = isSelected || isHovered;
        const deg = degreeMap[id] || 0;
        const rank = importanceRankMap[id] ?? 999;

        let baseBg = '#1f6feb';
        let baseBorder = '#388bfd';

        if (isCognitiveMode) {
          const energy = n.activation_energy || 0;
          const r = Math.round(58 + energy * 200);
          const g = Math.round(100 * (1 - energy));
          const b = Math.round(200 + energy * 55);
          baseBg = `rgb(${Math.min(255, r)},${Math.max(0, g)},${Math.min(255, b)})`;
          baseBorder = isRoot ? '#ffffff' : baseBg;
        } else {
          if (tag === 'PIONEER') {
            baseBg = '#8957e5';
            baseBorder = '#a371f7';
          } else if (tag === 'OPTIMIZER') {
            baseBg = '#238636';
            baseBorder = '#3fb950';
          } else if (tag === 'BRIDGE') {
            baseBg = '#d29922';
            baseBorder = '#e3b341';
          }
        }

        // Evaluasi redup (dimming) dari filter legenda atau sorotan jalur (spotlight)
        const isUntagged = !tag;
        const dimmedByLegend =
          activeFilter &&
          ((activeFilter === 'UNTAGGED' && !isUntagged) ||
            (activeFilter !== 'UNTAGGED' && tag !== activeFilter)) &&
          !isRoot;

        const dimmedBySpotlight = focusId ? !spotlightNodes.has(id) : false;
        const isDimmed = dimmedByLegend || dimmedBySpotlight;

        const nodeOpacity = isDimmed ? 0.14 : 1.0;

        // Ukuran simpul proporsional berdasarkan peran dan derajat kepentingan
        let nodeSize = 13;
        if (isRoot) {
          nodeSize = 26;
        } else if (isSelected) {
          nodeSize = 21;
        } else if (isCognitiveMode) {
          nodeSize = 12 + Math.pow(n.activation_energy || 0, 0.5) * 20;
        } else {
          const citBonus = Math.min(5, Math.floor(Number(n.citation_count || 0) / 2));
          const degBonus = Math.min(5, Math.floor(deg / 2));
          nodeSize = (deg <= 1 && isUntagged ? 11.5 : 14) + Math.max(citBonus, degBonus);
        }

        // Logika Label Adaptif (Level of Detail berdasarkan Zoom & Kepentingan)
        let showLabel = false;
        if (isDimmed) {
          showLabel = false;
        } else if (focusId && spotlightNodes.has(id)) {
          // Saat sorotan aktif, seluruh simpul pada jalur sorotan menampilkan label dengan jelas
          showLabel = true;
        } else if (labelMode === 'all') {
          showLabel = currentScale >= 0.35 || rank < 15;
        } else if (labelMode === 'core') {
          showLabel = isRoot || isFocused || rank < 7;
        } else {
          // Mode 'adaptive' (Default)
          if (currentScale < 0.48) {
            showLabel = isRoot || isFocused || rank < 5;
          } else if (currentScale < 0.78) {
            showLabel = isRoot || isFocused || rank < 11 || deg >= 3;
          } else if (currentScale < 1.1) {
            showLabel = isRoot || isFocused || rank < 22 || Boolean(tag) || deg >= 2;
          } else {
            showLabel = true;
          }
        }

        const labelMaxLen = isRoot || isFocused ? 44 : currentScale >= 0.9 ? 36 : 28;
        const displayLabel = showLabel ? formatNodeLabel(n.title || n.label, n.year, labelMaxLen) : '';
        const fontSize = !showLabel ? 0 : isRoot || isSelected ? 13.5 : isHovered || rank < 6 ? 12 : 11;

        let positioning = {};
        if (includePositions && layoutMode === 'chronological') {
          const nodeYear = Number(n.year) && n.year > 1900 ? Number(n.year) : fallbackYear;
          const yearGroup = nodesByYear[nodeYear] || [n];
          const idxInYear = yearGroup.findIndex((item) => (item.id || item.paper_id) === id);
          const countInYear = yearGroup.length;
          const baseX = yearXPositions[nodeYear] ?? 0;

          let xPos = baseX;
          let yPos = 0;
          if (countInYear > 5) {
            const col = idxInYear % 2;
            const row = Math.floor(idxInYear / 2);
            const totalRows = Math.ceil(countInYear / 2);
            xPos = baseX + (col === 0 ? -42 : 42);
            yPos = (row - (totalRows - 1) / 2) * 72;
          } else {
            xPos = baseX;
            yPos = (idxInYear - (countInYear - 1) / 2) * 84;
          }

          positioning = {
            x: xPos,
            y: yPos,
            fixed: { x: true, y: false },
          };
        }

        return {
          id,
          label: displayLabel,
          title: isCognitiveMode
            ? `Judul: ${n.title}\nTahun: ${n.year || 'N/A'}\nEnergi Aktivasi: ${(n.activation_energy || 0).toFixed(3)}\nSkor Serendipity: ${(n.serendipity_score || 0).toFixed(3)}\nKedalaman: ${n.depth} hop`
            : `Judul: ${n.title}\nTahun: ${n.year || 'N/A'}\nPeran: ${tag || 'Belum Diklasifikasi'}\nKoneksi Graf: ${deg} relasi | Sitasi: ${n.citation_count || 0}`,
          color: {
            background: baseBg,
            border: isFocused || isRoot ? '#ffffff' : baseBorder,
            opacity: nodeOpacity,
            highlight: { background: baseBg, border: '#ffffff' },
            hover: { background: baseBg, border: '#ffffff' },
          },
          size: nodeSize,
          shadow:
            isFocused || isRoot
              ? {
                  enabled: true,
                  color: isSelected ? 'rgba(88, 166, 255, 0.75)' : 'rgba(255, 255, 255, 0.45)',
                  size: isSelected ? 18 : 12,
                  x: 0,
                  y: 0,
                }
              : isCognitiveMode && (n.activation_energy || 0) > 0.2
              ? {
                  enabled: true,
                  color: baseBg,
                  size: 15 * (n.activation_energy || 0.2),
                  x: 0,
                  y: 0,
                }
              : false,
          font: {
            color: isDimmed ? 'rgba(139, 148, 158, 0.15)' : isFocused || isRoot ? '#ffffff' : '#e6edf3',
            size: fontSize,
            strokeWidth: showLabel ? 3.5 : 0,
            strokeColor: '#0d1117',
          },
          borderWidth: isSelected ? 3.5 : isRoot ? 3 : isHovered ? 2.5 : 1.5,
          ...positioning,
          rawData: n,
        };
      });

      const styledEdges = (graphData.edges || []).map((e) => {
        const u = e.from || e.source;
        const v = e.to || e.target;
        const edgeId = `${u}__${v}__${e.rel_type || 'cites'}`;
        const isActivationFlow = e.rel_type === 'activation_flow';
        const isCitation = e.rel_type !== 'similar_to';

        const isHighlightedEdge = focusId ? spotlightEdges.has(edgeId) : false;
        const isDimmedEdge = focusId ? !isHighlightedEdge : false;

        const smoothConfig =
          layoutMode === 'chronological'
            ? {
                type: 'cubicBezier',
                forceDirection: 'horizontal',
                roundness: 0.35,
              }
            : { type: 'continuous' };

        if (isActivationFlow) {
          return {
            id: edgeId,
            from: u,
            to: v,
            arrows: 'to',
            color: {
              color: '#ff61e6',
              opacity: isDimmedEdge ? 0.08 : 0.92,
            },
            width: isHighlightedEdge ? 3.2 : 2.2,
            dashes: [4, 4],
            smooth: smoothConfig,
          };
        }

        // Bedakan warna sorotan untuk sitasi keluar (Mengutip) vs masuk (Dikutip Oleh)
        let edgeColor = isCitation ? '#58a6ff' : '#f0883e';
        if (isHighlightedEdge && focusId) {
          if (u === focusId) edgeColor = '#58a6ff'; // Dokumen ini mengutip target
          else if (v === focusId) edgeColor = '#3fb950'; // Dokumen ini dikutip oleh source
          else edgeColor = '#a371f7'; // Jalur penghubung ke root
        }

        return {
          id: edgeId,
          from: u,
          to: v,
          arrows: 'to',
          color: {
            color: edgeColor,
            opacity: isDimmedEdge ? 0.06 : isHighlightedEdge ? 0.95 : 0.48,
          },
          width: isHighlightedEdge ? 2.6 : isDimmedEdge ? 1.0 : isCitation ? 1.4 : 1.1,
          dashes: isCitation ? false : [5, 5],
          smooth: smoothConfig,
        };
      });

      return { nodes: styledNodes, edges: styledEdges, distinctYears, yearXPositions };
    },
    [graphData, graphMetrics, selectedNodeId, hoveredNodeId, activeFilter, labelMode, currentScale, layoutMode]
  );

  // Zoom control handlers
  const handleZoomIn = useCallback(() => {
    if (!networkRef.current) return;
    const scale = networkRef.current.getScale();
    const newScale = Math.min(MAX_SCALE, scale * 1.3);
    networkRef.current.moveTo({
      scale: newScale,
      animation: { duration: 220, easingFunction: 'easeInOutQuad' },
    });
    setCurrentScale(newScale);
  }, []);

  const handleZoomOut = useCallback(() => {
    if (!networkRef.current) return;
    const scale = networkRef.current.getScale();
    const newScale = Math.max(dynamicMinScale, scale / 1.3);
    networkRef.current.moveTo({
      scale: newScale,
      animation: { duration: 220, easingFunction: 'easeInOutQuad' },
    });
    setCurrentScale(newScale);
  }, [dynamicMinScale]);

  const handleFitCenter = useCallback(() => {
    if (!networkRef.current) return;
    networkRef.current.fit({
      animation: { duration: 350, easingFunction: 'easeInOutQuad' },
    });
    setTimeout(() => {
      if (!networkRef.current) return;
      const scale = networkRef.current.getScale();
      const effectiveScale = Math.max(dynamicMinScale, Math.min(MAX_SCALE, scale));
      const pos = networkRef.current.getViewPosition();
      const xOffset = layoutMode === 'chronological' ? -60 : 0;
      networkRef.current.moveTo({
        position: { x: pos.x + xOffset, y: pos.y },
        scale: effectiveScale,
        animation: { duration: 220, easingFunction: 'easeInOutQuad' },
      });
      setCurrentScale(effectiveScale);
    }, 380);
  }, [dynamicMinScale, layoutMode]);

  // 1. Efek Inisialisasi Jaringan (hanya jalan ketika topologi atau mode tata letak berubah)
  useEffect(() => {
    if (!containerRef.current || !graphData || !graphData.nodes || graphData.nodes.length === 0) {
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
      return;
    }

    const { nodes, edges, distinctYears, yearXPositions } = computeVisualElements(true);
    const data = { nodes, edges };

    const options = {
      nodes: {
        shape: 'dot',
      },
      physics:
        layoutMode === 'chronological'
          ? {
              solver: 'barnesHut',
              barnesHut: {
                gravitationalConstant: -1500,
                centralGravity: 0.02,
                springLength: 80,
                springConstant: 0.015,
                damping: 0.38,
                avoidOverlap: 0.85,
              },
              stabilization: {
                iterations: 90,
              },
            }
          : {
              barnesHut: {
                gravitationalConstant: -3200,
                centralGravity: 0.18,
                springLength: 155,
                springConstant: 0.025,
                damping: 0.22,
                avoidOverlap: 0.65,
              },
              stabilization: {
                iterations: 150,
              },
            },
      interaction: {
        hover: true,
        tooltipDelay: 120,
        zoomView: true,
        hideEdgesOnDrag: false,
      },
    };

    const network = new Network(containerRef.current, data, options);
    networkRef.current = network;

    // Render Garis Panduan Kolom & Lencana Tahun pada Kanvas (Garis Waktu)
    network.on('beforeDrawing', (ctx) => {
      if (layoutMode !== 'chronological' || distinctYears.length === 0) return;

      ctx.save();
      const positions = network.getPositions();
      const yValues = Object.values(positions)
        .map((p) => p?.y)
        .filter((y) => y !== undefined);
      const minY = yValues.length > 0 ? Math.min(...yValues) : -250;
      const maxY = yValues.length > 0 ? Math.max(...yValues) : 250;
      const topY = minY - 85;
      const bottomY = maxY + 85;

      distinctYears.forEach((year) => {
        const x = yearXPositions[year];
        if (x === undefined) return;

        ctx.beginPath();
        ctx.setLineDash([5, 6]);
        ctx.strokeStyle = 'rgba(88, 166, 255, 0.16)';
        ctx.lineWidth = 1.5;
        ctx.moveTo(x, topY);
        ctx.lineTo(x, bottomY);
        ctx.stroke();
        ctx.setLineDash([]);

        const yearText = `${year}`;
        ctx.font = 'bold 12px ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace';
        const textMetrics = ctx.measureText(yearText);
        const pillW = textMetrics.width + 20;
        const pillH = 24;
        const pillX = x - pillW / 2;
        const pillY = topY - 14;

        ctx.fillStyle = 'rgba(13, 17, 23, 0.92)';
        ctx.strokeStyle = 'rgba(88, 166, 255, 0.45)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(pillX, pillY, pillW, pillH, 5);
        } else {
          ctx.rect(pillX, pillY, pillW, pillH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#79c0ff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(yearText, x, pillY + pillH / 2);
      });

      ctx.restore();
    });

    network.once('stabilizationIterationsDone', () => {
      network.fit({
        animation: { duration: 400, easingFunction: 'easeInOutQuad' },
      });
      setTimeout(() => {
        if (!networkRef.current) return;
        const scale = networkRef.current.getScale();
        const effectiveScale = Math.max(dynamicMinScale, Math.min(MAX_SCALE, scale));
        const pos = networkRef.current.getViewPosition();
        const xOffset = layoutMode === 'chronological' ? -60 : 0;
        networkRef.current.moveTo({
          position: { x: pos.x + xOffset, y: pos.y },
          scale: effectiveScale,
          animation: { duration: 250, easingFunction: 'easeInOutQuad' },
        });
        setCurrentScale(effectiveScale);
      }, 420);
    });

    network.on('zoom', () => {
      if (isClampingRef.current) return;
      const scale = network.getScale();

      if (scale < dynamicMinScale) {
        isClampingRef.current = true;
        network.moveTo({ scale: dynamicMinScale });
        isClampingRef.current = false;
      } else if (scale > MAX_SCALE) {
        isClampingRef.current = true;
        network.moveTo({ scale: MAX_SCALE });
        isClampingRef.current = false;
      }

      const clamped = Math.max(dynamicMinScale, Math.min(MAX_SCALE, scale));
      setCurrentScale((prev) => (Math.abs(prev - clamped) > 0.04 ? clamped : prev));
    });

    network.on('hoverNode', (params) => {
      if (params.node) {
        setHoveredNodeId(params.node);
      }
    });

    network.on('blurNode', () => {
      setHoveredNodeId(null);
    });

    network.on('oncontext', (params) => {
      params.event.preventDefault();
      if (params.nodes.length > 0 && onExpandNode) {
        const nodeId = params.nodes[0];
        const latestNodes = graphDataRef.current?.nodes || [];
        const clicked = latestNodes.find((n) => (n.id || n.paper_id) === nodeId);
        if (clicked && (clicked.arxiv_id || clicked.paper_id)) {
          onExpandNode(clicked.arxiv_id || clicked.paper_id);
        }
      }
    });

    network.on('click', (params) => {
      if (params.nodes.length > 0 && onNodeClick) {
        const nodeId = params.nodes[0];
        const latestNodes = graphDataRef.current?.nodes || [];
        const clicked = latestNodes.find((n) => (n.id || n.paper_id) === nodeId);
        if (clicked) {
          onNodeClick(clicked);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topologyKey, dynamicMinScale]);

  // 2. Efek Pembaruan Visual In-Place (tanpa mereset posisi fisika atau kamera)
  useEffect(() => {
    const network = networkRef.current;
    if (!network || !graphData || !graphData.nodes || graphData.nodes.length === 0) return;

    const { nodes, edges } = computeVisualElements(false);
    try {
      network.body.data.nodes.update(nodes);
      network.body.data.edges.update(edges);
    } catch (e) {
      // Abaikan apabila jaringan sedang dalam transisi inisialisasi
    }
  }, [computeVisualElements, graphData]);

  return (
    <div className="graph-canvas-wrapper" style={{ flex: 1, position: 'relative', width: '100%', height: '100%' }}>
      <div
        className="vis-container"
        style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}
        ref={containerRef}
      ></div>

      {/* ── Floating Zoom Navigation Controls ─────────────────────────────── */}
      {graphData && graphData.nodes && graphData.nodes.length > 0 && (
        <>
          <div className="graph-zoom-controls">
            <button className="zoom-btn" onClick={handleZoomIn} title="Perbesar Tampilan">
              +
            </button>
            <button className="zoom-btn" onClick={handleZoomOut} title="Perkecil Tampilan">
              &minus;
            </button>
            <button className="zoom-btn reset-btn" onClick={handleFitCenter} title="Pusatkan Graf">
              Fit
            </button>
          </div>

          {/* Indikator Mode Sorotan Jalur saat ada simpul terpilih */}
          {(selectedNodeId || activeFilter) && (
            <div className="spotlight-active-banner">
              <span>
                {selectedNodeId
                  ? 'Menyorot jalur sitasi dokumen terpilih'
                  : `Filter peran aktif: ${activeFilter}`}
              </span>
              <button
                className="spotlight-reset-btn"
                onClick={() => {
                  if (selectedNodeId && onNodeClick) onNodeClick(null);
                  if (activeFilter) setActiveFilter(null);
                }}
              >
                Tampilkan Semua
              </button>
            </div>
          )}
        </>
      )}

      {(!graphData || !graphData.nodes || graphData.nodes.length === 0) && (
        <div className="graph-empty-state">
          <div className="empty-state-badge">ScholarNexus Knowledge Graph</div>
          <h2 className="empty-state-title">Mulai Eksplorasi Silsilah Riset</h2>
          <p className="empty-state-subtitle">
            Pilih naskah terobosan di bawah ini untuk melihat pohon silsilah penemuan secara visual,
            atau cari topik penelitian melalui bilah pencarian di sebelah kiri.
          </p>

          <div className="example-cards-grid">
            <div
              className="example-paper-card"
              onClick={() => onSelectExample?.('1706.03762', 'Attention Is All You Need')}
            >
              <div className="example-card-head">
                <span className="example-badge pioneer-badge">PIONEER</span>
                <span className="example-year">2017</span>
              </div>
              <div className="example-card-title">Attention Is All You Need</div>
              <div className="example-card-meta">Vaswani et al. · Arsitektur Transformer</div>
              <div className="example-card-action">Jelajahi Silsilah &rarr;</div>
            </div>

            <div
              className="example-paper-card"
              onClick={() => onSelectExample?.('1512.03385', 'Deep Residual Learning for Image Recognition')}
            >
              <div className="example-card-head">
                <span className="example-badge optimizer-badge">OPTIMIZER</span>
                <span className="example-year">2015</span>
              </div>
              <div className="example-card-title">Deep Residual Learning for Image Recognition</div>
              <div className="example-card-meta">He et al. · ResNet &amp; Skip Connection</div>
              <div className="example-card-action">Jelajahi Silsilah &rarr;</div>
            </div>

            <div
              className="example-paper-card"
              onClick={() => onSelectExample?.('1810.04805', 'BERT: Pre-training of Deep Bidirectional Transformers')}
            >
              <div className="example-card-head">
                <span className="example-badge bridge-badge">BRIDGE</span>
                <span className="example-year">2018</span>
              </div>
              <div className="example-card-title">BERT: Pre-training of Deep Bidirectional Transformers</div>
              <div className="example-card-meta">Devlin et al. · Masked Language Model</div>
              <div className="example-card-action">Jelajahi Silsilah &rarr;</div>
            </div>
          </div>
        </div>
      )}

      {graphData && graphData.nodes && graphData.nodes.length > 0 && (
        <div className="graph-legend" style={{ pointerEvents: 'auto' }}>
          <div className="legend-header">PERAN ILMIAH (KLIK FILTER)</div>
          <div
            className="legend-row"
            onClick={() => setActiveFilter(activeFilter === 'PIONEER' ? null : 'PIONEER')}
            title="Pelopor: Memperkenalkan arsitektur, paradigma, atau formulasi masalah orisinal"
            style={{
              cursor: 'pointer',
              opacity: activeFilter && activeFilter !== 'PIONEER' ? 0.4 : 1,
              transition: 'opacity 0.2s',
            }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--pioneer-color)' }}></div>
            <span className="legend-name">Pioneer</span>
            <span className="legend-count">{roleCounts.PIONEER}</span>
          </div>
          <div
            className="legend-row"
            onClick={() => setActiveFilter(activeFilter === 'OPTIMIZER' ? null : 'OPTIMIZER')}
            title="Pengoptimal: Meningkatkan efisiensi, akurasi, atau skalabilitas metode yang ada"
            style={{
              cursor: 'pointer',
              opacity: activeFilter && activeFilter !== 'OPTIMIZER' ? 0.4 : 1,
              transition: 'opacity 0.2s',
            }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--optimizer-color)' }}></div>
            <span className="legend-name">Optimizer</span>
            <span className="legend-count">{roleCounts.OPTIMIZER}</span>
          </div>
          <div
            className="legend-row"
            onClick={() => setActiveFilter(activeFilter === 'BRIDGE' ? null : 'BRIDGE')}
            title="Penghubung: Menjembatani dua domain riset atau mengadaptasi metode lintas-bidang"
            style={{
              cursor: 'pointer',
              opacity: activeFilter && activeFilter !== 'BRIDGE' ? 0.4 : 1,
              transition: 'opacity 0.2s',
            }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--bridge-color)' }}></div>
            <span className="legend-name">Bridge</span>
            <span className="legend-count">{roleCounts.BRIDGE}</span>
          </div>
          <div
            className="legend-row"
            onClick={() => setActiveFilter(activeFilter === 'UNTAGGED' ? null : 'UNTAGGED')}
            title="Simpul referensi yang menunggu giliran klasifikasi otomatis"
            style={{
              cursor: 'pointer',
              opacity: activeFilter && activeFilter !== 'UNTAGGED' ? 0.4 : 1,
              transition: 'opacity 0.2s',
            }}
          >
            <div className="legend-dot" style={{ backgroundColor: 'var(--accent-primary)' }}></div>
            <span className="legend-name">Belum Diklasifikasi</span>
            <span className="legend-count">{roleCounts.UNTAGGED}</span>
          </div>
        </div>
      )}
    </div>
  );
}
