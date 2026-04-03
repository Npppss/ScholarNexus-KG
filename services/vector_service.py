# services/vector_service.py
import google.generativeai as genai
from app.config.settings import settings

genai.configure(api_key=settings.gemini_api_key)

def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding vector dari teks menggunakan Gemini text-embedding-004.
    Mengembalikan list float[768].
    """
    if not text or not text.strip():
        return [0.0] * 768  # fallback vector kosong

    result = genai.embed_content(
        model   = settings.embedding_model,   # "models/text-embedding-004"
        content = text[:8000],                # trim jika terlalu panjang
        task_type = "RETRIEVAL_DOCUMENT",
    )
    return result["embedding"]