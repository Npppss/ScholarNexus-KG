from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from services.vector_service import generate_embedding
from services.graph_service import graph_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

class SmartSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    limit: int = 20

@router.post("/smart")
async def smart_search(req: SmartSearchRequest):
    """
    AI-Powered Paper Discovery (GraphRAG).
    Combines Vector Search (by Gemini embeddings) with Graph Traversal (2-hop citations)
    and dynamically re-ranks the results based on similarity, citation popularity, and recency.
    """
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty.")
        
    try:
        # Step 1: Generate embedding for the user intent
        query_embedding = generate_embedding(req.query)
        
        # Step 2: Query the knowledge graph using our smart GraphRAG logic
        results = graph_service.smart_graphrag_search(
            query_embedding=query_embedding,
            top_k=req.top_k,
            limit=req.limit
        )
        
        return {
            "query": req.query,
            "count": len(results),
            "results": results,
            "strategy": "GraphRAG (Vector + Citation Expansion + Re-rank)"
        }
    except Exception as e:
        log.error(f"Smart Search failed: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Smart Search failed: {str(e)}")
