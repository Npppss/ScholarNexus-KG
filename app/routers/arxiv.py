from fastapi import APIRouter, HTTPException, BackgroundTasks, logger
from pydantic import BaseModel, field_validator
from typing import Optional

from services.arxiv_service import ArxivPaper
from services.graph_service import upsert_paper_to_graph
from services.vector_service import generate_embedding

router = APIRouter(prefix="/arxiv", tags=["arxiv"])


class ArxivFetchRequest(BaseModel):
    """Request body untuk fetch satu atau banyak paper dari ArXiv."""
    arxiv_ids: list[str]
    auto_fetch_references: bool = False   # Jika True, rekursif fetch refs-nya juga

    @field_validator("arxiv_ids")
    @classmethod
    def validate_ids(cls, ids):
        if not ids:
            raise ValueError("arxiv_ids cannot be empty")
        if len(ids) > 50:
            raise ValueError("Max 50 IDs per request")
        return ids


class ArxivSearchRequest(BaseModel):
    """Request body untuk search ArXiv berdasarkan query teks."""
    query:       str
    max_results: int              = 10
    category:    Optional[str]   = None   # e.g. "cs.CL", "cs.LG"
    year_from:   Optional[int]   = None
    year_to:     Optional[int]   = None


# ── Endpoint 1: Fetch by ID ──────────────────────────────────────────────────
@router.post("/fetch")
async def fetch_by_ids(
    req: ArxivFetchRequest,
    background_tasks: BackgroundTasks
):
    """
    Fetch satu atau lebih paper dari ArXiv ID.
    Paper langsung dimasukkan ke Knowledge Graph.
    """
    results  = {"success": [], "failed": []}

    for arxiv_id in req.arxiv_ids:
        paper = arxiv_service.fetch_by_id(arxiv_id)

        if not paper:
            results["failed"].append({
                "arxiv_id": arxiv_id,
                "reason": "Not found on ArXiv or invalid ID"
            })
            continue

        # Generate embedding dan simpan ke graph (background task)
        background_tasks.add_task(
            _persist_arxiv_paper,
            paper,
            req.auto_fetch_references
        )

        results["success"].append({
            "arxiv_id":       paper.arxiv_id,
            "title":          paper.title,
            "authors":        paper.authors[:3],
            "year":           paper.year,
            "categories":     paper.categories,
            "venue":          paper.venue_parsed,
        })

    return {
        "fetched":      len(results["success"]),
        "failed":       len(results["failed"]),
        "details":      results,
    }


# ── Endpoint 2: Search ArXiv ─────────────────────────────────────────────────
@router.post("/search")
async def search_arxiv(req: ArxivSearchRequest):
    """
    Search ArXiv dengan query bebas. Hasilnya preview only — belum masuk graph.
    Gunakan /fetch setelah memilih paper yang diinginkan.
    """
    query = req.query
    if req.category:
        query = f"cat:{req.category} AND ({query})"

    try:
        search = arxiv.Search(
            query       = query,
            max_results = min(req.max_results, 25),  # hard cap
            sort_by     = arxiv.SortCriterion.Relevance,
        )
        papers = []
        for result in search.results():
            if req.year_from and result.published.year < req.year_from:
                continue
            if req.year_to and result.published.year > req.year_to:
                continue

            papers.append({
                "arxiv_id":  result.entry_id.split("/abs/")[-1],
                "title":     result.title,
                "authors":   [a.name for a in result.authors[:4]],
                "abstract":  result.summary[:300] + "...",
                "year":      result.published.year,
                "categories": result.categories,
                "pdf_url":   result.pdf_url,
            })

        return {"query": req.query, "count": len(papers), "papers": papers}

    except Exception as e:
        raise HTTPException(500, f"ArXiv search failed: {str(e)}")


# ── Endpoint 3: Expand graph dari paper yang sudah ada ───────────────────────
@router.post("/expand/{arxiv_id}")
async def expand_from_paper(
    arxiv_id: str,
    depth:    int = 1,            # berapa level referensi yang diikuti
    background_tasks: BackgroundTasks = None,
):
    """
    Dari satu paper, fetch semua referensinya dan masukkan ke graph.
    Ini membangun 'Research Lineage' secara otomatis.
    depth=1 → refs langsung saja
    depth=2 → refs + refs-dari-refs (hati-hati: bisa ribuan paper!)
    """
    if depth > 2:
        raise HTTPException(400, "Max depth is 2 to prevent graph explosion")

    # Fetch paper utama
    paper = arxiv_service.fetch_by_id(arxiv_id)
    if not paper:
        raise HTTPException(404, f"ArXiv paper {arxiv_id} not found")

    # Untuk sekarang kita return metadata saja; refs diproses di background
    background_tasks.add_task(
        _expand_references_background, arxiv_id, depth
    )

    return {
        "status":    "expansion_started",
        "arxiv_id":  paper.arxiv_id,
        "title":     paper.title,
        "message":   f"Processing references at depth={depth} in background",
    }


# ── Background Tasks ─────────────────────────────────────────────────────────
async def _persist_arxiv_paper(paper, fetch_refs: bool):
    """Simpan ArxivPaper ke Neo4j + generate embedding."""
    embedding = generate_embedding(f"{paper.title}. {paper.abstract}")
    upsert_paper_to_graph(
        arxiv_paper = paper,
        embedding   = embedding,
    )
    if fetch_refs and paper.arxiv_id:
        await _expand_references_background(paper.arxiv_id, depth=1)


async def _expand_references_background(arxiv_id: str, depth: int):
    """Background task: ambil referensi dan masukkan ke graph."""
    logger.info(f"Expanding references for {arxiv_id} at depth={depth}")
    # Implementation: fetch related papers via ArXiv search
    # menggunakan judul paper utama sebagai seed query
    pass    