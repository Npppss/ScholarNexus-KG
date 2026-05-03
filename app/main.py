# app/main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from neo4j import GraphDatabase
import logging

from app.config.settings import settings
from app.routers import paper, arxiv, graph, search, maintenance, cognitive
from services.maintenance_service import maintenance_service

logger = logging.getLogger(__name__)

MAINTENANCE_INTERVAL_SECONDS = 3600


async def scheduled_maintenance_worker(stop_event: asyncio.Event):
    """Periodic worker to keep graph data healthy while API is running."""
    while not stop_event.is_set():
        try:
            pending_embeddings = await asyncio.to_thread(
                maintenance_service.count_pending_embeddings
            )
            orphan_stubs = await asyncio.to_thread(
                maintenance_service.count_orphan_stubs
            )

            if pending_embeddings > 0 or orphan_stubs > 0:
                embedded = await asyncio.to_thread(
                    maintenance_service.run_re_embedding_pipeline
                )
                deleted = await asyncio.to_thread(
                    maintenance_service.run_dead_reference_cleanup
                )
                deduped = await asyncio.to_thread(
                    maintenance_service.run_deduplication_pipeline
                )
                logger.info(
                    "[Maintenance] Scheduled run completed: embedded=%s, cleaned=%s, deduped=%s",
                    embedded,
                    deleted,
                    deduped,
                )
            else:
                logger.debug(
                    "[Maintenance] Scheduled check skipped (no pending embeddings/dead references)."
                )
        except Exception as e:
            logger.error(f"[Maintenance] Scheduled worker failed: {e}", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=MAINTENANCE_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: verifikasi koneksi ke Neo4j dan Redis.
    Shutdown: tutup semua koneksi dengan bersih.
    """
    logger.info("Starting KG_personality API...")

    # ── Verifikasi Neo4j ──────────────────────────────────────────────────
    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password)
        )
        driver.verify_connectivity()
        app.state.neo4j = driver
        logger.info("Neo4j connected.")
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")
        raise

    # ── Verifikasi Redis ──────────────────────────────────────────────────
    try:
        redis = await aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await redis.ping()
        app.state.redis = redis
        logger.info("Redis connected.")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    # Start periodic maintenance worker (single process/single worker assumption).
    app.state.maintenance_stop_event = asyncio.Event()
    app.state.maintenance_task = asyncio.create_task(
        scheduled_maintenance_worker(app.state.maintenance_stop_event)
    )
    logger.info("Scheduled maintenance worker started.")

    yield  # ← aplikasi berjalan di sini

    # Shutdown
    app.state.maintenance_stop_event.set()
    app.state.maintenance_task.cancel()
    try:
        await app.state.maintenance_task
    except asyncio.CancelledError:
        pass

    app.state.neo4j.close()
    await app.state.redis.aclose()
    logger.info("Connections closed.")


app = FastAPI(
    title       = "KG_personality API",
    description = "Knowledge Graph for Academic Paper Personality Mapping",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(paper.router)
app.include_router(arxiv.router)
app.include_router(graph.router)
app.include_router(search.router)
app.include_router(maintenance.router)
app.include_router(cognitive.router)


# ── Health check endpoint (dipakai Docker healthcheck) ────────────────────
@app.get("/health", tags=["system"])
async def health():
    checks = {}

    # Neo4j
    try:
        app.state.neo4j.verify_connectivity()
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"

    # Redis
    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "services": checks, "version": "1.0.0"}
