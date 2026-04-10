// frontend/js/graph.js
import { getLineage, getSimilar } from './api.js';

const COLOR  = { PIONEER:'#7F77DD', OPTIMIZER:'#1D9E75', BRIDGE:'#BA7517' };
const STROKE = { PIONEER:'#534AB7', OPTIMIZER:'#0F6E56', BRIDGE:'#854F0B' };
const STUB_COLOR  = '#B4B2A9';
const STUB_STROKE = '#888780';

export class KGGraph {
  constructor(svgEl, onNodeSelect) {
    this.svg          = d3.select(svgEl);
    this.onNodeSelect = onNodeSelect;  // callback ke panels.js
    this.nodes        = [];
    this.links        = [];
    this.simulation   = null;
    this._activeFilter = 'ALL';
    this._setupSvg();
  }

  // ── Setup ────────────────────────────────────────────────────────────────
  _setupSvg() {
    const el  = this.svg.node();
    this.W    = el.clientWidth;
    this.H    = el.clientHeight;

    this.svg.attr('viewBox', `0 0 ${this.W} ${this.H}`);

    // Arrow markers
    const defs = this.svg.append('defs');
    this._addMarker(defs, 'arr-cites',   '#888780');
    this._addMarker(defs, 'arr-similar', '#EF9F27');

    // Zoom layer
    this.container = this.svg.append('g').attr('id', 'kg-container');
    this.linkG     = this.container.append('g').attr('id', 'kg-links');
    this.nodeG     = this.container.append('g').attr('id', 'kg-nodes');
    this.labelG    = this.container.append('g').attr('id', 'kg-labels');

    const zoom = d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', e => this.container.attr('transform', e.transform));
    this.svg.call(zoom);

    // Deselect on canvas click
    this.svg.on('click', () => {
      this._highlightNode(null);
      this.onNodeSelect(null);
    });
  }

  _addMarker(defs, id, color) {
    defs.append('marker')
      .attr('id', id).attr('viewBox', '0 0 10 10')
      .attr('refX', 20).attr('refY', 5)
      .attr('markerWidth', 5).attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M1 1L9 5L1 9')
      .attr('fill', 'none').attr('stroke', color)
      .attr('stroke-width', 1.5).attr('stroke-linecap', 'round');
  }

  // ── Load data dari API ────────────────────────────────────────────────────
  async loadLineage(arxivId, direction = 'ancestors', depth = 3) {
    const data = await getLineage(arxivId, direction, depth);
    this._ingestData(data.nodes, data.edges);
  }

  _ingestData(newNodes, newEdges) {
    // Merge dengan data yang sudah ada (untuk expand graph)
    const existingIds = new Set(this.nodes.map(n => n.paper_id));
    newNodes.forEach(n => {
      if (!existingIds.has(n.paper_id)) this.nodes.push(n);
    });
    const existingEdgeKeys = new Set(
      this.links.map(l => `${l.source?.paper_id||l.source}__${l.target?.paper_id||l.target}`)
    );
    newEdges.forEach(e => {
      const key = `${e.source}__${e.target}`;
      if (!existingEdgeKeys.has(key)) this.links.push(e);
    });
    this._render();
  }

  // ── Render ────────────────────────────────────────────────────────────────
  _render() {
    this._renderLinks();
    this._renderNodes();
    this._renderLabels();
    this._startSimulation();
  }

  _renderLinks() {
    this.linkG.selectAll('line')
      .data(this.links, d => `${d.source?.paper_id||d.source}__${d.target?.paper_id||d.target}`)
      .join(
        enter => enter.append('line')
          .attr('stroke', d => d.type === 'SIMILAR_TO' ? '#EF9F27' : '#B4B2A9')
          .attr('stroke-width', d => d.type === 'SIMILAR_TO' ? 1.2 : 0.8)
          .attr('stroke-dasharray', d => d.type === 'SIMILAR_TO' ? '5 3' : null)
          .attr('opacity', 0.55)
          .attr('marker-end', d =>
            d.type === 'SIMILAR_TO' ? 'url(#arr-similar)' : 'url(#arr-cites)'
          )
      );
  }

  _renderNodes() {
    const drag = d3.drag()
      .on('start', (e, d) => {
        if (!e.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => {
        if (!e.active) this.simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
      });

    this.nodeG.selectAll('circle')
      .data(this.nodes, d => d.paper_id)
      .join(
        enter => enter.append('circle')
          .attr('r', d => this._radius(d))
          .attr('fill',   d => COLOR[d.personality_tag]   || STUB_COLOR)
          .attr('stroke', d => STROKE[d.personality_tag]  || STUB_STROKE)
          .attr('stroke-width', d => d.personality_tag ? 1.5 : 0.8)
          .style('cursor', 'pointer')
          .call(drag)
          .on('click', (e, d) => {
            e.stopPropagation();
            this._highlightNode(d);
            this.onNodeSelect(d);
          })
      );
  }

  _renderLabels() {
    this.labelG.selectAll('text')
      .data(this.nodes.filter(n => n.personality_tag), d => d.paper_id)
      .join(
        enter => enter.append('text')
          .text(d => d.title.length > 30
            ? d.title.slice(0, 28) + '…'
            : d.title
          )
          .attr('font-size', '10px')
          .attr('fill', 'var(--color-text-secondary)')
          .attr('text-anchor', 'middle')
          .attr('pointer-events', 'none')
      );
  }

  _startSimulation() {
    if (this.simulation) this.simulation.stop();

    this.simulation = d3.forceSimulation(this.nodes)
      .force('link',    d3.forceLink(this.links)
                          .id(d => d.paper_id)
                          .distance(d => d.type === 'SIMILAR_TO' ? 160 : 100))
      .force('charge',  d3.forceManyBody().strength(-350))
      .force('center',  d3.forceCenter(this.W / 2, this.H / 2))
      .force('collide', d3.forceCollide(d => this._radius(d) + 10))
      .on('tick', () => this._ticked());
  }

  _ticked() {
    this.linkG.selectAll('line')
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    this.nodeG.selectAll('circle')
      .attr('cx', d => d.x).attr('cy', d => d.y);
    this.labelG.selectAll('text')
      .attr('x', d => d.x)
      .attr('y', d => d.y + this._radius(d) + 12);
  }

  // ── Interaksi ─────────────────────────────────────────────────────────────
  _highlightNode(selected) {
    if (!selected) {
      this.nodeG.selectAll('circle').attr('opacity', 1).attr('stroke-width', d => d.personality_tag ? 1.5 : 0.8);
      this.linkG.selectAll('line').attr('opacity', 0.55);
      return;
    }
    const connectedIds = new Set(
      this.links
        .filter(l =>
          (l.source.paper_id||l.source) === selected.paper_id ||
          (l.target.paper_id||l.target) === selected.paper_id
        )
        .flatMap(l => [l.source.paper_id||l.source, l.target.paper_id||l.target])
    );
    this.nodeG.selectAll('circle')
      .attr('opacity', d => (d.paper_id === selected.paper_id || connectedIds.has(d.paper_id)) ? 1 : 0.15)
      .attr('stroke-width', d => d.paper_id === selected.paper_id ? 3 : (d.personality_tag ? 1.5 : 0.8));
    this.linkG.selectAll('line')
      .attr('opacity', l =>
        (l.source.paper_id||l.source) === selected.paper_id ||
        (l.target.paper_id||l.target) === selected.paper_id ? 1 : 0.06
      );
  }

  // ── Filter & Search ───────────────────────────────────────────────────────
  setFilter(tag) {
    this._activeFilter = tag;
    this.nodeG.selectAll('circle')
      .attr('opacity', d => tag === 'ALL' ? 1 : (d.personality_tag === tag ? 1 : 0.12));
    this.labelG.selectAll('text')
      .attr('opacity', d => tag === 'ALL' ? 1 : (d.personality_tag === tag ? 1 : 0));
  }

  search(query) {
    if (!query) { this.nodeG.selectAll('circle').attr('opacity', 1); return; }
    const q = query.toLowerCase();
    this.nodeG.selectAll('circle')
      .attr('opacity', d =>
        d.title.toLowerCase().includes(q) ||
        (d.authors||[]).some(a => a.toLowerCase().includes(q)) ? 1 : 0.08
      );
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  _radius(d) {
    if (!d.personality_tag) return 7;
    return d.confidence_score > 0.9 ? 18 : 14;
  }

  clear() {
    this.nodes = []; this.links = [];
    this.linkG.selectAll('line').remove();
    this.nodeG.selectAll('circle').remove();
    this.labelG.selectAll('text').remove();
    if (this.simulation) this.simulation.stop();
  }
}