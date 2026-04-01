import fitz  # PyMuPDF
import re
from dataclasses import dataclass, field
from typing import Optional

# --- Section heading patterns (case-insensitive) ---
SECTION_PATTERNS = {
    "abstract":      r"^\s*(abstract)\s*$",
    "introduction":  r"^\s*\d*\.?\s*(introduction)\s*$",
    "related_work":  r"^\s*\d*\.?\s*(related\s+work|background|literature\s+review)\s*$",
    "methods":       r"^\s*\d*\.?\s*(method(ology)?s?|approach|proposed\s+method)\s*$",
    "experiments":   r"^\s*\d*\.?\s*(experiment(s|al\s+results)?|evaluation|results)\s*$",
    "conclusion":    r"^\s*\d*\.?\s*(conclusion(s)?|summary|discussion)\s*$",
    "references":    r"^\s*(references|bibliography)\s*$",
}

@dataclass
class ParsedPaper:
    raw_text:     str           = ""
    sections:     dict          = field(default_factory=dict)
    title:        Optional[str] = None
    authors_raw:  list[str]     = field(default_factory=list)
    references_raw: list[str]   = field(default_factory=list)
    num_pages:    int           = 0
    file_name:    str           = ""


def extract_pdf(file_path: str) -> ParsedPaper:
    """Stage 1: Buka PDF dan ambil raw text per blok."""
    doc = fitz.open(file_path)
    paper = ParsedPaper(num_pages=len(doc), file_name=file_path)

    full_blocks = []
    for page_num, page in enumerate(doc):
        # dict mode memberi kita info font-size → berguna untuk deteksi heading
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        full_blocks.append({
                            "text":      span["text"].strip(),
                            "size":      round(span["size"], 1),
                            "bold":      "Bold" in span.get("font", ""),
                            "page":      page_num,
                        })

    paper.raw_text = " ".join(b["text"] for b in full_blocks if b["text"])

    # Heuristik: judul = teks terbesar di halaman pertama
    page0_blocks = [b for b in full_blocks if b["page"] == 0 and b["text"]]
    if page0_blocks:
        paper.title = max(page0_blocks, key=lambda b: b["size"])["text"]

    paper.sections = _detect_sections(full_blocks)
    paper.references_raw = _split_references(
        paper.sections.get("references", "")
    )
    return paper


def _detect_sections(blocks: list[dict]) -> dict[str, str]:
    """Stage 2: Pisahkan teks per section berdasarkan heading detection."""
    sections: dict[str, list[str]] = {k: [] for k in SECTION_PATTERNS}
    current_section = "preamble"
    buffer: list[str] = []

    for block in blocks:
        text = block["text"]
        if not text:
            continue

        matched = None
        for section_name, pattern in SECTION_PATTERNS.items():
            if re.match(pattern, text, re.IGNORECASE):
                matched = section_name
                break

        if matched:
            # Simpan buffer ke section sebelumnya
            if current_section in sections:
                sections[current_section].append(" ".join(buffer))
            buffer = []
            current_section = matched
        else:
            buffer.append(text)

    # Flush buffer terakhir
    if current_section in sections:
        sections[current_section].append(" ".join(buffer))

    return {k: " ".join(v).strip() for k, v in sections.items()}


def _split_references(ref_text: str) -> list[str]:
    """Pisahkan daftar referensi individual menggunakan pola numbered list."""
    # Cocokkan pola: [1], [2], ... atau 1. 2. 3.
    entries = re.split(r"\s*(?:\[\d+\]|\d+\.)\s+", ref_text)
    return [e.strip() for e in entries if len(e.strip()) > 20]