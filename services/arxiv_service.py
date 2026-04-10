import time
import re
import hashlib
import arxiv
from dataclasses import dataclass, field
from typing import Optional
from functools import wraps
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArxivPaper:
    """Representasi terstruktur satu paper dari ArXiv API."""
    arxiv_id:     str
    title:        str
    authors:      list[str]
    abstract:     str
    published:    str                   # ISO date string "YYYY-MM-DD"
    updated:      str
    categories:   list[str]            # e.g. ["cs.CL", "cs.LG"]
    primary_cat:  str                  # e.g. "cs.CL"
    doi:          Optional[str] = None
    journal_ref:  Optional[str] = None
    pdf_url:      Optional[str] = None
    comment:      Optional[str] = None  # sering berisi "Accepted to NeurIPS 2023"

    # Derived fields — kita isi sendiri
    venue_parsed: Optional[str] = None  # hasil parse dari journal_ref + comment
    year:         Optional[int] = None


    @classmethod
    def from_arxiv_result(cls, result: arxiv.Result) -> "ArxivPaper":
        """Factory method dari objek arxiv.Result."""
        arxiv_id = result.entry_id.split("/abs/")[-1]  # "2307.09288v2" → strip version
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)       # "2307.09288"

        paper = cls(
            arxiv_id    = arxiv_id,
            title       = result.title.strip(),
            authors     = [a.name for a in result.authors],
            abstract    = result.summary.strip().replace("\n", " "),
            published   = result.published.strftime("%Y-%m-%d"),
            updated     = result.updated.strftime("%Y-%m-%d"),
            categories  = result.categories,
            primary_cat = result.primary_category,
            doi         = result.doi,
            journal_ref = result.journal_ref,
            pdf_url     = result.pdf_url,
            comment     = result.comment,
            year        = result.published.year,
        )
        paper.venue_parsed = _parse_venue(result.journal_ref, result.comment)
        return paper

    def to_dict(self) -> dict:
        """Serialisasi untuk cache storage."""
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "ArxivPaper":
        """Deserialisasi dari cache."""
        return cls(**d)


def _parse_venue(journal_ref: Optional[str], comment: Optional[str]) -> Optional[str]:
    """
    Ekstrak venue dari journal_ref atau comment.
    Contoh input: "Accepted at NeurIPS 2023" → "NeurIPS 2023"
    """
    target = journal_ref or comment or ""
    if not target:
        return None

    # Cari konferensi/jurnal terkenal
    venue_patterns = [
        r"(NeurIPS|ICML|ICLR|ACL|EMNLP|NAACL|CVPR|ICCV|ECCV|AAAI|IJCAI"
        r"|KDD|WWW|SIGIR|RecSys|CIKM)\s*(?:20\d{2})?",
        r"(Nature|Science|PNAS|PLOS ONE|arXiv)\s*(?:20\d{2})?",
        r"(IEEE Trans\.|Journal of|Transactions on)\s*[\w\s]+",
    ]
    for pattern in venue_patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return target[:80] if len(target) > 80 else target

# ─── Rate Limiter ───────────────────────────────────────────────────────────

class RateLimiter:
    """
    Token bucket rate limiter.
    ArXiv policy: max 3 req/sec, harap pakai delay ≥ 3 detik antar burst.
    """
    def __init__(self, calls_per_second: float = 3.0, burst_size: int = 5):
        self.min_interval = 1.0 / calls_per_second
        self.burst_size   = burst_size
        self._tokens      = burst_size
        self._last_check  = time.monotonic()

    def acquire(self):
        """Block hingga ada token tersedia. Thread-safe via GIL."""
        now     = time.monotonic()
        elapsed = now - self._last_check
        self._last_check = now

        # Isi ulang token berdasarkan waktu yang berlalu
        self._tokens = min(
            self.burst_size,
            self._tokens + elapsed / self.min_interval
        )

        if self._tokens >= 1:
            self._tokens -= 1
        else:
            # Hitung waktu tunggu dan sleep
            sleep_time = self.min_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            self._tokens = 0


# Singleton rate limiter — shared across all ArxivService instances
_rate_limiter = RateLimiter(calls_per_second=3.0)

def rate_limited(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        _rate_limiter.acquire()
        return func(*args, **kwargs)
    return wrapper

# 4. Definisi Class Utama
class ArxivService:
    def __init__(self):
        self.client = arxiv.Client()

    @rate_limited  # Sekarang Python sudah kenal fungsi ini
    def fetch_by_id(self, arxiv_id: str) -> Optional[ArxivPaper]:
        clean_id = re.sub(r"v\d+$", "", arxiv_id.strip())
        try:
            search = arxiv.Search(id_list=[clean_id])
            results = list(self.client.results(search))
            return ArxivPaper.from_arxiv_result(results[0]) if results else None
        except Exception as e:
            logger.error(f"ArXiv Error: {e}")
            return None

# 5. Export Singleton (Yang dicari oleh Routers)
arxiv_service = ArxivService()