# app/routers/graph.py
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from services.graph_service  import graph_service
from app.routers.cognitive import cognitive_search as cognitive_search_v2

log = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


# ── Paper Intelligence: data lengkap untuk Detail Panel ──────────────────────
@router.get("/paper/{paper_id}/details")
async def get_paper_details(paper_id: str):
    """
    Abstract, TL;DR (problem & contribution), personality + evidence,
    dan metrik silsilah (in-graph citations, references, lineage role).
    """
    resolved = await asyncio.to_thread(graph_service.resolve_paper_id, paper_id)
    if not resolved:
        raise HTTPException(404, f"Paper '{paper_id}' not found in graph")
    details = await asyncio.to_thread(graph_service.get_paper_details, resolved)
    if not details:
        raise HTTPException(404, f"Paper '{paper_id}' not found in graph")
    return details


@router.post("/paper/{paper_id}/analyze")
async def analyze_paper(paper_id: str):
    """
    Jalankan DeepSeek R1 on-demand untuk paper yang belum di-tag.
    Jika abstract belum ada (stub node), abstract diambil dulu dari ArXiv.
    """
    from pipeline.personality_tagger import classify_arxiv_paper
    from services.arxiv_service import arxiv_service

    resolved = await asyncio.to_thread(graph_service.resolve_paper_id, paper_id)
    if not resolved:
        raise HTTPException(404, f"Paper '{paper_id}' not found in graph")

    paper = await asyncio.to_thread(graph_service.get_paper_details, resolved)
    abstract   = paper.get("abstract") or ""
    categories = [paper["primary_category"]] if paper.get("primary_category") else []
    fetched_abstract = None

    # Stub node → lengkapi abstract dari ArXiv
    if not abstract.strip() and paper.get("arxiv_id"):
        arxiv_paper = await asyncio.to_thread(arxiv_service.fetch_by_id, paper["arxiv_id"])
        if arxiv_paper:
            abstract = fetched_abstract = arxiv_paper.abstract
            categories = arxiv_paper.categories or categories

    if not abstract.strip():
        raise HTTPException(422, "Abstract tidak tersedia — paper tidak bisa dianalisis.")

    log.info(f"🧠 On-demand reasoning analysis for {resolved}")
    result = await asyncio.to_thread(
        classify_arxiv_paper,
        title=paper.get("title") or "",
        abstract=abstract,
        categories=categories,
        year=paper.get("year"),
    )

    if result.get("error"):
        err = result["error"]
        if "Insufficient Balance" in err or "402" in err or "RESOURCE_EXHAUSTED" in err or "Quota" in err:
            raise HTTPException(402, "Kuota / saldo API habis. Silakan periksa akun API key Anda.")
        if "401" in err or "Authentication" in err or "API_KEY_INVALID" in err:
            raise HTTPException(401, "API key tidak valid. Silakan periksa konfigurasi di .env.")
        raise HTTPException(502, f"Analisis LLM gagal: {err[:200]}")
    if not result.get("personality_tag"):
        raise HTTPException(502, "Model LLM tidak menghasilkan tag yang valid. Silakan coba lagi.")

    await asyncio.to_thread(graph_service.save_paper_analysis, resolved, result, fetched_abstract)
    return await asyncio.to_thread(graph_service.get_paper_details, resolved)


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
    request: Request,
    paper_id: str,
    profile: str = Query("balanced"),
    decay: Optional[float] = Query(None, ge=0.1, le=0.95),
    threshold: Optional[float] = Query(None, ge=0.001, le=0.5),
    max_depth: Optional[int] = Query(None, ge=1, le=8),
    max_results: Optional[int] = Query(None, ge=5, le=100),
    max_expansions: Optional[int] = Query(None, ge=100, le=20000),
    no_cache: bool = Query(False),
):
    """
    Legacy endpoint for backward compatibility.
    Delegates to the canonical Cognitive router handler.
    """
    return await cognitive_search_v2(
        request=request,
        paper_id=paper_id,
        profile=profile,
        decay=decay,
        threshold=threshold,
        max_depth=max_depth,
        max_results=max_results,
        max_expansions=max_expansions,
        no_cache=no_cache,
    )
