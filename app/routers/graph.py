# app/routers/graph.py
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
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
    Auto-hydrates stub nodes if abstract or title is missing.
    """
    resolved = await asyncio.to_thread(graph_service.resolve_paper_id, paper_id)
    if not resolved:
        raise HTTPException(404, f"Paper '{paper_id}' not found in graph")
    details = await asyncio.to_thread(graph_service.get_paper_details, resolved)
    if not details:
        raise HTTPException(404, f"Paper '{paper_id}' not found in graph")

    # Auto-hydrate stub node if abstract or title is missing but arxiv_id exists
    has_abstract = bool(details.get("abstract") and details["abstract"].strip())
    has_clean_title = bool(details.get("title") and not details["title"].startswith("ArXiv"))
    if (not has_abstract or not has_clean_title) and details.get("arxiv_id"):
        from services.arxiv_service import arxiv_service
        try:
            arxiv_paper = await asyncio.to_thread(arxiv_service.fetch_by_id, details["arxiv_id"])
            if arxiv_paper:
                if arxiv_paper.abstract and not has_abstract:
                    details["abstract"] = arxiv_paper.abstract
                if arxiv_paper.title and not has_clean_title:
                    details["title"] = arxiv_paper.title
                if arxiv_paper.authors and not details.get("authors"):
                    details["authors"] = arxiv_paper.authors
                if arxiv_paper.primary_category and not details.get("primary_category"):
                    details["primary_category"] = arxiv_paper.primary_category
                
                await asyncio.to_thread(
                    graph_service.hydrate_paper_metadata,
                    resolved,
                    details.get("abstract") or "",
                    details.get("authors") or [],
                    details.get("title") or "",
                    details.get("primary_category") or ""
                )
        except Exception as e:
            log.warning(f"Could not auto-hydrate paper {resolved}: {e}")

    return details


@router.post("/paper/{paper_id}/analyze")
async def analyze_paper(paper_id: str):
    """
    Jalankan klasifikasi peran ilmiah on-demand untuk paper yang belum di-tag.
    Jika abstract belum ada (stub node), abstract diambil dari ArXiv atau OpenAlex.
    """
    from pipeline.personality_tagger import classify_paper_with_fallback
    from services.arxiv_service import arxiv_service
    from services.openalex_service import openalex_service

    resolved = await asyncio.to_thread(graph_service.resolve_paper_id, paper_id)
    if not resolved:
        raise HTTPException(404, f"Paper '{paper_id}' not found in graph")

    paper = await asyncio.to_thread(graph_service.get_paper_details, resolved)
    abstract   = paper.get("abstract") or ""
    categories = [paper["primary_category"]] if paper.get("primary_category") else []
    fetched_abstract = None

    # Stub node -> lengkapi abstract dari ArXiv
    if not abstract.strip() and paper.get("arxiv_id"):
        try:
            arxiv_paper = await asyncio.to_thread(arxiv_service.fetch_by_id, paper["arxiv_id"])
            if arxiv_paper and arxiv_paper.abstract:
                abstract = fetched_abstract = arxiv_paper.abstract
                categories = arxiv_paper.categories or categories
        except Exception as e:
            log.warning(f"ArXiv abstract fetch failed for {resolved}: {e}")

    # Fallback -> lengkapi abstract dari OpenAlex berdasarkan judul
    if not abstract.strip() and paper.get("title"):
        try:
            oa_results = await asyncio.to_thread(openalex_service.search_works, paper["title"], 1)
            if oa_results and oa_results[0].get("abstract"):
                abstract = fetched_abstract = oa_results[0]["abstract"]
        except Exception as e:
            log.warning(f"OpenAlex abstract fetch failed for {resolved}: {e}")

    log.info(f"Running reasoning analysis for {resolved}")
    result = await asyncio.to_thread(
        classify_paper_with_fallback,
        title=paper.get("title") or "",
        abstract=abstract,
        categories=categories,
        year=paper.get("year"),
    )

    if not result.get("personality_tag"):
        raise HTTPException(502, "Gagal menghasilkan klasifikasi peran ilmiah.")

    await asyncio.to_thread(graph_service.save_paper_analysis, resolved, result, fetched_abstract)
    return await asyncio.to_thread(graph_service.get_paper_details, resolved)


class BatchAnalyzeRequest(BaseModel):
    paper_ids: Optional[list[str]] = None
    max_papers: int = 8


@router.get("/untagged")
async def get_untagged_nodes(limit: int = Query(15, ge=1, le=50)):
    """Daftar simpul makalah dalam graf yang belum memiliki klasifikasi personality ilmiah."""
    papers = await asyncio.to_thread(graph_service.get_untagged_papers, limit)
    return {"count": len(papers), "papers": papers}


@router.post("/batch-analyze")
async def batch_analyze_papers(payload: BatchAnalyzeRequest):
    """
    Jalankan analisis peran ilmiah secara massal (batch)
    dengan kontrol konkurensi (semaphore) dan fallback cerdas agar seluruh simpul terklasifikasi.
    """
    from pipeline.personality_tagger import classify_paper_with_fallback
    from services.arxiv_service import arxiv_service
    from services.openalex_service import openalex_service

    target_ids = payload.paper_ids or []
    if not target_ids:
        untagged = await asyncio.to_thread(graph_service.get_untagged_papers, payload.max_papers)
        target_ids = [p["paper_id"] for p in untagged]

    if not target_ids:
        return {"total": 0, "succeeded": 0, "failed": 0, "results": []}

    target_ids = target_ids[:max(1, min(payload.max_papers, 15))]
    semaphore = asyncio.Semaphore(2)
    results = []

    async def process_paper(pid: str):
        async with semaphore:
            resolved = await asyncio.to_thread(graph_service.resolve_paper_id, pid)
            if not resolved:
                return {"paper_id": pid, "status": "error", "message": "Paper not found"}

            paper = await asyncio.to_thread(graph_service.get_paper_details, resolved)
            if not paper:
                return {"paper_id": pid, "status": "error", "message": "Details not found"}

            abstract = paper.get("abstract") or ""
            categories = [paper["primary_category"]] if paper.get("primary_category") else []
            fetched_abstract = None

            # Stub node fallback via ArXiv
            if not abstract.strip() and paper.get("arxiv_id"):
                try:
                    arxiv_paper = await asyncio.to_thread(arxiv_service.fetch_by_id, paper["arxiv_id"])
                    if arxiv_paper and arxiv_paper.abstract:
                        abstract = fetched_abstract = arxiv_paper.abstract
                        categories = arxiv_paper.categories or categories
                except Exception:
                    pass

            # Stub node fallback via OpenAlex
            if not abstract.strip() and paper.get("title") and not paper["title"].startswith("ArXiv"):
                try:
                    oa_works = await asyncio.to_thread(openalex_service.search_works, paper["title"], 1)
                    if oa_works and oa_works[0].get("abstract"):
                        abstract = fetched_abstract = oa_works[0]["abstract"]
                except Exception:
                    pass

            try:
                analysis = await asyncio.to_thread(
                    classify_paper_with_fallback,
                    title=paper.get("title") or "",
                    abstract=abstract,
                    categories=categories,
                    year=paper.get("year"),
                )
                if not analysis.get("personality_tag"):
                    return {
                        "paper_id": pid,
                        "status": "failed",
                        "message": analysis.get("error") or "Gagal menentukan peran"
                    }

                await asyncio.to_thread(graph_service.save_paper_analysis, resolved, analysis, fetched_abstract)
                return {
                    "paper_id": resolved,
                    "requested_id": pid,
                    "title": paper.get("title"),
                    "status": "success",
                    "personality_tag": analysis.get("personality_tag"),
                    "confidence_score": analysis.get("confidence_score"),
                    "reasoning": analysis.get("reasoning")
                }
            except Exception as e:
                return {"paper_id": pid, "status": "error", "message": str(e)}

    tasks = [process_paper(pid) for pid in target_ids]
    completed = await asyncio.gather(*tasks)

    succeeded = sum(1 for c in completed if c.get("status") == "success")
    failed = len(completed) - succeeded

    return {
        "total": len(completed),
        "succeeded": succeeded,
        "failed": failed,
        "results": completed
    }


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
