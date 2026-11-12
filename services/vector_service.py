# services/vector_service.py
#
# Embedding tetap menggunakan Gemini karena DeepSeek tidak menyediakan
# API embedding. Jika gemini_api_key tidak diset, fallback ke OpenAI
# embedding sebagai alternatif.
import logging
import google.generativeai as genai
from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── Pilih embedding provider ──────────────────────────────────────────────────
_USE_GEMINI = bool(settings.gemini_api_key)
_USE_OPENAI = bool(settings.openai_api_key) and not _USE_GEMINI

if _USE_GEMINI:
    genai.configure(api_key=settings.gemini_api_key)
    logger.info("Embedding provider: Gemini (%s)", settings.embedding_model)
elif _USE_OPENAI:
    from openai import OpenAI as _OpenAI
    _openai_client = _OpenAI(api_key=settings.openai_api_key)
    logger.info("Embedding provider: OpenAI (text-embedding-3-small)")
else:
    logger.warning(
        "No embedding API key configured (GEMINI_API_KEY or OPENAI_API_KEY). "
        "Embeddings will return zero vectors."
    )


def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding vector dari teks.
    Priority: Gemini → OpenAI → zero vector fallback.
    Mengembalikan list float[768].
    """
    if not text or not text.strip():
        return [0.0] * 768  # fallback vector kosong

    if _USE_GEMINI:
        result = genai.embed_content(
            model   = settings.embedding_model,
            content = text[:8000],                # trim jika terlalu panjang
            task_type = "RETRIEVAL_DOCUMENT",
            output_dimensionality = 768,          # truncate ke 768 dims (MRL)
        )
        return result["embedding"]

    elif _USE_OPENAI:
        response = _openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
            dimensions=768,
        )
        return response.data[0].embedding

    else:
        logger.warning("No embedding provider — returning zero vector")
        return [0.0] * 768
