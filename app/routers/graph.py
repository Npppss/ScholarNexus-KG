# app/routers/graph.py
from fastapi import APIRouter, Query
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