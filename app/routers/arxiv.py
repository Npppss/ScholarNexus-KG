from fastapi import APIRouter, HTTPException, BackgroundTasks, logger
from pydantic import BaseModel, field_validator
from typing import Optional
import arxiv
from services.arxiv_service import arxiv_service
from services.arxiv_service import ArxivPaper
from services.graph_service import upsert_paper_to_graph, _make_paper_id, driver, MERGE_PAPER, MERGE_CITES
from services.vector_service import generate_embedding
from services.semantic_scholar_service import semantic_scholar_service
from pipeline.personality_tagger import classify_arxiv_paper
import logging

log = logging.getLogger(__name__)

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
    """Simpan ArxivPaper ke Neo4j + generate embedding + personality tag."""

    # 1. Generate embedding
    embedding = generate_embedding(f"{paper.title}. {paper.abstract}")

    # 2. Personality tagging via Gemini LLM
    log.info(f"🎭 Tagging personality for: {paper.title[:60]}...")
    personality = classify_arxiv_paper(
        title      = paper.title,
        abstract   = paper.abstract,
        categories = paper.categories,
        year       = paper.year,
    )

    # 3. Build extraction dict
    extraction = {
        "title": paper.title,
        "metadata": {
            "abstract": getattr(paper, "abstract", ""),
            "year":     getattr(paper, "year", None),
            "venue":    getattr(paper, "venue_parsed", None),
            "authors":  getattr(paper, "authors", []),
            "methods_proposed": [],
            "methods_used_as_baseline": [],
            "topics":   getattr(paper, "categories", []),
        },
        "personality": {
            "personality_tag":  personality.get("personality_tag"),
            "confidence_score": personality.get("confidence_score", 0.0),
            "reasoning":        personality.get("reasoning", ""),
        },
    }

    # 4. Upsert to Neo4j
    upsert_paper_to_graph(
        extraction  = extraction,
        embedding   = embedding,
        arxiv_paper = paper,
    )

    # 5. Fetch related papers
    if fetch_refs and paper.arxiv_id:
        await _expand_references_background(paper.arxiv_id, depth=1)


async def _expand_references_background(arxiv_id: str, depth: int):
    """
    Background task: fetch references + citations dari Semantic Scholar
    dan buat node stub + relasi CITES di Neo4j.
    """
    log.info(f"🔗 Expanding references for {arxiv_id} at depth={depth}")

    try:
        # 1. Fetch dari Semantic Scholar API
        result = semantic_scholar_service.get_references_and_citations(arxiv_id)
        
        # Smart expansion: hanya expand paper yang punya ArXiv ID
        references = [r for r in result["references"] if r.arxiv_id]
        citations  = [c for c in result["citations"] if c.arxiv_id]

        log.info(f"   Found {len(references)} ArXiv references, {len(citations)} ArXiv citations")

        # 2. paper_id dari paper saat ini
        source_paper_id = _make_paper_id(arxiv_id=arxiv_id)

        with driver.session() as session:
            # 3. Buat stub nodes untuk references + relasi CITES
            #    (source paper) -[:CITES]-> (referenced paper)
            for ref in references:
                ref_paper_id = _make_paper_id(
                    title=ref.title, year=ref.year, arxiv_id=ref.arxiv_id
                )
                # Create stub Paper node
                session.run(MERGE_PAPER, {
                    "paper_id":         ref_paper_id,
                    "title":            ref.title,
                    "abstract":         "",
                    "year":             ref.year,
                    "venue":            None,
                    "arxiv_id":         ref.arxiv_id,
                    "doi":              ref.doi,
                    "personality_tag":  None,
                    "confidence_score": 0.0,
                    "reasoning":        "",
                    "primary_category": None,
                    "embedding":        None,
                    "unresolved":       not ref.found_on_arxiv,
                })
                # Create CITES relationship
                session.run(MERGE_CITES, {
                    "source_paper_id": source_paper_id,
                    "target_paper_id": ref_paper_id,
                    "context":         ref.raw_text[:200],
                    "confidence":      1.0 if ref.found_on_arxiv else 0.7,
                    "resolved_via":    "semantic_scholar",
                })

            # 4. Buat stub nodes untuk citations + relasi CITES
            #    (citing paper) -[:CITES]-> (source paper)
            for cit in citations:
                cit_paper_id = _make_paper_id(
                    title=cit.title, year=cit.year, arxiv_id=cit.arxiv_id
                )
                # Create stub Paper node
                session.run(MERGE_PAPER, {
                    "paper_id":         cit_paper_id,
                    "title":            cit.title,
                    "abstract":         "",
                    "year":             cit.year,
                    "venue":            None,
                    "arxiv_id":         cit.arxiv_id,
                    "doi":              cit.doi,
                    "personality_tag":  None,
                    "confidence_score": 0.0,
                    "reasoning":        "",
                    "primary_category": None,
                    "embedding":        None,
                    "unresolved":       not cit.found_on_arxiv,
                })
                # Create CITES relationship (citing paper cites source)
                session.run(MERGE_CITES, {
                    "source_paper_id": cit_paper_id,
                    "target_paper_id": source_paper_id,
                    "context":         cit.raw_text[:200],
                    "confidence":      1.0 if cit.found_on_arxiv else 0.7,
                    "resolved_via":    "semantic_scholar",
                })

        total = len(references) + len(citations)
        log.info(f"✅ Expanded {arxiv_id}: {total} related papers added to graph")

        # Level 2 expansion: untuk top-5 most-cited references, fetch citations mereka juga
        if depth > 1:
            import asyncio
            # Sort references by citation count, take top 5
            top_refs = sorted(references, key=lambda x: x.citation_count, reverse=True)[:5]
            for ref in top_refs:
                log.info(f"🚀 Batch processing: recursive expansion for top-cited ref {ref.arxiv_id}")
                asyncio.create_task(_expand_references_background(ref.arxiv_id, depth=depth-1))

    except Exception as e:
        log.error(f"❌ Failed to expand references for {arxiv_id}: {e}")    