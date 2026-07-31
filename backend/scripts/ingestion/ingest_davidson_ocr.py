#!/usr/bin/env python3
"""
OCR Davidson's Principles and Practice of Medicine and upload to remote Qdrant.
Uses OpenRouter Vision API for OCR, same embedding model as medical library.
"""

import os
import re
import sys
import time
import logging
from pathlib import Path

import fitz
import tiktoken

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.infrastructure.vector_store import vector_store
from app.infrastructure.embedding_service import embedding_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_davidson")

BOOKS_DIR = Path(__file__).parent.parent.parent.parent / "books"
DAVIDSON_PDF = BOOKS_DIR / "Disease Knowledge" / "Davidsons-Principles-Practice-of-Medicine-PDFDrive.com-.pdf"

EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"  # Same as medical library
EMBEDDING_DIM = 2048
CHUNK_SIZE = 750
CHUNK_OVERLAP = 125
BATCH_SIZE = 64
COLLECTION = "diseases"

PROTECTED_BLOCKS = [
    re.compile(r"^\s*\|.+\|.+\|.*$", re.M),
    re.compile(r"^\s*(?:Normal|Abnormal|Result|Range|Reference).*", re.I),
    re.compile(r"\b\d+\s*[-–]\s*\d+\s*(?:mg|g|µg|mL|L|U|IU|mmol|mEq|ng|pg)"),
    re.compile(r"(?:Diagnostic Criteria|Diagnosis|ICD-?\d*)[\s\S]{0,200}(?:\n\s*(?:•|-|\d+\.))"),
    re.compile(r"(?:Treatment|Dosage|Administration|Contraindications)[\s\S]{0,300}(?:\n\s*(?:•|-|\d+\.))"),
    re.compile(r"(?:Normal Values|Reference Range|Laboratory Values)[\s\S]{0,300}(?:\n\s*(?:•|-|\d+\.|\|))"),
    re.compile(r"(?:Staging|Classification|Grades?)[\s\S]{0,300}(?:\n\s*(?:•|-|\d+\.|\|))"),
]

HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*\d+\s*$"),
    re.compile(r"^\s*Page\s+\d+\s*$", re.I),
    re.compile(r"^\s*[A-Z\s]{10,}\s*$"),
    re.compile(r"^(www\.|http|©|Copyright|Printed|All rights reserved)"),
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),
    re.compile(r"^\s*\d+\s*of\s*\d+\s*$", re.I),
    re.compile(r"^\s*(?:CHAPTER|Chapter|CH\.|Ch\.)\s+\d+", re.I),
    re.compile(r"^\s*Part\s+[IVXLCDM]+\b", re.I),
]

CHAPTER_RE = re.compile(
    r"^\s*(?:(?:CHAPTER|Chapter|CH\.|Ch\.)\s+)?(\d+|[IVXLCDM]+)\s*[.:–-]?\s*(.+)$", re.I
)
SECTION_RE = re.compile(r"^\s*((?:\d+\.)+\d*\s+.+|(?:[A-Z][a-z]+\s)+(?:[A-Z][a-z]+))\s*$")

tokenizer = tiktoken.get_encoding("cl100k_base")


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_chapters_ocr(pdf_path: Path) -> list[dict]:
    """Extract text from PDF using text extraction only (no OCR)."""
    doc = fitz.open(str(pdf_path))
    results = []
    current_chapter = "Front Matter"
    current_section = "Introduction"

    stats = {"total_pages": len(doc), "text_pages": 0, "failed_pages": 0}

    logger.info(f"Processing {stats['total_pages']} pages from {pdf_path.name}")

    # Pass 1: extract text from pages
    page_texts: dict[int, str] = {}
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip() and len(text.strip()) >= 50:
            stats["text_pages"] += 1
            page_texts[page_num] = text
        else:
            stats["failed_pages"] += 1

    doc.close()

    logger.info(f"Pages with text: {stats['text_pages']}, pages skipped (no text): {stats['failed_pages']}")

    # Pass 2: sequential chapter detection and section building
    for page_num in sorted(page_texts):
        text = page_texts[page_num]
        if not text.strip():
            continue

        lines = text.split("\n")
        content_lines = []
        chapter_candidates = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                content_lines.append("")
                continue

            if any(p.match(stripped) for p in HEADER_FOOTER_PATTERNS):
                if not CHAPTER_RE.match(stripped) and not SECTION_RE.match(stripped):
                    continue

            cm = CHAPTER_RE.match(stripped)
            if cm:
                num = cm.group(1)
                title = cm.group(2).strip().rstrip(".:–- ")
                if title and len(title) > 2:
                    chapter_candidates.append((f"Chapter {num}: {title}", title))

            content_lines.append(stripped)

        if chapter_candidates:
            best_chapter, best_section = chapter_candidates[-1]
            current_chapter = best_chapter
            current_section = best_section

        body = _clean_text("\n".join(content_lines))
        if not body:
            continue

        results.append({
            "book": "Davidson's Principles and Practice of Medicine",
            "chapter": current_chapter,
            "section": current_section,
            "text": body,
            "page_number": page_num + 1,
        })

    # Merge consecutive sections with same chapter/section
    merged = []
    buf = None
    for p in results:
        key = (p["chapter"], p["section"])
        if buf is None:
            buf = {**p}
            continue
        if (buf["chapter"], buf["section"]) == key:
            buf["text"] += "\n\n" + p["text"]
            buf["page_number"] = min(buf["page_number"], p["page_number"])
        else:
            merged.append(buf)
            buf = {**p}
    if buf:
        merged.append(buf)

    logger.info(f"Extraction complete: {len(merged)} sections | Text: {stats['text_pages']} | Skipped (no text): {stats['failed_pages']}")
    return merged


def chunk_section(section: dict) -> list[dict]:
    text = section.get("text", "")
    if not text.strip():
        return []

    placeholders = {}
    for i, pattern in enumerate(PROTECTED_BLOCKS):
        def replacer(m, idx=i):
            key = f"__P{idx}_{hash(m.group(0)) % (2**32)}__"
            placeholders[key] = m.group(0)
            return key
        text = pattern.sub(replacer, text)

    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue

        t_para = len(tokenizer.encode(para_stripped))
        t_cur = len(tokenizer.encode(current_chunk)) if current_chunk else 0

        if t_cur + t_para > CHUNK_SIZE and current_chunk:
            chunks.append(current_chunk.strip())
            prev_t = tokenizer.encode(current_chunk)
            overlap = prev_t[-min(CHUNK_OVERLAP, len(prev_t)):]
            current_chunk = (tokenizer.decode(overlap) + "\n\n") if overlap else ""
            current_chunk += para_stripped + "\n"
        else:
            sep = "\n\n" if current_chunk else ""
            current_chunk += sep + para_stripped

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    result = []
    for i, chunk_text in enumerate(chunks):
        for key, val in placeholders.items():
            chunk_text = chunk_text.replace(key, val)
        result.append({**section, "text": chunk_text, "chunk_index": i})
    return result


def upload_batch(chunks: list[dict], vectors: list[list[float]], global_start: int):
    if len(chunks) != len(vectors):
        raise ValueError(f"Chunks/vectors mismatch: {len(chunks)} vs {len(vectors)}")

    points = []
    for offset, (chunk, vec) in enumerate(zip(chunks, vectors)):
        global_i = global_start + offset
        payload = {
            "source_book": chunk.get("book", ""),
            "chapter": chunk.get("chapter", ""),
            "section": chunk.get("section", ""),
            "collection": COLLECTION,
            "page_number": str(chunk.get("page_number", "")),
            "medical_topic": "",
            "text": chunk.get("text", "")[:5000],
        }
        pid = hash(f"lib:{COLLECTION}:{chunk.get('book','')}:{global_i}") % (2**63 - 1)
        points.append({"id": pid, "vector": vec, "payload": payload})

    # Upload via vector_store's client (which uses remote Qdrant)
    import qdrant_client.http.models as qm
    qdrant_points = [qm.PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points]
    response = vector_store.client.upsert(collection_name=COLLECTION, points=qdrant_points, wait=True)
    if hasattr(response, 'status') and response.status != 'ok':
        raise RuntimeError(f"Upload failed: {response}")
    logger.info(f"  Uploaded {len(points)} points to {COLLECTION} (batch start={global_start})")


def main():
    if not DAVIDSON_PDF.exists():
        logger.error(f"PDF not found: {DAVIDSON_PDF}")
        sys.exit(1)

    logger.info(f"Starting text extraction for Davidson's Principles and Practice of Medicine")
    logger.info(f"Collection: {COLLECTION}, Embedding model: {EMBEDDING_MODEL}")

    # Extract
    t0 = time.time()
    sections = extract_chapters_ocr(DAVIDSON_PDF)
    logger.info(f"Extracted {len(sections)} sections in {time.time() - t0:.1f}s")

    # Chunk
    t0 = time.time()
    all_chunks = []
    for sec in sections:
        all_chunks.extend(chunk_section(sec))
    logger.info(f"Created {len(all_chunks)} chunks in {time.time() - t0:.1f}s")

    if not all_chunks:
        logger.error("No chunks generated!")
        return

    # Embed and upload in batches
    total_uploaded = 0
    t0 = time.time()
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        logger.info(f"Embedding batch {i // BATCH_SIZE + 1}/{(len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(texts)} chunks)...")

        vectors = embedding_service.embed(texts)
        if len(vectors) != len(batch):
            raise RuntimeError(f"Embedding count mismatch: got {len(vectors)} for {len(batch)} texts")

        upload_batch(batch, vectors, i)
        total_uploaded += len(batch)
        elapsed = time.time() - t0
        rate = total_uploaded / elapsed if elapsed > 0 else 0
        logger.info(f"  Progress: {total_uploaded}/{len(all_chunks)} ({rate:.1f} chunks/s)")

    logger.info(f"\n=== COMPLETE ===")
    logger.info(f"Total sections: {len(sections)}")
    logger.info(f"Total chunks: {len(all_chunks)}")
    logger.info(f"Total uploaded: {total_uploaded}")
    logger.info(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()