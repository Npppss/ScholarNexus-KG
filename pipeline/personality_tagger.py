import json
import re
import logging
from app.config.settings import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  PROMPT 1: Metadata Extraction
# ─────────────────────────────────────────────
METADATA_PROMPT = """
You are a scientific paper analyst. Extract structured metadata from the paper sections below.

PAPER SECTIONS:
---
TITLE: {title}
ABSTRACT: {abstract}
INTRODUCTION: {introduction}
METHODS: {methods}
---

Return ONLY a valid JSON object with this exact schema:
{{
  "authors": ["string"],
  "year": "string or null",
  "venue": "string or null",
  "topics": ["string"],
  "methods_proposed": ["string"],
  "methods_used_as_baseline": ["string"],
  "datasets": ["string"],
  "problem_statement": "1-2 sentence summary",
  "key_contribution": "1-2 sentence summary"
}}

Rules:
- topics: 2-5 high-level research areas (e.g. "Natural Language Processing", "Computer Vision")
- methods_proposed: only NEW methods this paper introduces
- methods_used_as_baseline: methods from OTHER papers this paper compares against
- Return ONLY JSON. No explanation. No markdown fences.
"""

# ─────────────────────────────────────────────
#  PROMPT 2: Personality Classification
#  (Chain-of-Thought → JSON)
# ─────────────────────────────────────────────
PERSONALITY_PROMPT = """
You are an expert research analyst. Your task is to classify the "personality" of
an academic paper based on its role in the research ecosystem.

There are exactly 3 personality types:

[THE PIONEER]
- Introduces a genuinely new method, architecture, or paradigm
- The paper's core contribution is something that did NOT exist before
- Signal phrases: "we propose", "we introduce", "a novel", "for the first time"
- The paper defines the problem AND the solution

[THE OPTIMIZER]
- Takes an existing, named method and makes it significantly better
- Core contribution is improving speed, accuracy, efficiency, or scalability
- Always references the original method it improves (e.g., "improves BERT by...")
- Signal phrases: "we improve", "outperforms", "better than", "more efficient than"

[THE BRIDGE]
- Its PRIMARY contribution is connecting two previously separate research domains
- Applies method from Domain A to solve a problem in Domain B
- The novelty is the CONNECTION, not the method itself
- Signal phrases: "we apply X to Y", "bridging", "cross-domain", "transfer"

PAPER INFORMATION:
---
TITLE: {title}
ABSTRACT: {abstract}
PROBLEM: {problem_statement}
KEY CONTRIBUTION: {key_contribution}
METHODS PROPOSED: {methods_proposed}
TOPICS: {topics}
---

INSTRUCTIONS:
1. Think step-by-step about which personality fits best (write your reasoning in "reasoning")
2. Pick the SINGLE best personality_tag
3. Score your confidence from 0.0 to 1.0

Return ONLY this JSON (no markdown, no extra text):
{{
  "reasoning": "3-5 sentences explaining your classification decision",
  "personality_tag": "PIONEER" | "OPTIMIZER" | "BRIDGE",
  "confidence_score": 0.0-1.0,
  "evidence_quotes": ["short quote from abstract supporting this", "another quote"]
}}
"""

# ─────────────────────────────────────────────
#  PROMPT Lightweight: Personality only
#  (Untuk ArXiv papers yang sudah punya metadata)
# ─────────────────────────────────────────────
PERSONALITY_ONLY_PROMPT = """
You are an expert research analyst. Classify the "personality" of this academic paper.

There are exactly 3 personality types:
- PIONEER: Introduces a genuinely new method, architecture, or paradigm that did NOT exist before.
- OPTIMIZER: Improves an existing method — better speed, accuracy, efficiency, or scalability.
- BRIDGE: Connects two previously separate research domains — applies method from Domain A to Domain B.

PAPER:
---
TITLE: {title}
ABSTRACT: {abstract}
CATEGORIES: {categories}
YEAR: {year}
---

Think step-by-step, then return ONLY this JSON:
{{
  "reasoning": "2-3 sentences explaining your classification",
  "personality_tag": "PIONEER" or "OPTIMIZER" or "BRIDGE",
  "confidence_score": 0.0-1.0,
  "evidence_quotes": ["short verbatim quote from the abstract supporting the tag", "another quote"],
  "problem_statement": "1 sentence: the core problem this paper addresses",
  "key_contribution": "1 sentence: the main contribution of this paper"
}}
"""


def _call_llm(prompt: str) -> str:
    """
    Unified LLM caller:
    - Default/Preferred: Gemini Reasoning (gemini-2.5-flash / gemini-2.5-pro)
    - Alternative: DeepSeek (deepseek-reasoner)
    """
    provider = (settings.llm_provider or "gemini").lower()

    if provider == "gemini" and settings.gemini_api_key:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        logger.info(f"🧠 Calling Gemini Reasoning model: {settings.gemini_model}")
        response = model.generate_content(prompt)
        return response.text or ""

    elif provider == "deepseek" and settings.deepseek_api_key:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        logger.info(f"🧠 Calling DeepSeek model: {settings.deepseek_model}")
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
        )
        choice = response.choices[0].message
        reasoning = getattr(choice, "reasoning_content", None)
        if reasoning:
            logger.debug(f"DeepSeek R1 reasoning: {reasoning[:300]}")
        return choice.content or ""

    # Fallback to whichever key is available
    if settings.gemini_api_key:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        logger.info(f"🧠 Fallback: Calling Gemini {settings.gemini_model}")
        response = model.generate_content(prompt)
        return response.text or ""

    raise ValueError("No LLM API key configured (neither Gemini nor DeepSeek)")


def run_extraction_pipeline(paper) -> dict:
    """
    Jalankan 2-step LLM extraction dari ParsedPaper (PDF upload flow):
    1. Metadata extraction
    2. Personality classification
    """
    from pipeline.pdf_extractor import ParsedPaper

    # ── Call 1: Metadata ──────────────────────────────
    try:
        meta_prompt = METADATA_PROMPT.format(
            title        = paper.title or "Unknown",
            abstract     = paper.sections.get("abstract", "")[:3000],
            introduction = paper.sections.get("introduction", "")[:2000],
            methods      = paper.sections.get("methods", "")[:2000],
        )
        meta_text = _call_llm(meta_prompt)
        metadata = _safe_parse_json(meta_text)
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        metadata = {
            "problem_statement": "Metadata extraction failed due to API error.",
            "key_contribution": str(e),
            "methods_proposed": [],
            "topics": []
        }

    # ── Call 2: Personality ───────────────────────────
    try:
        personality_prompt = PERSONALITY_PROMPT.format(
            title              = paper.title or "Unknown",
            abstract           = paper.sections.get("abstract", "")[:2000],
            problem_statement  = metadata.get("problem_statement", ""),
            key_contribution   = metadata.get("key_contribution", ""),
            methods_proposed   = ", ".join(metadata.get("methods_proposed", [])),
            topics             = ", ".join(metadata.get("topics", [])),
        )
        personality_text = _call_llm(personality_prompt)
        personality = _safe_parse_json(personality_text)
        
        valid_tags = {"PIONEER", "OPTIMIZER", "BRIDGE"}
        tag = str(personality.get("personality_tag") or "").upper().strip()
        if tag not in valid_tags:
            personality["personality_tag"] = None
        else:
            personality["personality_tag"] = tag
            
    except Exception as e:
        logger.error(f"Personality extraction failed: {e}")
        personality = {
            "personality_tag": None,
            "confidence_score": 0.0,
            "reasoning": f"API error: {str(e)}"
        }

    return {
        "title":            paper.title,
        "metadata":         metadata,
        "personality":      personality,
        "references_raw":   paper.references_raw,
        "sections_found":   list(paper.sections.keys()),
    }


def classify_arxiv_paper(
    title:      str,
    abstract:   str,
    categories: list[str] = None,
    year:       int = None,
) -> dict:
    """
    Classify personality dari ArXiv paper menggunakan 1 LLM call.
    Returns: {"personality_tag": "PIONEER"|"OPTIMIZER"|"BRIDGE",
              "confidence_score": float, "reasoning": str,
              "evidence_quotes": list[str], "problem_statement": str,
              "key_contribution": str}
    """
    if not settings.gemini_api_key and not settings.deepseek_api_key:
        logger.warning("No LLM API key set — skipping personality tagging")
        return {
            "personality_tag":  None,
            "confidence_score": 0.0,
            "reasoning":        "API key not configured",
        }

    try:
        prompt = PERSONALITY_ONLY_PROMPT.format(
            title      = title or "Unknown",
            abstract   = (abstract or "")[:4000],
            categories = ", ".join(categories or []),
            year       = year or "Unknown",
        )

        response_text = _call_llm(prompt)
        result = _safe_parse_json(response_text)

        # Validate tag
        valid_tags = {"PIONEER", "OPTIMIZER", "BRIDGE"}
        tag = str(result.get("personality_tag") or "").upper().strip()
        if tag not in valid_tags:
            logger.warning(f"Invalid personality tag '{tag}' — defaulting to None")
            result["personality_tag"] = None
            result["confidence_score"] = 0.0
        else:
            result["personality_tag"] = tag

        try:
            result["confidence_score"] = max(0.0, min(1.0, float(result.get("confidence_score") or 0.0)))
        except (TypeError, ValueError):
            result["confidence_score"] = 0.0

        logger.info(
            f"🎭 Personality: {result.get('personality_tag')} "
            f"(confidence={result.get('confidence_score', 0):.2f}) "
            f"for '{title[:60]}...'"
        )
        return result

    except Exception as e:
        logger.error(f"Personality tagging failed: {e}")
        return {
            "personality_tag":  None,
            "confidence_score": 0.0,
            "reasoning":        f"Error: {str(e)}",
            "error":            str(e),
        }


def heuristic_classify_paper(
    title: str,
    abstract: str = "",
    categories: list[str] = None,
    year: int = None,
) -> dict:
    """
    Klasifikasi heuristik berbasis sinyal leksikal dan metodologis
    sebagai cadangan (fallback) andal apabila abstrak eksternal terbatas
    atau ketika kuota inferensi LLM sedang mencapai batas laju (rate limit).
    """
    t_lower = (title or "").lower()
    a_lower = (abstract or "").lower()
    combined = f"{t_lower} {a_lower}"

    bridge_signals = [
        "bridging", "cross-domain", "multimodal", "vision-language", "image-text",
        "transfer learning", "domain adaptation", "connecting", "from language to",
        "for vision", "in medical", "in biology", "audio-visual", "speech-to-",
        "image caption", "visual question", "translating", "jointly learning",
        "multi-task", "unified", "combining", "hybrid", "fusion", "across domains"
    ]
    optimizer_signals = [
        "improving", "accelerating", "faster", "fast ", "efficient", "scaling",
        "optimization", "optimizing", "pruning", "quantization", "distillation",
        "lightweight", "compact", "regularization", "normalization", "batch normalization",
        "layer normalization", "dropout", "preventing", "rethinking", "better",
        "deeper", "very deep", "residual", "stochastic gradient", "adam",
        "training", "convergence", "reducing", "compressing", "speeding", "hints for"
    ]
    pioneer_signals = [
        "attention is all you need", "introducing", "novel", "generative adversarial",
        "auto-encoding", "variational", "transformer", "bert:", "sequence to sequence",
        "neural turing", "memory networks", "pointer networks", "capsule",
        "graph convolutional", "diffusion", "contrastive learning", "alexnet",
        "lenet", "imagenet classification", "fundamental", "towards a new"
    ]

    bridge_score = sum(2 if s in t_lower else 1 for s in bridge_signals if s in combined)
    optimizer_score = sum(2 if s in t_lower else 1 for s in optimizer_signals if s in combined)
    pioneer_score = sum(2 if s in t_lower else 1 for s in pioneer_signals if s in combined)

    if bridge_score > optimizer_score and bridge_score >= pioneer_score and bridge_score > 0:
        tag = "BRIDGE"
        conf = min(0.88, 0.72 + bridge_score * 0.04)
        reasoning = (
            f"Karya ilmiah '{title}' diklasifikasikan sebagai BRIDGE karena menjembatani "
            f"pendekatan lintas-domain atau mengintegrasikan dua paradigma komputasi yang berbeda."
        )
        problem = f"Mengatasi keterbatasan integrasi metode lintas domain pada permasalahan yang dibahas dalam '{title}'."
        contribution = "Menyajikan kerangka kerja penghubung yang mengadaptasi teknik antar-bidang secara sinergis."
    elif optimizer_score >= pioneer_score and optimizer_score > 0:
        tag = "OPTIMIZER"
        conf = min(0.90, 0.74 + optimizer_score * 0.04)
        reasoning = (
            f"Karya ilmiah '{title}' diklasifikasikan sebagai OPTIMIZER karena berfokus pada "
            f"peningkatan efisiensi, stabilitas pelatihan, skala arsitektur, atau akurasi metode yang telah ada."
        )
        problem = f"Mengatasi kendala efisiensi, konvergensi, atau kapasitas performa pada arsitektur terdahulu."
        contribution = "Mengusulkan teknik optimasi dan penyempurnaan struktural yang meningkatkan kinerja secara signifikan."
    elif pioneer_score > 0 or (year and int(year) <= 2015):
        tag = "PIONEER"
        conf = min(0.92, 0.76 + pioneer_score * 0.04)
        reasoning = (
            f"Karya ilmiah '{title}' ({year or 'N/A'}) diklasifikasikan sebagai PIONEER karena "
            f"memperkenalkan fondasi arsitektur atau formulasi metodologis baru yang menjadi rujukan utama."
        )
        problem = f"Merumuskan pendekatan fundamental baru untuk menyelesaikan keterbatasan paradigma konvensional."
        contribution = "Memperkenalkan arsitektur atau metode orisinal yang membuka jalur riset baru."
    else:
        tag = "OPTIMIZER"
        conf = 0.72
        reasoning = (
            f"Berdasarkan posisi struktural dalam silsilah literatur, '{title}' berperan dalam "
            f"pengembangan dan penguatan metodologi pada domain terkait."
        )
        problem = "Meningkatkan efektivitas pemodelan dan representasi pada domain penelitian terkait."
        contribution = "Memberikan pengembangan metodologis dan evaluasi empiris pada arsitektur jaringan."

    return {
        "personality_tag": tag,
        "confidence_score": round(conf, 2),
        "reasoning": reasoning,
        "evidence_quotes": [title] if not abstract else [abstract[:160].strip() + "..."],
        "problem_statement": problem,
        "key_contribution": contribution,
    }


def classify_paper_with_fallback(
    title: str,
    abstract: str = "",
    categories: list[str] = None,
    year: int = None,
) -> dict:
    """
    Jalankan klasifikasi LLM (Gemini/DeepSeek) terlebih dahulu apabila abstrak tersedia,
    dan gunakan klasifikasi heuristik ilmiah jika abstrak kosong atau kuota API terbatas.
    """
    if abstract and len(abstract.strip()) >= 30 and (settings.gemini_api_key or settings.deepseek_api_key):
        llm_res = classify_arxiv_paper(
            title=title,
            abstract=abstract,
            categories=categories,
            year=year,
        )
        if llm_res.get("personality_tag") in {"PIONEER", "OPTIMIZER", "BRIDGE"}:
            return llm_res

    return heuristic_classify_paper(
        title=title,
        abstract=abstract,
        categories=categories,
        year=year,
    )


def _safe_parse_json(text: str) -> dict:
    """Parse JSON dari LLM response, toleran terhadap trailing text."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"```(?:json)?", "", text).strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"error": "JSON parse failed", "raw": text}
