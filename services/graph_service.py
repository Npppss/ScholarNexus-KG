# services/graph_service.py
import uuid
import hashlib
from neo4j import GraphDatabase
from app.config.settings import settings

driver = GraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password)
)

# ─────────────────────────────────────────────────────────────────────────────
#  MERGE helpers — setiap fungsi mengembalikan node id yang di-upsert
# ─────────────────────────────────────────────────────────────────────────────

MERGE_PAPER = """
MERGE (p:Paper {paper_id: $paper_id})
SET
  p.title            = $title,
  p.abstract         = $abstract,
  p.year             = $year,
  p.venue            = $venue,
  p.arxiv_id         = $arxiv_id,
  p.doi              = $doi,
  p.personality_tag  = $personality_tag,
  p.confidence_score = $confidence_score,
  p.reasoning        = $reasoning,
  p.primary_category = $primary_category,
  p.embedding        = $embedding,
  p.unresolved       = $unresolved,
  p.updated_at       = datetime()
RETURN p.paper_id AS paper_id
"""

MERGE_AUTHOR = """
MERGE (a:Author {author_id: $author_id})
SET
  a.name        = $name,
  a.affiliation = $affiliation,
  a.updated_at  = datetime()
RETURN a.author_id AS author_id
"""

MERGE_METHOD = """
MERGE (m:Method {method_id: $method_id})
SET
  m.name        = $name,
  m.category    = $category,
  m.description = $description,
  m.updated_at  = datetime()
RETURN m.method_id AS method_id
"""

MERGE_DATASET = """
MERGE (d:Dataset {dataset_id: $dataset_id})
SET
  d.name       = $name,
  d.domain     = $domain,
  d.url        = $url,
  d.updated_at = datetime()
RETURN d.dataset_id AS dataset_id
"""

MERGE_TOPIC = """
MERGE (t:Topic {topic_id: $topic_id})
SET
  t.label           = $label,
  t.domain          = $domain,
  t.hierarchy_level = $hierarchy_level,
  t.updated_at      = datetime()
RETURN t.topic_id AS topic_id
"""

# Lanjutan services/graph_service.py

# ── Relasi Paper ↔ Author ─────────────────────────────────────────────────
MERGE_AUTHORED_BY = """
MATCH (p:Paper  {paper_id:  $paper_id})
MATCH (a:Author {author_id: $author_id})
MERGE (p)-[r:AUTHORED_BY]->(a)
SET r.author_order = $order,
    r.is_corresponding = $is_corresponding
"""

# ── Relasi Author ↔ Author (Co-authorship) ────────────────────────────────
MERGE_CO_AUTHORED = """
MATCH (a1:Author {author_id: $author_id_1})
MATCH (a2:Author {author_id: $author_id_2})
MERGE (a1)-[r:CO_AUTHORED_WITH]->(a2)
SET r.paper_count  = coalesce(r.paper_count, 0) + 1,
    r.first_paper  = coalesce(r.first_paper, $paper_id),
    r.updated_at   = datetime()
"""

# ── Relasi Paper → Paper (Citation) ──────────────────────────────────────
MERGE_CITES = """
MATCH (src:Paper {paper_id: $source_paper_id})
MATCH (tgt:Paper {paper_id: $target_paper_id})
MERGE (src)-[r:CITES]->(tgt)
SET r.citation_context  = $context,
    r.match_confidence  = $confidence,
    r.resolved_via      = $resolved_via,
    r.created_at        = coalesce(r.created_at, datetime())
"""

# ── Relasi Paper → Method ─────────────────────────────────────────────────
MERGE_USES_METHOD = """
MATCH (p:Paper  {paper_id:  $paper_id})
MATCH (m:Method {method_id: $method_id})
MERGE (p)-[r:USES_METHOD]->(m)
SET r.role        = $role,
    r.is_proposed = $is_proposed
"""

# ── Relasi Paper → Dataset ────────────────────────────────────────────────
MERGE_EVALUATED_ON = """
MATCH (p:Paper   {paper_id:   $paper_id})
MATCH (d:Dataset {dataset_id: $dataset_id})
MERGE (p)-[r:EVALUATED_ON]->(d)
SET r.metric      = $metric,
    r.score       = $score,
    r.split        = $split
"""

# ── Relasi Paper → Topic ──────────────────────────────────────────────────
MERGE_BELONGS_TO = """
MATCH (p:Paper {paper_id: $paper_id})
MATCH (t:Topic {topic_id: $topic_id})
MERGE (p)-[r:BELONGS_TO]->(t)
SET r.confidence_score = $confidence_score
"""

# ── Relasi Paper ↔ Paper (Semantic Similarity) ────────────────────────────
MERGE_SIMILAR_TO = """
MATCH (p1:Paper {paper_id: $paper_id_1})
MATCH (p2:Paper {paper_id: $paper_id_2})
MERGE (p1)-[r:SIMILAR_TO]->(p2)
SET r.similarity_score = $similarity_score,
    r.computed_at      = datetime()
"""

def upsert_paper_to_graph(
    extraction:    dict,
    embedding:     list[float],
    resolved_refs: list = None,
    arxiv_paper=None,
) -> dict:
    """
    Tulis satu paper lengkap ke Neo4j dalam satu transaksi atomik.
    Mengembalikan stats tentang berapa node/rel yang dibuat.
    """
    meta        = extraction.get("metadata", {})
    personality = extraction.get("personality", {})
    title       = extraction.get("title", "Unknown")

    # Generate deterministic paper_id dari judul + tahun
    paper_id = _make_paper_id(
        title  = title,
        year   = meta.get("year"),
        arxiv_id = arxiv_paper.arxiv_id if arxiv_paper else None
    )

    stats = {"nodes_created": 0, "rels_created": 0, "paper_id": paper_id}

    with driver.session() as session:

        # ── 1. Upsert :Paper node ─────────────────────────────────────────
        session.run(MERGE_PAPER, {
            "paper_id":         paper_id,
            "title":            title,
            "abstract":         meta.get("abstract", ""),
            "year":             _safe_int(meta.get("year")),
            "venue":            arxiv_paper.venue_parsed if arxiv_paper else meta.get("venue"),
            "arxiv_id":         arxiv_paper.arxiv_id if arxiv_paper else None,
            "doi":              arxiv_paper.doi if arxiv_paper else None,
            "personality_tag":  personality.get("personality_tag"),
            "confidence_score": personality.get("confidence_score", 0.0),
            "reasoning":        personality.get("reasoning", ""),
            "primary_category": arxiv_paper.primary_cat if arxiv_paper else None,
            "embedding":        embedding,
            "unresolved":       False,
        })
        stats["nodes_created"] += 1

        # ── 2. Upsert :Author nodes + AUTHORED_BY rels ───────────────────
        authors = arxiv_paper.authors if arxiv_paper else meta.get("authors", [])
        for idx, author_name in enumerate(authors):
            author_id = _make_id("author", author_name)
            session.run(MERGE_AUTHOR, {
                "author_id":   author_id,
                "name":        author_name,
                "affiliation": None,
            })
            session.run(MERGE_AUTHORED_BY, {
                "paper_id":         paper_id,
                "author_id":        author_id,
                "order":            idx + 1,
                "is_corresponding": (idx == 0),
            })
            stats["nodes_created"] += 1
            stats["rels_created"]  += 1

        # Co-authorship (semua pasangan penulis)
        for i in range(len(authors)):
            for j in range(i + 1, len(authors)):
                session.run(MERGE_CO_AUTHORED, {
                    "author_id_1": _make_id("author", authors[i]),
                    "author_id_2": _make_id("author", authors[j]),
                    "paper_id":    paper_id,
                })
                stats["rels_created"] += 1

        # ── 3. Upsert :Method nodes + USES_METHOD rels ───────────────────
        for method_name in meta.get("methods_proposed", []):
            method_id = _make_id("method", method_name)
            session.run(MERGE_METHOD, {
                "method_id":   method_id,
                "name":        method_name,
                "category":    "proposed",
                "description": "",
            })
            session.run(MERGE_USES_METHOD, {
                "paper_id":   paper_id,
                "method_id":  method_id,
                "role":       "proposed",
                "is_proposed": True,
            })

        for method_name in meta.get("methods_used_as_baseline", []):
            method_id = _make_id("method", method_name)
            session.run(MERGE_METHOD, {
                "method_id":   method_id,
                "name":        method_name,
                "category":    "baseline",
                "description": "",
            })
            session.run(MERGE_USES_METHOD, {
                "paper_id":   paper_id,
                "method_id":  method_id,
                "role":       "baseline",
                "is_proposed": False,
            })

        # ── 4. Upsert :Topic nodes + BELONGS_TO rels ─────────────────────
        for topic_label in meta.get("topics", []):
            topic_id = _make_id("topic", topic_label)
            session.run(MERGE_TOPIC, {
                "topic_id":        topic_id,
                "label":           topic_label,
                "domain":          _infer_domain(topic_label),
                "hierarchy_level": 1,
            })
            session.run(MERGE_BELONGS_TO, {
                "paper_id":         paper_id,
                "topic_id":         topic_id,
                "confidence_score": 0.9,
            })

        # ── 5. Upsert :CITES rels dari resolved references ────────────────
        if resolved_refs:
            for ref in resolved_refs:
                ref_paper_id = _make_paper_id(
                    title    = ref.title,
                    year     = ref.year,
                    arxiv_id = ref.arxiv_id,
                )
                # Buat node stub untuk paper yang direferensikan
                # (jika belum ada di graph)
                session.run(MERGE_PAPER, {
                    "paper_id":         ref_paper_id,
                    "title":            ref.title or ref.raw_text[:120],
                    "abstract":         "",
                    "year":             _safe_int(ref.year),
                    "venue":            None,
                    "arxiv_id":         ref.arxiv_id,
                    "doi":              ref.doi,
                    "personality_tag":  None,
                    "confidence_score": 0.0,
                    "reasoning":        "",
                    "primary_category": None,
                    "embedding":        None,   # akan diisi saat paper ini di-fetch
                    "unresolved":       not ref.found_on_arxiv,
                })
                session.run(MERGE_CITES, {
                    "source_paper_id": paper_id,
                    "target_paper_id": ref_paper_id,
                    "context":         ref.raw_text[:200],
                    "confidence":      1.0 if ref.found_on_arxiv else 0.6,
                    "resolved_via":    "arxiv" if ref.found_on_arxiv else "heuristic",
                })
                stats["rels_created"] += 1

    return stats


# ── Helpers ───────────────────────────────────────────────────────────────────
def _make_paper_id(title=None, year=None, arxiv_id=None) -> str:
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    seed = f"{(title or '').lower().strip()}:{year or ''}"
    return "paper:" + hashlib.md5(seed.encode()).hexdigest()[:12]

def _make_id(prefix: str, name: str) -> str:
    return f"{prefix}:" + hashlib.md5(name.lower().encode()).hexdigest()[:10]

def _safe_int(val) -> int | None:
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None

def _infer_domain(topic: str) -> str:
    NLP_KEYWORDS = {"language","nlp","text","translation","summarization","qa"}
    CV_KEYWORDS  = {"vision","image","detection","segmentation","object"}
    topic_lower  = topic.lower()
    if any(k in topic_lower for k in NLP_KEYWORDS):  return "NLP"
    if any(k in topic_lower for k in CV_KEYWORDS):   return "CV"
    return "General AI"

# services/graph_service.py (lanjutan)

class GraphService:

    # ── Research Lineage ─────────────────────────────────────────────────
    def get_research_lineage(
        self,
        arxiv_id:  str,
        direction: str = "ancestors",   # "ancestors" | "descendants" | "both"
        max_depth: int = 5,
    ) -> dict:
        """
        Kembalikan silsilah riset sebuah paper sebagai graph structure
        yang siap di-render oleh frontend (vis.js nodes + edges).
        """
        depth = min(max_depth, 6)  # hard cap mencegah query terlalu lambat

        with driver.session() as session:
            # ── 1. Selalu fetch root paper ─────────────────────────────────
            root_result = session.run(
                """
                MATCH (p:Paper {arxiv_id: $arxiv_id})
                RETURN p {
                    .paper_id, .title, .year, .arxiv_id,
                    .personality_tag, .confidence_score,
                    .primary_category
                } AS node
                """,
                arxiv_id=arxiv_id
            ).single()

            nodes = []
            if root_result:
                root_node = dict(root_result["node"])
                root_node["depth"] = 0
                root_node["id"] = root_node["paper_id"]
                root_node["label"] = root_node.get("title", arxiv_id)[:50]
                nodes.append(root_node)

            # ── 2. Fetch related nodes via CITES ──────────────────────────
            if direction in ("ancestors", "both"):
                query = f"""
                    MATCH path = (root:Paper {{arxiv_id: $arxiv_id}})
                                 -[:CITES*1..{depth}]->(ancestor:Paper)
                    WHERE ancestor.unresolved = false
                    WITH ancestor, length(path) AS d
                    RETURN ancestor {{
                        .paper_id, .title, .year, .arxiv_id,
                        .personality_tag, .confidence_score,
                        .primary_category, depth: d
                    }} AS node, d AS depth
                    ORDER BY d ASC, ancestor.year DESC
                    LIMIT 60
                """
                result = session.run(query, arxiv_id=arxiv_id)
                for r in result:
                    n = dict(r["node"])
                    n["id"] = n["paper_id"]
                    n["label"] = n.get("title", "?")[:50]
                    if not any(existing["paper_id"] == n["paper_id"] for existing in nodes):
                        nodes.append(n)

            if direction in ("descendants", "both"):
                query = f"""
                    MATCH path = (child:Paper)
                                 -[:CITES*1..{depth}]->(root:Paper {{arxiv_id: $arxiv_id}})
                    WHERE child.unresolved = false
                    AND child.paper_id <> root.paper_id
                    WITH child, length(path) AS d
                    RETURN child {{
                        .paper_id, .title, .year, .arxiv_id,
                        .personality_tag, .confidence_score,
                        .primary_category, depth: d
                    }} AS node, d AS depth
                    ORDER BY d ASC, child.year DESC
                    LIMIT 40
                """
                result = session.run(query, arxiv_id=arxiv_id)
                for r in result:
                    n = dict(r["node"])
                    n["id"] = n["paper_id"]
                    n["label"] = n.get("title", "?")[:50]
                    if not any(existing["paper_id"] == n["paper_id"] for existing in nodes):
                        nodes.append(n)

            # ── 3. Fetch edges ────────────────────────────────────────────
            node_ids = [n["paper_id"] for n in nodes]
            edges = self._get_edges_between(node_ids) if len(node_ids) > 1 else []

        # Format edges for vis.js (needs from/to instead of source/target)
        vis_edges = []
        for e in edges:
            vis_edges.append({
                "from": e["source"],
                "to":   e["target"],
                "label": "CITES",
                "arrows": "to",
            })

        return {
            "root":      arxiv_id,
            "direction": direction,
            "nodes":     nodes,
            "edges":     vis_edges,
            "depth":     depth,
        }

    def _get_edges_between(self, paper_ids: list[str]) -> list[dict]:
        """Ambil semua CITES edges di antara sekumpulan paper_ids."""
        query = """
            MATCH (src:Paper)-[r:CITES]->(tgt:Paper)
            WHERE src.paper_id IN $ids AND tgt.paper_id IN $ids
            RETURN
              src.paper_id       AS source,
              tgt.paper_id       AS target,
              r.match_confidence AS confidence,
              r.resolved_via     AS resolved_via
        """
        with driver.session() as session:
            result = session.run(query, ids=paper_ids)
            return [dict(r) for r in result]

    # ── Vector Similarity ─────────────────────────────────────────────────
    def find_similar_papers(
        self,
        source_paper_id: str,
        query_embedding: list[float],
        top_k:           int   = 10,
        min_score:       float = 0.75,
        materialize:     bool  = True,   # tulis SIMILAR_TO ke graph?
    ) -> list[dict]:
        """
        Cari paper paling mirip secara semantik + opsional tulis edge SIMILAR_TO.
        """
        query = """
            CALL db.index.vector.queryNodes(
              'paper_embedding_index', $top_k, $embedding
            )
            YIELD node AS paper, score
            WHERE paper.paper_id <> $source_id
              AND score > $min_score
            RETURN
              paper.paper_id        AS paper_id,
              paper.title           AS title,
              paper.arxiv_id        AS arxiv_id,
              paper.personality_tag AS personality,
              paper.year            AS year,
              round(score * 1000) / 1000 AS similarity
            ORDER BY score DESC
        """
        with driver.session() as session:
            result  = session.run(
                query,
                embedding  = query_embedding,
                top_k      = top_k,
                min_score  = min_score,
                source_id  = source_paper_id,
            )
            similar = [dict(r) for r in result]

            if materialize and similar:
                self._write_similar_to_edges(source_paper_id, similar)

        return similar

    def _write_similar_to_edges(
        self, source_id: str, similar_papers: list[dict]
    ) -> None:
        query = """
            UNWIND $papers AS sp
            MATCH (src:Paper {paper_id: $source_id})
            MATCH (tgt:Paper {paper_id: sp.paper_id})
            MERGE (src)-[r:SIMILAR_TO]->(tgt)
            SET r.similarity_score = sp.similarity,
                r.computed_at      = datetime()
        """
        with driver.session() as session:
            session.run(query, source_id=source_id, papers=similar_papers)

    # ── Analytics ─────────────────────────────────────────────────────────
    def get_graph_stats(self) -> dict:
        """Dashboard stats untuk monitoring Knowledge Graph."""
        import logging
        logger = logging.getLogger(__name__)

        query = """
            MATCH (p:Paper)
            WITH
              count(p)                                          AS total_papers,
              count(p.personality_tag)                          AS tagged_papers,
              count(CASE WHEN p.unresolved = true THEN 1 END)   AS stubs,
              count(CASE WHEN p.embedding IS NOT NULL THEN 1 END) AS embedded
            
            OPTIONAL MATCH ()-[r:CITES]->()
            WITH total_papers, tagged_papers, stubs, embedded, count(r) AS total_citations
            
            OPTIONAL MATCH ()-[s:SIMILAR_TO]->()
            RETURN
              total_papers, tagged_papers, stubs, embedded,
              total_citations,
              count(s) AS similarity_edges,
              CASE WHEN total_papers > 0 THEN round(toFloat(tagged_papers)/total_papers * 100) ELSE 0.0 END AS pct_tagged
        """
        try:
            with driver.session() as session:
                result = session.run(query)
                record = result.single()
                
                if record is None:
                    logger.warning("Neo4j graph stats query returned None. Graph may be totally empty or disconnected. Defaulting to zeroes.")
                    return {
                        "total_papers": 0,
                        "tagged_papers": 0,
                        "stubs": 0,
                        "embedded": 0,
                        "total_citations": 0,
                        "similarity_edges": 0,
                        "pct_tagged": 0.0
                    }
                return dict(record)
        except Exception as e:
            logger.error(f"Error fetching graph stats: {e}", exc_info=True)
            return {
                "total_papers": 0,
                "tagged_papers": 0,
                "stubs": 0,
                "embedded": 0,
                "total_citations": 0,
                "similarity_edges": 0,
                "pct_tagged": 0.0
            }

    def get_personality_distribution(self) -> list[dict]:
        query = """
            MATCH (p:Paper)
            WHERE p.personality_tag IS NOT NULL
            RETURN
              p.personality_tag        AS tag,
              count(p)                 AS count,
              avg(p.confidence_score)  AS avg_confidence,
              avg(p.year)              AS avg_year
            ORDER BY count DESC
        """
        with driver.session() as session:
            return [dict(r) for r in session.run(query)]


# Singleton
graph_service = GraphService()