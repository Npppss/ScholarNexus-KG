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
  p.title            = coalesce(nullif($title, ''), p.title),
  p.abstract         = coalesce(nullif($abstract, ''), p.abstract),
  p.year             = coalesce($year, p.year),
  p.venue            = coalesce($venue, p.venue),
  p.arxiv_id         = coalesce($arxiv_id, p.arxiv_id),
  p.doi              = coalesce($doi, p.doi),
  p.personality_tag  = coalesce($personality_tag, p.personality_tag),
  p.confidence_score = CASE WHEN $confidence_score > 0 THEN $confidence_score ELSE coalesce(p.confidence_score, 0.0) END,
  p.reasoning        = coalesce(nullif($reasoning, ''), p.reasoning),
  p.primary_category = coalesce($primary_category, p.primary_category),
  p.embedding        = coalesce($embedding, p.embedding),
  p.unresolved       = coalesce($unresolved, p.unresolved),
  p.authors_text     = CASE WHEN $authors_text IS NOT NULL AND trim($authors_text) <> '' THEN $authors_text ELSE p.authors_text END,
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

    # Convert authors to text for fast frontend retrieval
    authors_list = [a.get("name", "") if isinstance(a, dict) else a for a in meta.get("authors", [])]
    if not authors_list and arxiv_paper and arxiv_paper.authors:
        authors_list = arxiv_paper.authors
    authors_text = ", ".join(filter(None, authors_list))

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
            "authors_text":     authors_text
        })
        stats["nodes_created"] += 1

        # ── 1b. TL;DR + evidence (dari LLM pipeline) ─────────────────────
        session.run(
            """
            MATCH (p:Paper {paper_id: $paper_id})
            SET p.problem_statement = coalesce(nullif($problem, ''), p.problem_statement),
                p.key_contribution  = coalesce(nullif($contribution, ''), p.key_contribution),
                p.evidence_quotes   = CASE WHEN size($quotes) > 0 THEN $quotes ELSE p.evidence_quotes END,
                p.analyzed_at       = CASE WHEN $tag IS NOT NULL THEN datetime() ELSE p.analyzed_at END
            """,
            {
                "paper_id":     paper_id,
                "problem":      meta.get("problem_statement") or personality.get("problem_statement") or "",
                "contribution": meta.get("key_contribution") or personality.get("key_contribution") or "",
                "quotes":       [str(q) for q in (personality.get("evidence_quotes") or []) if q][:4],
                "tag":          personality.get("personality_tag"),
            },
        )

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
                    "authors_text":     "",
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
                MATCH (p:Paper)
                WHERE p.arxiv_id = $arxiv_id OR p.paper_id = $arxiv_id OR p.paper_id = 'arxiv:' + $arxiv_id
                OPTIONAL MATCH (p)-[:AUTHORED_BY]->(a:Author)
                WITH p, collect(DISTINCT a.name) AS author_names, COUNT { (:Paper)-[:CITES]->(p) } AS cit_count
                RETURN p {
                    .paper_id, .title, .year, .arxiv_id,
                    .personality_tag, .confidence_score,
                    .primary_category, .authors_text,
                    citation_count: cit_count
                } AS node, author_names
                LIMIT 1
                """,
                arxiv_id=arxiv_id
            ).single()

            nodes = []
            if root_result:
                root_node = dict(root_result["node"])
                root_node["depth"] = 0
                root_node["id"] = root_node["paper_id"]
                root_node["label"] = root_node.get("title", arxiv_id)[:50]
                graph_authors = [a for a in root_result.get("author_names", []) if a]
                text_authors = [a.strip() for a in root_node.get("authors_text", "").split(",") if a.strip()] if root_node.get("authors_text") else []
                root_node["authors"] = text_authors if text_authors else graph_authors
                nodes.append(root_node)

            # ── 2. Fetch related nodes via CITES ──────────────────────────
            if direction in ("ancestors", "both"):
                query = f"""
                    MATCH path = (root:Paper)
                                 -[:CITES*1..{depth}]->(ancestor:Paper)
                    WHERE (root.arxiv_id = $arxiv_id OR root.paper_id = $arxiv_id OR root.paper_id = 'arxiv:' + $arxiv_id) 
                      AND ancestor.unresolved = false
                    OPTIONAL MATCH (ancestor)-[:AUTHORED_BY]->(a:Author)
                    WITH ancestor, min(length(path)) AS d, collect(DISTINCT a.name) AS author_names, COUNT {{ (:Paper)-[:CITES]->(ancestor) }} AS cit_count
                    RETURN ancestor {{
                        .paper_id, .title, .year, .arxiv_id,
                        .personality_tag, .confidence_score,
                        .primary_category, .authors_text,
                        depth: d, citation_count: cit_count
                    }} AS node, d AS depth, author_names
                    ORDER BY d ASC, cit_count DESC, ancestor.year DESC
                    LIMIT 65
                """
                result = session.run(query, arxiv_id=arxiv_id)
                for r in result:
                    n = dict(r["node"])
                    n["id"] = n["paper_id"]
                    n["label"] = n.get("title", "?")[:50]
                    graph_authors = [a for a in r.get("author_names", []) if a]
                    text_authors = [a.strip() for a in n.get("authors_text", "").split(",") if a.strip()] if n.get("authors_text") else []
                    n["authors"] = text_authors if text_authors else graph_authors
                    if not any(existing["paper_id"] == n["paper_id"] for existing in nodes):
                        nodes.append(n)

            if direction in ("descendants", "both"):
                query = f"""
                    MATCH path = (child:Paper)
                                 -[:CITES*1..{depth}]->(root:Paper)
                    WHERE (root.arxiv_id = $arxiv_id OR root.paper_id = $arxiv_id OR root.paper_id = 'arxiv:' + $arxiv_id) 
                      AND child.unresolved = false
                    AND child.paper_id <> root.paper_id
                    OPTIONAL MATCH (child)-[:AUTHORED_BY]->(a:Author)
                    WITH child, min(length(path)) AS d, collect(DISTINCT a.name) AS author_names, COUNT {{ (:Paper)-[:CITES]->(child) }} AS cit_count
                    RETURN child {{
                        .paper_id, .title, .year, .arxiv_id,
                        .personality_tag, .confidence_score,
                        .primary_category, .authors_text,
                        depth: d, citation_count: cit_count
                    }} AS node, d AS depth, author_names
                    ORDER BY d ASC, cit_count DESC, child.year DESC
                    LIMIT 45
                """
                result = session.run(query, arxiv_id=arxiv_id)
                for r in result:
                    n = dict(r["node"])
                    n["id"] = n["paper_id"]
                    n["label"] = n.get("title", "?")[:50]
                    graph_authors = [a for a in r.get("author_names", []) if a]
                    text_authors = [a.strip() for a in n.get("authors_text", "").split(",") if a.strip()] if n.get("authors_text") else []
                    n["authors"] = text_authors if text_authors else graph_authors
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
                "label": e.get("rel_type", "cites").upper(),
                "arrows": "to",
                "rel_type": e.get("rel_type", "cites"),
            })

        return {
            "root":      arxiv_id,
            "direction": direction,
            "nodes":     nodes,
            "edges":     vis_edges,
            "depth":     depth,
        }

    def _get_edges_between(self, paper_ids: list[str]) -> list[dict]:
        """Ambil semua CITES dan SIMILAR_TO edges di antara sekumpulan paper_ids."""
        query = """
            MATCH (src:Paper)-[r:CITES]->(tgt:Paper)
            WHERE src.paper_id IN $ids AND tgt.paper_id IN $ids
            RETURN src.paper_id AS source, tgt.paper_id AS target, 
                   r.match_confidence AS confidence, 'cites' AS rel_type
            UNION
            MATCH (src:Paper)-[r:SIMILAR_TO]->(tgt:Paper)
            WHERE src.paper_id IN $ids AND tgt.paper_id IN $ids
            RETURN src.paper_id AS source, tgt.paper_id AS target, 
                   r.similarity_score AS confidence, 'similar_to' AS rel_type
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

    # ── Paper Intelligence (Detail Panel) ────────────────────────────────
    def resolve_paper_id(self, identifier: str) -> str | None:
        """Terima paper_id / arxiv_id (dengan atau tanpa prefix) → paper_id kanonik."""
        query = """
            MATCH (p:Paper)
            WHERE p.paper_id = $id OR p.arxiv_id = $id
               OR p.paper_id = 'arxiv:' + $id
               OR p.arxiv_id = replace($id, 'arxiv:', '')
            RETURN p.paper_id AS paper_id
            LIMIT 1
        """
        with driver.session() as session:
            r = session.run(query, id=identifier.strip()).single()
            return r["paper_id"] if r else None

    def get_paper_details(self, paper_id: str) -> dict | None:
        """
        Data lengkap untuk Detail Panel: abstract, TL;DR, personality,
        evidence quotes, dan metrik posisi paper dalam silsilah graf.
        """
        query = """
            MATCH (p:Paper {paper_id: $pid})
            OPTIONAL MATCH (p)-[:AUTHORED_BY]->(a:Author)
            WITH p, collect(DISTINCT a.name) AS graph_authors
            
            // Citing papers (dikutip oleh)
            OPTIONAL MATCH (citing:Paper)-[:CITES]->(p)
            WITH p, graph_authors, 
                 count(DISTINCT citing) AS in_graph_citations,
                 collect(DISTINCT {
                     paper_id: citing.paper_id,
                     arxiv_id: citing.arxiv_id,
                     title: coalesce(citing.title, citing.paper_id),
                     year: citing.year,
                     personality_tag: citing.personality_tag
                 })[0..20] AS citing_papers

            // Cited references (mengutip)
            OPTIONAL MATCH (p)-[:CITES]->(ref:Paper)
            WITH p, graph_authors, in_graph_citations, citing_papers,
                 count(DISTINCT ref) AS references_count,
                 count(DISTINCT CASE WHEN ref.unresolved = false THEN ref END) AS resolved_references,
                 collect(DISTINCT {
                     paper_id: ref.paper_id,
                     arxiv_id: ref.arxiv_id,
                     title: coalesce(ref.title, ref.paper_id),
                     year: ref.year,
                     personality_tag: ref.personality_tag
                 })[0..30] AS cited_references

            OPTIONAL MATCH (p)-[:BELONGS_TO]->(t:Topic)
            RETURN p {
                .paper_id, .title, .year, .arxiv_id, .venue, .doi,
                .abstract, .problem_statement, .key_contribution,
                .personality_tag, .confidence_score, .reasoning,
                .evidence_quotes, .primary_category, .authors_text,
                .analyzed_at
            } AS paper,
            graph_authors,
            in_graph_citations,
            citing_papers,
            references_count,
            resolved_references,
            cited_references,
            collect(DISTINCT t.label) AS topics
        """
        with driver.session() as session:
            r = session.run(query, pid=paper_id).single()
            if not r:
                return None

        paper = dict(r["paper"])
        text_authors = [
            a.strip() for a in (paper.get("authors_text") or "").split(",") if a.strip()
        ]
        paper["authors"] = text_authors or [a for a in r["graph_authors"] if a]
        paper["topics"] = [t for t in r["topics"] if t]
        paper["evidence_quotes"] = list(paper.get("evidence_quotes") or [])
        paper["citing_papers"] = [c for c in (r["citing_papers"] or []) if c.get("paper_id")]
        paper["cited_references"] = [c for c in (r["cited_references"] or []) if c.get("paper_id")]
        if paper.get("analyzed_at") is not None:
            paper["analyzed_at"] = str(paper["analyzed_at"])

        citations  = r["in_graph_citations"]
        references = r["references_count"]
        paper["metrics"] = {
            "in_graph_citations":  citations,
            "references_count":    references,
            "resolved_references": r["resolved_references"],
            **self._classify_lineage_role(citations, references),
        }
        return paper

    @staticmethod
    def _classify_lineage_role(citations: int, references: int) -> dict:
        """
        Tentukan posisi paper dalam silsilah:
        - Foundational Root : lebih banyak disitasi daripada mensitasi (fondasi ide)
        - Derivative Work   : membangun di atas paper lain di graf (turunan)
        - Isolated Node     : belum punya relasi sitasi di graf
        """
        if citations == 0 and references == 0:
            return {
                "lineage_role": "Isolated Node",
                "lineage_role_key": "isolated",
                "lineage_role_desc": "Belum ada relasi sitasi di graf. Klik Expand Lineage untuk memetakan silsilahnya.",
            }
        if citations > references:
            return {
                "lineage_role": "Foundational Root",
                "lineage_role_key": "root",
                "lineage_role_desc": "Lebih banyak menjadi rujukan daripada merujuk — fondasi bagi riset turunan di graf.",
            }
        return {
            "lineage_role": "Derivative Work",
            "lineage_role_key": "derivative",
            "lineage_role_desc": "Dibangun di atas karya-karya sebelumnya yang terpetakan di graf.",
        }

    def save_paper_analysis(self, paper_id: str, analysis: dict, abstract: str | None = None) -> None:
        """Persist hasil analisis DeepSeek R1 (personality + TL;DR) ke node Paper."""
        query = """
            MATCH (p:Paper {paper_id: $pid})
            SET p.personality_tag   = $tag,
                p.confidence_score  = $confidence,
                p.reasoning         = $reasoning,
                p.evidence_quotes   = $quotes,
                p.problem_statement = coalesce(nullif($problem, ''), p.problem_statement),
                p.key_contribution  = coalesce(nullif($contribution, ''), p.key_contribution),
                p.abstract          = coalesce(nullif($abstract, ''), p.abstract),
                p.analyzed_at       = datetime(),
                p.updated_at        = datetime()
        """
        quotes = [str(q) for q in (analysis.get("evidence_quotes") or []) if q][:4]
        with driver.session() as session:
            session.run(
                query,
                pid=paper_id,
                tag=analysis.get("personality_tag"),
                confidence=float(analysis.get("confidence_score") or 0.0),
                reasoning=analysis.get("reasoning") or "",
                quotes=quotes,
                problem=analysis.get("problem_statement") or "",
                contribution=analysis.get("key_contribution") or "",
                abstract=abstract or "",
            )

    def hydrate_paper_metadata(
        self,
        paper_id: str,
        abstract: str,
        authors: list[str] = None,
        title: str = None,
        primary_category: str = None
    ):
        """Update stub paper with hydrated metadata from ArXiv."""
        query = """
            MATCH (p:Paper {paper_id: $pid})
            SET p.abstract = CASE WHEN $abstract <> '' THEN $abstract ELSE p.abstract END,
                p.unresolved = false,
                p.updated_at = datetime()
            WITH p
            WHERE $title IS NOT NULL AND $title <> '' AND (p.title IS NULL OR p.title STARTS WITH 'ArXiv')
            SET p.title = $title
            WITH p
            WHERE $authors_text IS NOT NULL AND $authors_text <> '' AND p.authors_text IS NULL
            SET p.authors_text = $authors_text
            WITH p
            WHERE $primary_category IS NOT NULL AND $primary_category <> '' AND p.primary_category IS NULL
            SET p.primary_category = $primary_category
        """
        authors_text = ", ".join(authors) if authors else ""
        with driver.session() as session:
            session.run(
                query,
                pid=paper_id,
                abstract=abstract or "",
                title=title or "",
                authors_text=authors_text,
                primary_category=primary_category or ""
            )

    # ── GraphRAG Smart Search ─────────────────────────────────────────────
    def smart_graphrag_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        limit: int = 10,
        min_similarity: float = 0.58
    ) -> list[dict]:
        """
        AI-Powered Paper Discovery Endpoint (GraphRAG).
        Combines Neo4j Vector Search + Graph Neighbor Expansion + Re-ranking.
        Applies a minimum semantic threshold and log-dampened citation score
        to avoid irrelevant popular papers dominating the results.
        """
        query = """
        // 1. Vector Search for Core Candidates with minimum relevance threshold
        CALL db.index.vector.queryNodes('paper_embedding_index', $top_k, $embedding)
        YIELD node AS paper, score AS similarity_score
        WHERE similarity_score >= $min_similarity
        WITH paper, similarity_score

        // 2. Expand Neighbors 0 to 2 hops away
        // If direct similarity is high (>= 0.70), expand neighbors; otherwise keep to direct seed
        OPTIONAL MATCH path = (paper)-[:CITES*0..2]-(neighbor:Paper)
        WHERE neighbor IS NOT NULL 
          AND neighbor.unresolved = false
          AND (similarity_score >= 0.70 OR paper = neighbor)

        // 3. Unify Candidate Selection
        WITH neighbor AS candidate, 
             max(similarity_score) AS context_sim, 
             max(CASE WHEN paper = neighbor THEN similarity_score ELSE 0 END) AS direct_sim,
             min(length(path)) AS hop_distance

        // 4. Citation Count for Prominence
        OPTIONAL MATCH ()-[r:CITES]->(candidate)
        WITH candidate, context_sim, direct_sim, hop_distance, count(r) AS citation_count

        // 5. Re-ranking: heavily weight semantic match, dampen citation bias via log
        WITH candidate, context_sim, direct_sim, hop_distance, citation_count,
             coalesce(candidate.year, 2018) AS c_year

        // Re-ranking formula:
        // Direct semantic match gets up to 0.75.
        // Citation popularity is dampened logarithmically.
        WITH candidate, direct_sim, context_sim, hop_distance, citation_count,
             (CASE 
                WHEN direct_sim > 0 THEN direct_sim * 0.75 
                ELSE (context_sim / (hop_distance + 1.2)) * 0.45 
              END) + 
             (log(citation_count + 1) * 0.04) + 
             (CASE WHEN c_year >= 2015 THEN (c_year - 2015) * 0.005 ELSE 0 END) AS final_score

        WHERE final_score >= 0.45

        RETURN 
          candidate.paper_id AS paper_id,
          candidate.title AS title,
          candidate.year AS year,
          candidate.arxiv_id AS arxiv_id,
          candidate.personality_tag AS personality,
          direct_sim AS vector_similarity,
          hop_distance,
          citation_count,
          final_score
        ORDER BY final_score DESC
        LIMIT $limit
        """
        with driver.session() as session:
            result = session.run(
                query,
                embedding=query_embedding,
                top_k=top_k,
                limit=limit,
                min_similarity=min_similarity
            )
            return [dict(r) for r in result]

    def get_untagged_papers(self, limit: int = 20) -> list[dict]:
        """Ambil makalah dalam graf yang belum memiliki personality tag untuk analisis massal."""
        query = """
            MATCH (p:Paper)
            WHERE p.personality_tag IS NULL 
              AND p.title IS NOT NULL
              AND p.title <> ''
              AND NOT p.title STARTS WITH 'ArXiv'
            RETURN p.paper_id AS paper_id,
                   p.arxiv_id AS arxiv_id,
                   p.title AS title,
                   p.year AS year,
                   coalesce(p.abstract, '') AS abstract,
                   p.primary_category AS primary_category
            LIMIT $limit
        """
        with driver.session() as session:
            result = session.run(query, limit=limit)
            return [dict(r) for r in result]

    def import_openalex_paper(self, paper_data: dict) -> dict:
        """
        Impor makalah dari OpenAlex ke dalam basis data Knowledge Graph Neo4j.
        Membuat node :Paper, mengklasifikasikan peran ilmiahnya, menghubungkan topik/penulis,
        serta menautkan relasi ke makalah relevan yang sudah ada di graf lokal.
        """
        from pipeline.personality_tagger import heuristic_classify_paper

        raw_id = paper_data.get("paper_id") or f"openalex:{str(paper_data.get('doi', '') or uuid.uuid4().hex[:8]).replace('/', '_')}"
        arxiv_id = paper_data.get("arxiv_id")
        paper_id = f"arxiv:{arxiv_id}" if arxiv_id and not raw_id.startswith("arxiv:") else raw_id

        title = paper_data.get("title") or "Unknown Title"
        abstract = paper_data.get("abstract") or ""
        year = _safe_int(paper_data.get("year"))
        doi = paper_data.get("doi")
        venue = paper_data.get("venue")
        authors = paper_data.get("authors") or []
        authors_text = ", ".join(authors)

        # Klasifikasi awal instan agar simpul memiliki peran ilmiah dan ringkasan
        initial_analysis = heuristic_classify_paper(title=title, abstract=abstract, year=year)

        with driver.session() as session:
            session.run(
                MERGE_PAPER,
                {
                    "paper_id":         paper_id,
                    "title":            title,
                    "abstract":         abstract,
                    "year":             year,
                    "venue":            venue,
                    "arxiv_id":         arxiv_id,
                    "doi":              doi,
                    "personality_tag":  initial_analysis.get("personality_tag"),
                    "confidence_score": initial_analysis.get("confidence_score", 0.75),
                    "reasoning":        initial_analysis.get("reasoning", ""),
                    "primary_category": "openalex",
                    "embedding":        None,
                    "unresolved":       False,
                    "authors_text":     authors_text
                }
            )

            session.run(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.problem_statement = coalesce(nullif($problem, ''), p.problem_statement),
                    p.key_contribution  = coalesce(nullif($contribution, ''), p.key_contribution),
                    p.evidence_quotes   = CASE WHEN size($quotes) > 0 THEN $quotes ELSE p.evidence_quotes END,
                    p.analyzed_at       = datetime()
                """,
                {
                    "paper_id":     paper_id,
                    "problem":      initial_analysis.get("problem_statement", ""),
                    "contribution": initial_analysis.get("key_contribution", ""),
                    "quotes":       initial_analysis.get("evidence_quotes", []),
                }
            )

            # Relasi penulis
            for idx, a_name in enumerate(authors):
                if not a_name:
                    continue
                a_id = _make_id("author", a_name)
                session.run(MERGE_AUTHOR, {"author_id": a_id, "name": a_name, "affiliation": None})
                session.run(
                    MERGE_AUTHORED_BY,
                    {
                        "paper_id": paper_id,
                        "author_id": a_id,
                        "order": idx + 1,
                        "is_corresponding": (idx == 0),
                    },
                )

            # Relasi topik (lengkap dengan parameter domain, hierarchy_level, dan confidence_score)
            for t_label in (paper_data.get("topics") or []):
                if not t_label:
                    continue
                t_id = _make_id("topic", t_label)
                session.run(
                    MERGE_TOPIC,
                    {
                        "topic_id": t_id,
                        "label": t_label,
                        "domain": _infer_domain(t_label),
                        "hierarchy_level": 1,
                    },
                )
                session.run(
                    MERGE_BELONGS_TO,
                    {
                        "paper_id": paper_id,
                        "topic_id": t_id,
                        "confidence_score": 0.9,
                    },
                )

            # Tautkan ke makalah relevan di graf lokal berdasarkan kata kunci judul/topik agar dapat divisualisasikan
            stop_words = {
                "a", "an", "the", "of", "for", "in", "on", "with", "via", "using", "by", "to", "and",
                "from", "based", "towards", "deep", "learning", "network", "networks", "model", "models",
                "neural", "approach", "method", "system", "analysis", "study", "new", "modified"
            }
            raw_tokens = [
                w.strip(".,:;()[]{}\"'?!").lower()
                for w in (title + " " + " ".join(paper_data.get("topics") or [])).split()
            ]
            keywords = []
            for tok in raw_tokens:
                if len(tok) >= 4 and tok not in stop_words and tok not in keywords:
                    keywords.append(tok)
            keywords = keywords[:6]

            if keywords:
                session.run(
                    """
                    MATCH (src:Paper {paper_id: $paper_id})
                    MATCH (other:Paper)
                    WHERE other.paper_id <> $paper_id
                      AND other.unresolved = false
                      AND other.title IS NOT NULL
                      AND any(kw IN $keywords WHERE toLower(other.title) CONTAINS kw OR toLower(coalesce(other.abstract, '')) CONTAINS kw)
                    WITH src, other,
                         size([kw IN $keywords WHERE toLower(other.title) CONTAINS kw]) * 2 +
                         size([kw IN $keywords WHERE toLower(coalesce(other.abstract, '')) CONTAINS kw]) AS rel_score
                    ORDER BY rel_score DESC, coalesce(other.year, 2000) ASC
                    LIMIT 6
                    FOREACH (_ IN CASE WHEN coalesce(other.year, 2025) <= coalesce($year, 2025) THEN [1] ELSE [] END |
                        MERGE (src)-[r:CITES]->(other)
                        SET r.resolved_via = 'openalex_topic_link',
                            r.match_confidence = 0.75,
                            r.created_at = coalesce(r.created_at, datetime())
                    )
                    FOREACH (_ IN CASE WHEN coalesce(other.year, 2025) > coalesce($year, 2025) THEN [1] ELSE [] END |
                        MERGE (other)-[r:CITES]->(src)
                        SET r.resolved_via = 'openalex_topic_link',
                            r.match_confidence = 0.75,
                            r.created_at = coalesce(r.created_at, datetime())
                    )
                    """,
                    {"paper_id": paper_id, "keywords": keywords, "year": year or 2024},
                )

        return {
            "paper_id": paper_id,
            "arxiv_id": arxiv_id,
            "title": title,
            "year": year,
            "personality_tag": initial_analysis.get("personality_tag"),
        }


# Singleton
graph_service = GraphService()