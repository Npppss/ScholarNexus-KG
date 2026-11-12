# services/openalex_service.py
"""
OpenAlex API Integration for ScholarNexus KG.
OpenAlex is an open and comprehensive catalog of global scholarly papers,
offering free search, citation metrics, DOIs, and open-access PDF links.
"""
import httpx
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"
USER_AGENT = "ScholarNexus-KG/1.0 (https://github.com/scholarnexus; mailto:scholarnexus@example.org)"


def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    """Reconstruct continuous abstract string from OpenAlex inverted index format."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    try:
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join([w[1] for w in word_positions])
    except Exception as e:
        logger.warning(f"Failed to reconstruct OpenAlex abstract: {e}")
        return ""


class OpenAlexService:
    """Service to search and enrich scientific publications using OpenAlex API."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.headers = {"User-Agent": USER_AGENT}

    def search_works(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search OpenAlex for scholarly works matching query.
        Returns parsed list with titles, publication year, citations, and Open Access info.
        """
        if not query or not query.strip():
            return []

        url = f"{OPENALEX_BASE}/works"
        params = {
            "search": query.strip(),
            "per-page": min(max(1, limit), 25),
            "sort": "relevance_score:desc",
        }

        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])

            works = []
            for item in results:
                parsed = self._parse_work(item)
                if parsed:
                    works.append(parsed)

            logger.info(f"OpenAlex search for '{query}': found {len(works)} works.")
            return works

        except Exception as e:
            logger.error(f"OpenAlex search error for '{query}': {e}")
            return []

    def get_work_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific paper from OpenAlex using its DOI or OpenAlex ID."""
        if not doi:
            return None

        clean_doi = doi.strip().replace("https://doi.org/", "")
        url = f"{OPENALEX_BASE}/works/https://doi.org/{clean_doi}"

        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return self._parse_work(resp.json())
        except Exception as e:
            logger.warning(f"OpenAlex lookup failed for DOI '{doi}': {e}")
            return None

    def get_work_by_arxiv(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """Fetch OpenAlex paper details using ArXiv ID via DOI or filter."""
        if not arxiv_id:
            return None

        clean_id = arxiv_id.strip().replace("arxiv:", "").replace("ArXiv:", "")
        url_doi = f"{OPENALEX_BASE}/works/https://doi.org/10.48550/arxiv.{clean_id}"

        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                resp = client.get(url_doi)
                if resp.status_code == 200:
                    return self._parse_work(resp.json())

                # Fallback to general search if direct DOI lookup returns non-200
                search_url = f"{OPENALEX_BASE}/works"
                search_params = {"search": clean_id, "per-page": 1}
                search_resp = client.get(search_url, params=search_params)
                if search_resp.status_code == 200:
                    results = search_resp.json().get("results", [])
                    if results:
                        return self._parse_work(results[0])
            return None
        except Exception as e:
            logger.warning(f"OpenAlex lookup failed for ArXiv '{arxiv_id}': {e}")
            return None
            return None

    def _parse_work(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert raw OpenAlex JSON work to normalized ScholarNexus format."""
        if not item or not item.get("display_name"):
            return None

        ids = item.get("ids", {})
        doi = ids.get("doi") or item.get("doi")
        arxiv_raw = ids.get("arxiv")
        arxiv_id = None
        if arxiv_raw:
            arxiv_id = arxiv_raw.split("/")[-1].replace("abs/", "")

        # Extract authors
        authors = []
        for authorship in (item.get("authorships") or [])[:6]:
            author_obj = authorship.get("author", {})
            name = author_obj.get("display_name")
            if name:
                authors.append(name)

        # Primary location / PDF
        primary_loc = item.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        venue = source.get("display_name") or item.get("host_venue", {}).get("name")
        pdf_url = primary_loc.get("pdf_url") or item.get("open_access", {}).get("oa_url")

        # Reconstruct abstract
        abstract = reconstruct_abstract(item.get("abstract_inverted_index"))

        # Concepts / Topics
        topics = []
        for c in (item.get("concepts") or [])[:4]:
            t_name = c.get("display_name")
            if t_name:
                topics.append(t_name)

        return {
            "openalex_id": item.get("id"),
            "paper_id": f"openalex:{item.get('id', '').split('/')[-1]}",
            "title": item.get("display_name"),
            "year": item.get("publication_year"),
            "authors": authors,
            "venue": venue,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "citation_count": item.get("cited_by_count", 0),
            "abstract": abstract,
            "pdf_url": pdf_url,
            "is_oa": item.get("open_access", {}).get("is_oa", False),
            "topics": topics,
            "source": "OpenAlex Global Catalog"
        }


# Singleton
openalex_service = OpenAlexService()
