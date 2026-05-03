import asyncio
import json
import logging
import time
from collections import deque
from threading import Lock
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.config.settings import settings
from services.cognitive.spreading_activation import CognitiveSearch

router = APIRouter(tags=["cognitive"])
logger = logging.getLogger(__name__)
_METRIC_LOCK = Lock()
_LATENCY_SAMPLES = deque(maxlen=1000)
_METRICS = {
    "requests_total": 0,
    "cache_hits": 0,
    "cache_misses": 0,
}
_REDIS_METRIC_HASH_KEY = "cognitive:metrics:v1"
_REDIS_METRIC_LAT_KEY = "cognitive:metrics:v1:latencies"
_REDIS_METRIC_LAT_MAX = 1000
_PROFILE_PRESETS = {
    "fast": {
        "decay": 0.55,
        "threshold": 0.08,
        "max_depth": 4,
        "max_results": 20,
        "max_expansions": 1500,
    },
    "balanced": {
        "decay": 0.6,
        "threshold": 0.05,
        "max_depth": 5,
        "max_results": 30,
        "max_expansions": 3000,
    },
    "deep": {
        "decay": 0.7,
        "threshold": 0.02,
        "max_depth": 6,
        "max_results": 50,
        "max_expansions": 8000,
    },
}


def _build_cache_key(
    paper_id: str,
    decay: float,
    threshold: float,
    max_depth: int,
    max_results: int,
    max_expansions: int,
) -> str:
    normalized_id = paper_id.strip().lower()
    return (
        f"cognitive:v2:{normalized_id}:"
        f"{decay:.4f}:{threshold:.4f}:{max_depth}:{max_results}:{max_expansions}"
    )


def _record_metrics(cache_hit: bool, duration_ms: float) -> None:
    with _METRIC_LOCK:
        _METRICS["requests_total"] += 1
        if cache_hit:
            _METRICS["cache_hits"] += 1
        else:
            _METRICS["cache_misses"] += 1
        _LATENCY_SAMPLES.append(float(duration_ms))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    index = int((len(values_sorted) - 1) * percentile)
    return round(values_sorted[index], 2)


async def _record_metrics_redis(redis, cache_hit: bool, duration_ms: float) -> None:
    try:
        await redis.hincrby(_REDIS_METRIC_HASH_KEY, "requests_total", 1)
        if cache_hit:
            await redis.hincrby(_REDIS_METRIC_HASH_KEY, "cache_hits", 1)
        else:
            await redis.hincrby(_REDIS_METRIC_HASH_KEY, "cache_misses", 1)
        await redis.lpush(_REDIS_METRIC_LAT_KEY, float(duration_ms))
        await redis.ltrim(_REDIS_METRIC_LAT_KEY, 0, _REDIS_METRIC_LAT_MAX - 1)
    except Exception as e:
        logger.warning(f"[Cognitive] Redis metrics write failed: {e}")


async def _read_metrics_redis(redis) -> dict | None:
    try:
        raw_counts = await redis.hgetall(_REDIS_METRIC_HASH_KEY)
        raw_latencies = await redis.lrange(_REDIS_METRIC_LAT_KEY, 0, _REDIS_METRIC_LAT_MAX - 1)
        requests_total = int(raw_counts.get("requests_total", 0))
        cache_hits = int(raw_counts.get("cache_hits", 0))
        cache_misses = int(raw_counts.get("cache_misses", 0))
        samples = [float(v) for v in raw_latencies] if raw_latencies else []
        return {
            "requests_total": requests_total,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "samples": samples,
        }
    except Exception as e:
        logger.warning(f"[Cognitive] Redis metrics read failed: {e}")
        return None


def _resolve_search_params(
    profile: str,
    decay: Optional[float],
    threshold: Optional[float],
    max_depth: Optional[int],
    max_results: Optional[int],
    max_expansions: Optional[int],
) -> dict:
    if profile not in _PROFILE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid profile '{profile}'. Use one of: {', '.join(_PROFILE_PRESETS.keys())}.",
        )

    preset = _PROFILE_PRESETS[profile]
    return {
        "profile": profile,
        "decay": float(decay) if decay is not None else preset["decay"],
        "threshold": float(threshold) if threshold is not None else preset["threshold"],
        "max_depth": int(max_depth) if max_depth is not None else preset["max_depth"],
        "max_results": int(max_results) if max_results is not None else preset["max_results"],
        "max_expansions": int(max_expansions)
        if max_expansions is not None
        else preset["max_expansions"],
    }


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
    Spreading Activation search from a seed paper.
    Returns serendipitous discoveries ranked by activation signal.
    """
    resolved = _resolve_search_params(
        profile=profile,
        decay=decay,
        threshold=threshold,
        max_depth=max_depth,
        max_results=max_results,
        max_expansions=max_expansions,
    )

    engine = CognitiveSearch(
        decay_factor=resolved["decay"],
        threshold=resolved["threshold"],
        max_depth=resolved["max_depth"],
        max_expansions=resolved["max_expansions"],
    )
    started_at = time.perf_counter()
    cache_key = _build_cache_key(
        paper_id,
        resolved["decay"],
        resolved["threshold"],
        resolved["max_depth"],
        resolved["max_results"],
        resolved["max_expansions"],
    )
    redis = getattr(request.app.state, "redis", None)

    if redis is not None and not no_cache:
        try:
            cached = await redis.get(cache_key)
            if cached:
                payload = json.loads(cached)
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                payload["meta"] = {
                    **payload.get("meta", {}),
                    "cache_hit": True,
                    "cache_bypassed": False,
                    "profile": resolved["profile"],
                    "duration_ms": duration_ms,
                }
                _record_metrics(cache_hit=True, duration_ms=duration_ms)
                if redis is not None:
                    await _record_metrics_redis(redis, cache_hit=True, duration_ms=duration_ms)
                logger.info(
                    "[Cognitive] cache_hit=true seed=%s activated=%s",
                    payload.get("seed", paper_id),
                    payload.get("total_activated", 0),
                )
                return payload
        except Exception as e:
            logger.warning(f"[Cognitive] Redis cache read failed: {e}")

    result = await asyncio.to_thread(engine.activate, paper_id, resolved["max_results"])
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    result["meta"] = {
        "cache_hit": False,
        "cache_bypassed": bool(no_cache),
        "profile": resolved["profile"],
        "duration_ms": duration_ms,
    }
    _record_metrics(cache_hit=False, duration_ms=duration_ms)
    if redis is not None:
        await _record_metrics_redis(redis, cache_hit=False, duration_ms=duration_ms)

    if redis is not None and not no_cache:
        try:
            ttl_seconds = max(60, int(settings.redis_cache_ttl_days) * 24 * 3600)
            await redis.setex(cache_key, ttl_seconds, json.dumps(result, default=str))
        except Exception as e:
            logger.warning(f"[Cognitive] Redis cache write failed: {e}")

    logger.info(
        "[Cognitive] cache_hit=false seed=%s activated=%s duration_ms=%s",
        result.get("seed", paper_id),
        result.get("total_activated", 0),
        result["meta"]["duration_ms"],
    )
    return result


@router.get("/cognitive/metrics")
async def cognitive_metrics(request: Request):
    redis = getattr(request.app.state, "redis", None)
    redis_metrics = await _read_metrics_redis(redis) if redis is not None else None

    if redis_metrics is not None:
        requests_total = redis_metrics["requests_total"]
        cache_hits = redis_metrics["cache_hits"]
        cache_misses = redis_metrics["cache_misses"]
        samples = redis_metrics["samples"]
    else:
        with _METRIC_LOCK:
            requests_total = _METRICS["requests_total"]
            cache_hits = _METRICS["cache_hits"]
            cache_misses = _METRICS["cache_misses"]
            samples = list(_LATENCY_SAMPLES)

    cache_hit_rate = (cache_hits / requests_total) if requests_total else 0.0
    avg_latency = (sum(samples) / len(samples)) if samples else 0.0
    return {
        "requests_total": requests_total,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "cache_hit_rate": round(cache_hit_rate, 4),
        "latency_ms": {
            "avg": round(avg_latency, 2),
            "p50": _percentile(samples, 0.50),
            "p95": _percentile(samples, 0.95),
            "max": round(max(samples), 2) if samples else 0.0,
            "samples": len(samples),
        },
    }


@router.post("/cognitive/metrics/reset")
async def reset_cognitive_metrics(request: Request):
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.delete(_REDIS_METRIC_HASH_KEY)
            await redis.delete(_REDIS_METRIC_LAT_KEY)
        except Exception as e:
            logger.warning(f"[Cognitive] Redis metrics reset failed: {e}")

    with _METRIC_LOCK:
        _METRICS["requests_total"] = 0
        _METRICS["cache_hits"] = 0
        _METRICS["cache_misses"] = 0
        _LATENCY_SAMPLES.clear()
    return {"status": "ok", "message": "Cognitive metrics have been reset."}
