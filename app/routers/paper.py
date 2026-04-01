from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import tempfile, os

from pipeline.pdf_extractor    import extract_pdf
from pipeline.personality_tagger import run_extraction_pipeline
from pipeline.ref_resolver     import resolve_references
from services.vector_service   import generate_embedding
from services.graph_service    import upsert_paper_to_graph

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    """
    Endpoint utama: terima PDF → jalankan full pipeline → simpan ke Neo4j.
    Returns: paper_id + personality_tag + graph stats.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    # Simpan ke temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # ── Stage 1 & 2: Parse PDF ────────────────────
        paper = extract_pdf(tmp_path)

        # ── Stage 3: LLM Extraction ──────────────────
        extraction = run_extraction_pipeline(paper)

        # ── Stage 4a: Resolve References ─────────────
        resolved_refs = resolve_references(paper.references_raw)

        # ── Stage 4b: Generate Embedding ─────────────
        embed_text = f"{paper.title}. {paper.sections.get('abstract','')}"
        embedding  = generate_embedding(embed_text)

        # ── Stage 5: Write to Neo4j ──────────────────
        result = upsert_paper_to_graph(
            extraction   = extraction,
            embedding    = embedding,
            resolved_refs= resolved_refs,
        )

        return JSONResponse({
            "status":           "success",
            "paper_id":         result["paper_id"],
            "title":            paper.title,
            "personality_tag":  extraction["personality"]["personality_tag"],
            "confidence":       extraction["personality"]["confidence_score"],
            "refs_resolved":    sum(1 for r in resolved_refs if r.found_on_arxiv),
            "refs_total":       len(resolved_refs),
            "graph_nodes_created": result["nodes_created"],
        })

    finally:
        os.unlink(tmp_path)  # Selalu hapus temp file