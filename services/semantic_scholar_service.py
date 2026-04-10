# services/semantic_scholar_service.py
"""
Fetch citation data from Semantic Scholar API (free, no API key required).
Used to auto-discover related papers when a new paper is saved.
"""
import httpx
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"

# Fields we request for each referenced/citing paper
PAPER_FIELDS = "externalIds,title,year,authors,citationCount"


@dataclass
class RelatedPaper:
    """Lightweight representation of a related paper from Semantic Scholar."""
    title:       str
    year:        Optional[int]   = None
    arxiv_id:    Optional[str]   = None
    doi:         Optional[str]   = None
    authors:     list[str]       = None
    citation_count: int          = 0
    s2_paper_id: Optional[str]   = None
    raw_text:    str              = ""
    found_on_arxiv: bool         = False

    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        self.found_on_arxiv = bool(self.arxiv_id)


class SemanticScholarService:
    """Fetch references and citations from Semantic Scholar."""

    def __init__(self, timeout: float = 15.0, max_results: int = 30):
        self.timeout     = timeout
        self.max_results = max_results

    def get_references_and_citations(
        self,
        arxiv_id: str,
    ) -> dict:
        """
        Fetch both references (papers this paper cites) and citations
        (papers that cite this paper) from Semantic Scholar.

        Returns: {"references": [...], "citations": [...]}
        """
        s2_id = f"ArXiv:{arxiv_id}"
        references = self._fetch_references(s2_id)
        citations  = self._fetch_citations(s2_id)

        return {
            "references": references,
            "citations":  citations,
        }

    def _fetch_references(self, s2_id: str) -> list[RelatedPaper]:
        """Papers that this paper cites (its bibliography)."""
        url = f"{S2_BASE}/paper/{s2_id}/references"
        params = {
            "fields": PAPER_FIELDS,
            "limit":  self.max_results,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json().get("data", [])

            papers = []
            for entry in data:
                cited = entry.get("citedPaper", {})
                if not cited or not cited.get("title"):
                    continue
                papers.append(self._to_related_paper(cited))
            logger.info(f"Semantic Scholar: {len(papers)} references for {s2_id}")
            return papers

        except Exception as e:
            logger.warning(f"Semantic Scholar references failed for {s2_id}: {e}")
            return []

    def _fetch_citations(self, s2_id: str) -> list[RelatedPaper]:
        """Papers that cite this paper."""
        url = f"{S2_BASE}/paper/{s2_id}/citations"
        params = {
            "fields": PAPER_FIELDS,
            "limit":  self.max_results,
        }
        try:
            # Small delay to respect rate limits
            time.sleep(1.0)

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json().get("data", [])

            papers = []
            for entry in data:
                citing = entry.get("citingPaper", {})
                if not citing or not citing.get("title"):
                    continue
                papers.append(self._to_related_paper(citing))

            # Sort by citation count — most impactful first
            papers.sort(key=lambda p: p.citation_count, reverse=True)
            logger.info(f"Semantic Scholar: {len(papers)} citations for {s2_id}")
            return papers

        except Exception as e:
            logger.warning(f"Semantic Scholar citations failed for {s2_id}: {e}")
            return []

    @staticmethod
    def _to_related_paper(data: dict) -> RelatedPaper:
        """Convert S2 API response to RelatedPaper."""
        ext_ids  = data.get("externalIds") or {}
        authors  = [a.get("name", "") for a in (data.get("authors") or [])]
        arxiv_id = ext_ids.get("ArXiv")

        return RelatedPaper(
            title          = data.get("title", "Unknown"),
            year           = data.get("year"),
            arxiv_id       = arxiv_id,
            doi            = ext_ids.get("DOI"),
            authors        = authors[:5],  # limit to first 5
            citation_count = data.get("citationCount", 0),
            s2_paper_id    = data.get("paperId"),
            raw_text       = data.get("title", ""),
            found_on_arxiv = bool(arxiv_id),
        )


# Singleton
semantic_scholar_service = SemanticScholarService()
