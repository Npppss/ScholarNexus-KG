import json
import re
import logging
import google.generativeai as genai
from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── Configure Gemini dari settings (bukan hardcode) ───────────────────────────
genai.configure(api_key=settings.gemini_api_key)
MODEL = genai.GenerativeModel(settings.gemini_model)

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
  "confidence_score": 0.0-1.0
}}
"""


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
        meta_response = MODEL.generate_content(meta_prompt)
        metadata = _safe_parse_json(meta_response.text)
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
        personality_response = MODEL.generate_content(personality_prompt)
        personality = _safe_parse_json(personality_response.text)
        
        valid_tags = {"PIONEER", "OPTIMIZER", "BRIDGE"}
        tag = personality.get("personality_tag", "")
        if tag and isinstance(tag, str) and tag.upper() not in valid_tags:
            personality["personality_tag"] = None
            
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
    Lebih lightweight dari full pipeline karena metadata sudah ada dari ArXiv.

    Returns: {"personality_tag": "PIONEER"|"OPTIMIZER"|"BRIDGE",
              "confidence_score": float, "reasoning": str}
    """
    if not settings.gemini_api_key:
        logger.warning("Gemini API key not set — skipping personality tagging")
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

        response = MODEL.generate_content(prompt)
        result = _safe_parse_json(response.text)

        # Validate tag
        valid_tags = {"PIONEER", "OPTIMIZER", "BRIDGE"}
        tag = result.get("personality_tag", "").upper()
        if tag not in valid_tags:
            logger.warning(f"Invalid personality tag '{tag}' — defaulting to None")
            result["personality_tag"] = None
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
        }


def _safe_parse_json(text: str) -> dict:
    """Parse JSON dari LLM response, toleran terhadap trailing text."""
    text = text.strip()
    # Hapus markdown fence jika ada
    if text.startswith("```"):
        text = re.sub(r"```(?:json)?", "", text).strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: cari blok JSON pertama
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"error": "JSON parse failed", "raw": text}