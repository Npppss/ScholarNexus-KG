# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from neo4j import GraphDatabase
import logging

from app.config.settings import settings
from app.routers import paper, arxiv, graph, search

logger = logging.getLogger(__name__)


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

    yield  # ← aplikasi berjalan di sini

    # Shutdown
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