import asyncio
import logging
from fastapi import APIRouter, Query
from pydantic import BaseModel
from services.maintenance_service import maintenance_service

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])
logger = logging.getLogger(__name__)


class MaintenanceResponse(BaseModel):
    status: str
    message: str


def run_all_pipelines() -> dict:
    """Run all maintenance pipelines and return counters."""
    embedded = maintenance_service.run_re_embedding_pipeline()
    deleted = maintenance_service.run_dead_reference_cleanup()
    deduped = maintenance_service.run_deduplication_pipeline()
    logger.info(
        "[Maintenance] Embedded %s papers, cleaned %s dead references, deduplicated %s nodes.",
        embedded,
        deleted,
        deduped,
    )
    return {"embedded": embedded, "deleted": deleted, "deduped": deduped}


async def _run_all_pipelines_async() -> dict:
    return await asyncio.to_thread(run_all_pipelines)


@router.post("/run-pipeline")
async def run_maintenance_pipeline(background: bool = Query(True)):
    """
    Trigger the Data Pipeline:
    1. Re-embed old papers
    2. Clean up dead references
    3. Deduplicate
    Runs in background or synchronously based on `background` query param.
    """
    if background:
        asyncio.create_task(_run_all_pipelines_async())
        return MaintenanceResponse(
            status="success",
            message="Maintenance pipeline started in background task.",
        )

    result = await _run_all_pipelines_async()
    return {
        "status": "success",
        "message": (
            f"Maintenance completed. Embedded {result['embedded']} papers, "
            f"cleaned {result['deleted']} dead references, deduplicated {result['deduped']} nodes."
        ),
        "result": result,
    }
