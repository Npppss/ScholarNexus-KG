# app/routers/scholar.py
"""
Router for OpenAlex and Semantic Scholar external literature integration.
Enables global scholarly search, external citation metrics, and graph ingestion.
"""
import asyncio
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.openalex_service import openalex_service
from services.semantic_scholar_service import semantic_scholar_service
from services.graph_service import graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scholar", tags=["scholar"])


class OpenAlexImportRequest(BaseModel):
    paper_id: Optional[str] = None
    title: str
    year: Optional[int] = None
    authors: Optional[List[str]] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    abstract: Optional[str] = None
    topics: Optional[List[str]] = None
    citation_count: Optional[int] = 0


@router.get("/openalex/search")
async def search_openalex(
    query: str = Query(..., min_length=2, description="Kata kunci pencarian literatur global"),
    limit: int = Query(8, ge=1, le=25, description="Jumlah hasil maksimal"),
):
    """
    Cari literatur ilmiah dari katalog global OpenAlex (250+ juta naskah).
    Mengembalikan judul, tahun, penulis, jumlah sitasi global, DOI, dan tautan PDF Open Access.
    """
    try:
        results = await asyncio.to_thread(openalex_service.search_works, query, limit)
        return {"query": query, "count": len(results), "papers": results}
    except Exception as e:
        logger.error(f"OpenAlex search endpoint error: {e}")
        raise HTTPException(502, f"Gagal menghubungi OpenAlex API: {str(e)}")


@router.get("/paper/{paper_identifier}/external-metrics")
async def get_external_metrics(paper_identifier: str):
    """
    Ambil metrik sitasi global dan data eksternal dari OpenAlex dan Semantic Scholar
    berdasarkan ArXiv ID atau DOI.
    """
    clean_id = paper_identifier.replace("arxiv:", "").replace("ArXiv:", "").strip()
    
    # Jalankan query paralel ke OpenAlex dan Semantic Scholar
    async def fetch_openalex():
        return await asyncio.to_thread(openalex_service.get_work_by_arxiv, clean_id)

    async def fetch_s2():
        return await asyncio.to_thread(semantic_scholar_service.get_references_and_citations, clean_id)

    openalex_data, s2_data = await asyncio.gather(
        fetch_openalex(),
        fetch_s2(),
        return_exceptions=True
    )

    oa_res = openalex_data if not isinstance(openalex_data, Exception) else None
    s2_res = s2_data if not isinstance(s2_data, Exception) else {}

    s2_citations = s2_res.get("citations", []) if isinstance(s2_res, dict) else []
    s2_references = s2_res.get("references", []) if isinstance(s2_res, dict) else []

    return {
        "identifier": clean_id,
        "openalex": {
            "global_citation_count": oa_res.get("citation_count", 0) if oa_res else None,
            "doi": oa_res.get("doi") if oa_res else None,
            "venue": oa_res.get("venue") if oa_res else None,
            "is_oa": oa_res.get("is_oa", False) if oa_res else False,
            "pdf_url": oa_res.get("pdf_url") if oa_res else None,
        },
        "semantic_scholar": {
            "citations_found": len(s2_citations),
            "references_found": len(s2_references),
        }
    }


@router.post("/openalex/import")
async def import_openalex_to_graph(payload: OpenAlexImportRequest):
    """
    Impor dokumen dari OpenAlex langsung ke dalam basis data Knowledge Graph Neo4j.
    Dokumen ini selanjutnya dapat divisualisasikan dan dianalisis perannya.
    """
    try:
        paper_dict = payload.model_dump()
        result = await asyncio.to_thread(graph_service.import_openalex_paper, paper_dict)
        return {
            "status": "success",
            "message": "Dokumen berhasil diimpor ke Knowledge Graph",
            "paper": result
        }
    except Exception as e:
        logger.error(f"Failed to import OpenAlex paper: {e}")
        raise HTTPException(500, f"Gagal mengimpor dokumen ke graf: {str(e)}")

