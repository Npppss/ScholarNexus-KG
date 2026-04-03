import json
import time
from typing import Optional
from services.arxiv_service import ArxivPaper, rate_limited
from services.cache_service import paper_cache
import json
import logging
from typing import Optional
from fastapi import Request

class PaperCache:
    """
    In-memory cache dengan TTL. Di production, ganti dengan Redis:
    self._store = redis.Redis(...)
    """
    def __init__(self, ttl_seconds: int = 7 * 24 * 3600):  # 7 hari default
        self._store: dict[str, dict] = {}
        self._ttl   = ttl_seconds

    def get(self, arxiv_id: str) -> Optional[dict]:
        entry = self._store.get(self._normalize_key(arxiv_id))
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            del self._store[self._normalize_key(arxiv_id)]
            return None
        return entry["data"]

    def set(self, arxiv_id: str, data: dict) -> None:
        self._store[self._normalize_key(arxiv_id)] = {
            "data":       data,
            "expires_at": time.time() + self._ttl,
            "cached_at":  time.time(),
        }

    def exists(self, arxiv_id: str) -> bool:
        return self.get(arxiv_id) is not None

    def _normalize_key(self, arxiv_id: str) -> str:
        """Strip versi dari ID: '2307.09288v2' → '2307.09288'"""
        return re.sub(r"v\d+$", "", arxiv_id.strip())

    @property
    def size(self) -> int:
        return len(self._store)


# Singleton
paper_cache = PaperCache()


class ArxivService:
    """
    Wrapper ArXiv API dengan cache + rate limiting + dua jalur akses:
    - fetch_by_id()    : Jalur B — langsung dari arxiv_id
    - fetch_by_title() : Jalur A — dari judul yang diparse di PDF
    - enrich_references(): Jalur A bulk — proses list resolved_refs
    """

    # ── Jalur B: Direct fetch by arxiv_id ─────────────────────────────────
    @rate_limited
    def fetch_by_id(self, arxiv_id: str) -> Optional[ArxivPaper]:
        """
        Fetch paper berdasarkan ArXiv ID.
        Contoh input: "1706.03762" atau "https://arxiv.org/abs/1706.03762"
        """
        arxiv_id = self._normalize_arxiv_id(arxiv_id)
        if not arxiv_id:
            logger.warning("Invalid arxiv_id format")
            return None

        # Cache check
        cached = paper_cache.get(arxiv_id)
        if cached:
            logger.debug(f"Cache HIT: {arxiv_id}")
            return ArxivPaper.from_dict(cached)

        # API call
        logger.info(f"Fetching arxiv_id={arxiv_id}")
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            results = list(search.results())
            if not results:
                logger.warning(f"ArXiv: no result for id={arxiv_id}")
                return None

            paper = ArxivPaper.from_arxiv_result(results[0])
            paper_cache.set(arxiv_id, paper.to_dict())
            return paper

        except Exception as e:
            logger.error(f"ArXiv API error for {arxiv_id}: {e}")
            return None


    # ── Jalur A: Fetch by title (dari referensi PDF) ──────────────────────
    @rate_limited
    def fetch_by_title(self, title: str, year_hint: Optional[str] = None
                       ) -> Optional[ArxivPaper]:
        """
        Cari paper berdasarkan judul.
        Pakai year_hint untuk mempersempit hasil jika judul ambigu.
        """
        if len(title) < 10:
            return None

        # Cache key untuk title search (hash judul)
        cache_key = "title_" + hashlib.md5(title.lower().encode()).hexdigest()[:12]
        cached = paper_cache.get(cache_key)
        if cached:
            return ArxivPaper.from_dict(cached)

        # Bersihkan judul untuk query
        query_title = re.sub(r"[^\w\s]", " ", title).strip()
        query = f'ti:"{query_title}"'
        if year_hint:
            # ArXiv tidak support filter tahun langsung,
            # tapi kita bisa tambah author sebagai konteks
            pass

        try:
            search = arxiv.Search(
                query      = query,
                max_results= 5,
                sort_by    = arxiv.SortCriterion.Relevance,
            )
            results = list(search.results())

            best = self._find_best_match(title, year_hint, results)
            if not best:
                return None

            paper = ArxivPaper.from_arxiv_result(best)
            paper_cache.set(paper.arxiv_id, paper.to_dict())
            paper_cache.set(cache_key, paper.to_dict())   # cache via title juga
            return paper

        except Exception as e:
            logger.error(f"ArXiv title search error: {e}")
            return None


    # ── Jalur A Bulk: Enrichment loop ────────────────────────────────────
    def enrich_references(
        self,
        resolved_refs: list,          # list[ResolvedReference] dari ref_resolver.py
        progress_callback=None,
    ) -> dict:
        """
        Proses semua resolved_refs secara berurutan (respek rate limit).
        Mengembalikan stats + list ArxivPaper yang berhasil diambil.
        """
        enriched:   list[ArxivPaper] = []
        failed:     list[dict]       = []
        skipped:    int              = 0

        for i, ref in enumerate(resolved_refs):
            if progress_callback:
                progress_callback(i, len(resolved_refs), ref.title or "?")

            # Prioritas: pakai arxiv_id jika sudah ada dari Stage 4a
            paper = None
            if ref.arxiv_id:
                paper = self.fetch_by_id(ref.arxiv_id)
            elif ref.title:
                paper = self.fetch_by_title(ref.title, ref.year)

            if paper:
                enriched.append(paper)
            elif ref.title:
                failed.append({
                    "title": ref.title,
                    "year":  ref.year,
                    "raw":   ref.raw_text[:100],
                })
            else:
                skipped += 1

        return {
            "enriched":       enriched,
            "failed":         failed,
            "skipped":        skipped,
            "total":          len(resolved_refs),
            "success_rate":   len(enriched) / max(len(resolved_refs), 1),
        }


    # ── Helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _normalize_arxiv_id(raw: str) -> Optional[str]:
        """
        Normalisasi berbagai format input ke bare arxiv_id.
        Input bisa berupa:
          "1706.03762"
          "https://arxiv.org/abs/1706.03762"
          "https://arxiv.org/pdf/1706.03762v2"
          "arxiv:1706.03762"
        """
        raw = raw.strip()
        # Ekstrak dari URL
        url_match = re.search(
            r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+(?:v\d+)?)", raw
        )
        if url_match:
            raw = url_match.group(1)

        # Strip prefix "arxiv:"
        raw = re.sub(r"^arxiv:", "", raw, flags=re.IGNORECASE)

        # Strip versi akhir (v2, v3, ...)
        raw = re.sub(r"v\d+$", "", raw)

        # Validasi format: YYMM.NNNNN atau old format HEPPH/0001001
        if re.match(r"^\d{4}\.\d{4,5}$", raw):
            return raw
        if re.match(r"^[a-z\-]+/\d{7}$", raw, re.IGNORECASE):
            return raw

        return None

    @staticmethod
    def _find_best_match(
        query_title: str,
        year_hint:   Optional[str],
        candidates:  list[arxiv.Result]
    ) -> Optional[arxiv.Result]:
        """
        Dari beberapa kandidat hasil search, pilih yang paling cocok
        berdasarkan similarity judul + kecocokan tahun.
        """
        if not candidates:
            return None

        scored = []
        for result in candidates:
            title_sim = _jaccard_similarity(query_title, result.title)

            # Bonus score jika tahun cocok
            year_bonus = 0.0
            if year_hint:
                try:
                    if int(year_hint) == result.published.year:
                        year_bonus = 0.1
                except (ValueError, AttributeError):
                    pass

            scored.append((title_sim + year_bonus, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_result = scored[0]

        # Threshold: jika similarity terlalu rendah, jangan return
        SIMILARITY_THRESHOLD = 0.55
        if best_score < SIMILARITY_THRESHOLD:
            logger.debug(
                f"Best match score {best_score:.2f} below threshold "
                f"for '{query_title[:50]}'"
            )
            return None

        return best_result


def _jaccard_similarity(a: str, b: str) -> float:
    """Token-level Jaccard similarity, case-insensitive, ignore stopwords."""
    STOPWORDS = {"a","an","the","of","in","on","for","and","to","with","via","is"}
    tokens_a = {t for t in a.lower().split() if t not in STOPWORDS}
    tokens_b = {t for t in b.lower().split() if t not in STOPWORDS}
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


# Singleton service
arxiv_service = ArxivService()

logger = logging.getLogger(__name__)


class RedisCacheService:
    """
    Production cache menggunakan Redis.
    Dipanggil via app.state.redis yang diinisialisasi di lifespan().
    """

    def __init__(self, request: Request):
        self._redis = request.app.state.redis
        self._ttl   = 7 * 24 * 3600   # 7 hari default

    async def get(self, key: str) -> Optional[dict]:
        try:
            raw = await self._redis.get(self._normalize(key))
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.warning(f"Cache GET error for {key}: {e}")
            return None

    async def set(self, key: str, data: dict, ttl: int = None) -> bool:
        try:
            await self._redis.setex(
                self._normalize(key),
                ttl or self._ttl,
                json.dumps(data, default=str),
            )
            return True
        except Exception as e:
            logger.warning(f"Cache SET error for {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self._redis.exists(self._normalize(key)))
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        try:
            await self._redis.delete(self._normalize(key))
            return True
        except Exception:
            return False

    async def get_stats(self) -> dict:
        """Statistik penggunaan cache untuk monitoring."""
        try:
            info = await self._redis.info("stats")
            return {
                "hits":   info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "keys":   await self._redis.dbsize(),
            }
        except Exception:
            return {}

    @staticmethod
    def _normalize(key: str) -> str:
        import re
        return "kg:" + re.sub(r"v\d+$", "", key.strip())