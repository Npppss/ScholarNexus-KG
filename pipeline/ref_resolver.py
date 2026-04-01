import re
import arxiv
from dataclasses import dataclass

@dataclass
class ResolvedReference:
    raw_text:   str
    title:      str | None = None
    authors:    list[str]  = None
    year:       str | None = None
    arxiv_id:   str | None = None
    doi:        str | None = None
    found_on_arxiv: bool   = False


def resolve_references(raw_refs: list[str]) -> list[ResolvedReference]:
    """
    Untuk setiap referensi mentah:
    1. Ekstrak title + authors pakai regex heuristik
    2. Cari di ArXiv API
    3. Return resolved object
    """
    resolved = []
    for raw in raw_refs:
        ref = ResolvedReference(raw_text=raw)

        # Heuristik: tahun biasanya dalam kurung (2017) atau di awal
        year_match = re.search(r"\b(19|20)\d{2}\b", raw)
        if year_match:
            ref.year = year_match.group()

        # Heuristik title: teks setelah tahun atau dalam tanda kutip
        title_match = re.search(
            r'"([^"]{15,120})"|'     # judul dalam tanda kutip
            r'(?:20\d{2}[).]\s*)(.{15,120}?)(?:\.|In\s)',  # setelah tahun
            raw
        )
        if title_match:
            ref.title = (title_match.group(1) or title_match.group(2) or "").strip()

        # Cari ArXiv jika ada title
        if ref.title and len(ref.title) > 10:
            ref = _search_arxiv(ref)

        resolved.append(ref)
    return resolved


def _search_arxiv(ref: ResolvedReference) -> ResolvedReference:
    """Lookup ArXiv API menggunakan judul paper."""
    try:
        search = arxiv.Search(
            query      = ref.title,
            max_results= 3,
            sort_by    = arxiv.SortCriterion.Relevance
        )
        for result in search.results():
            # Cek kesamaan judul (simple token overlap)
            if _title_similarity(ref.title, result.title) > 0.7:
                ref.arxiv_id = result.entry_id.split("/")[-1]
                ref.authors  = [a.name for a in result.authors[:5]]
                ref.year     = str(result.published.year)
                ref.doi      = result.doi
                ref.found_on_arxiv = True
                break
    except Exception:
        pass  # Jangan crash pipeline karena satu referensi gagal
    return ref


def _title_similarity(t1: str, t2: str) -> float:
    """Token-level Jaccard similarity."""
    s1 = set(t1.lower().split())
    s2 = set(t2.lower().split())
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)