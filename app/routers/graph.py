# app/routers/graph.py
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from services.graph_service  import graph_service
from services.vector_service import generate_embedding

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/lineage/{arxiv_id}")
async def get_lineage(
    arxiv_id:  str,
    direction: str = Query("ancestors", enum=["ancestors","descendants","both"]),
    depth:     int = Query(3, ge=1, le=6),
):
    """
    Kembalikan Research Lineage sebagai graph {nodes, edges} —
    siap dikonsumsi oleh frontend visualisasi (D3, Cytoscape, dsb).
    """
    return graph_service.get_research_lineage(arxiv_id, direction, depth)


@router.get("/similar/{arxiv_id}")
async def get_similar(
    arxiv_id:   str,
    top_k:      int   = Query(10, ge=1, le=50),
    min_score:  float = Query(0.75, ge=0.0, le=1.0),
    materialize: bool = Query(True),
):
    """Cari paper semantically similar menggunakan vector index."""
    from services.graph_service import driver

    # Ambil embedding paper yang sudah tersimpan
    with driver.session() as session:
        r = session.run(
            "MATCH (p:Paper {arxiv_id: $id}) RETURN p.paper_id AS pid, p.embedding AS emb",
            id=arxiv_id
        ).single()
        if not r or not r["emb"]:
            return {"error": "Paper not found or has no embedding"}
        paper_id  = r["pid"]
        embedding = list(r["emb"])

    return {
        "source":  arxiv_id,
        "similar": graph_service.find_similar_papers(
            paper_id, embedding, top_k, min_score, materialize
        )
    }


@router.get("/stats")
async def graph_stats():
    """Overview stats seluruh Knowledge Graph."""
    return {
        "graph":        graph_service.get_graph_stats(),
        "personality":  graph_service.get_personality_distribution(),
    }

@router.get("/bibtex/{arxiv_id}", response_class=PlainTextResponse)
async def export_bibtex(arxiv_id: str, depth: int = Query(3, ge=1, le=6)):
    """Export the lineage graph of a paper into BibTeX format."""
    lineage = graph_service.get_research_lineage(arxiv_id, "both", depth)
    nodes = lineage.get("nodes", [])
    
    if not nodes:
        return ""
        
    bibtex_entries = []
    for n in nodes:
        authors_str = " and ".join(n.get("authors", [])) if n.get("authors") else "Unknown Author"
        title = n.get("title", "Unknown Title")
        year = n.get("year", "Unknown Year")
        pid = n.get("arxiv_id") or n.get("paper_id", "id").replace(":", "_")
        
        entry = (
            f"@article{{{pid},\n"
            f"  title={{{title}}},\n"
            f"  author={{{authors_str}}},\n"
            f"  year={{{year}}},\n"
            f"  journal={{arXiv preprint arXiv:{n.get('arxiv_id', '')}}},\n"
            f"}}"
        )
        bibtex_entries.append(entry)
        
    return "\n\n".join(bibtex_entries)


@router.post("/cognitive-search/{paper_id}")
async def cognitive_search(
    paper_id: str,
    decay: float = Query(0.85, ge=0.1, le=0.95),      # Higher decay retention
    threshold: float = Query(0.01, ge=0.001, le=0.5), # Lower drop-off threshold
    max_depth: int = Query(6, ge=1, le=8),
    max_results: int = Query(50, ge=5, le=100),
):
    """
    Cognitive Search — Spreading Activation Network.
    Simulates human associative thinking to discover serendipitous connections.
    """
    from services.cognitive_service import CognitiveSearch

    engine = CognitiveSearch(
        decay_factor=decay,
        threshold=threshold,
        max_depth=max_depth,
    )
    return engine.activate(paper_id, max_results=max_results)