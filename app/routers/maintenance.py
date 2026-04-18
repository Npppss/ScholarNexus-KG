from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from services.maintenance_service import maintenance_service

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])

class MaintenanceResponse(BaseModel):
    status: str
    message: str

def run_all_pipelines():
    """Background task function to run all maintenance pipelines."""
    embedded = maintenance_service.run_re_embedding_pipeline()
    deleted = maintenance_service.run_dead_reference_cleanup()
    deduped = maintenance_service.run_deduplication_pipeline()
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Maintenance] Embedded {embedded} papers, cleaned {deleted} dead references, deduplicated {deduped} nodes.")

@router.post("/run-pipeline", response_model=MaintenanceResponse)
async def run_maintenance_pipeline(background_tasks: BackgroundTasks):
    """
    Trigger the Data Pipeline:
    1. Re-embed old papers
    2. Clean up dead references
    3. Deduplicate
    Runs as a background task.
    """
    background_tasks.add_task(run_all_pipelines)
    return MaintenanceResponse(
        status="success",
        message="Maintenance pipeline started in the background."
    )
