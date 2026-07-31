"""
Extraction Diagnostics Script
Runs the EXACT extract_chapters + chunk_all_sections pipeline from pdf_extractor.py
and chunker.py on each PDF, then reports comprehensive stats.
"""
import sys
import os
import re
import time
import tiktoken

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import the exact pipeline modules
from app.domain.medical_library.pdf_extractor import extract_chapters, _clean_text
from app.domain.medical_library.chunker import chunk_all_sections, chunk_section, CHUNK_SIZE

tokenizer = tiktoken.get_encoding("cl100k_base")

BOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "books")

DIAGNOSTIC_BOOKS = [
    ("Harrison's Principles of Internal Medicine", "Disease Knowledge/Harrisons-Principles-of-Internal-Medicine-20th-Edition-Vol.1-Vol.2-Part-1.pdf"),
    ("Davidson's Principles and Practice of Medicine", "Disease Knowledge/Davidsons-Principles-Practice-of-Medicine-PDFDrive.com-.pdf"),
    ("Current Medical Diagnosis and Treatment 2025", "Disease Knowledge/current-medical-diagnosis-and-treatment-2025-1.pdf"),
    ("The Merck Manual of Diagnosis and Therapy", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ("Oxford Handbook of Clinical and Laboratory Investigation", "Report Intelligence/Oxford-Handbook-of-Clinical-and-Laboratory-Investigation.pdf"),
    ("Goodman & Gilman's The Pharmacological Basis of Therapeutics", "Pharmacology/Goodman-Gilmans-The-Pharmacological-Basis-of-Therapeutics-11th-Edition-2006.pdf"),
    ("Basic & Clinical Pharmacology", "Pharmacology/Basic-Clinical-Pharmacology-2018.pdf"),
    ("Oxford Handbook of Clinical Medicine", "Clinical Practice/8205Oxford Handbook of Clinical Medicine 10th 2017 Edition_SamanSarKo - Copy.pdf"),
]


def count_tokens(text):
    return len(tokenizer.encode(text))


def diag_book(book_name, relpath):
    pdf_path = os.path.join(BOOKS_DIR, relpath)
    if not os.path.exists(pdf_path):
        return {"book": book_name, "error": "FILE NOT FOUND"}

    import fitz
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Page-level stats
    pages_with_text = 0
    total_raw_chars = 0
    total_raw_tokens = 0
    non_ascii_removed = 0
    for i in range(total_pages):
        raw = doc[i].get_text("text")
        stripped = raw.strip()
        if stripped:
            pages_with_text += 1
            total_raw_chars += len(raw)
            total_raw_tokens += count_tokens(raw)
            # Count chars removed by _clean_text's non-ASCII filter
            non_ascii_removed += len(re.findall(r'[^\x20-\x7E]', stripped))

    doc.close()

    # Run the actual extraction
    t0 = time.time()
    sections = extract_chapters(pdf_path)
    extract_time = time.time() - t0
    for s in sections:
        s["book"] = book_name

    # Run actual chunking
    t0 = time.time()
    chunks = chunk_all_sections(sections)
    chunk_time = time.time() - t0

    # Analysis
    extracted_chars = sum(len(s["text"]) for s in sections)
    extracted_tokens = sum(count_tokens(s["text"]) for s in sections)
    chunk_chars = sum(len(c["text"]) for c in chunks)
    chunk_tokens = sum(count_tokens(c["text"]) for c in chunks)

    # Chapter/section analysis
    chapters_seen = set()
    sections_seen = set()
    for s in sections:
        chapters_seen.add(s["chapter"])
        sections_seen.add((s["chapter"], s["section"]))

    # Check for "Front Matter" (default) sections
    front_matter_sections = sum(1 for s in sections if s["chapter"] == "Front Matter")
    front_matter_chars = sum(len(s["text"]) for s in sections if s["chapter"] == "Front Matter")

    # Compute coverage ratio
    char_ratio_raw = extracted_chars / max(total_raw_chars, 1)
    char_ratio_cleaned = chunk_chars / max(total_raw_chars, 1)

    result = {
        "book": book_name,
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
        "total_raw_chars": total_raw_chars,
        "total_raw_tokens": total_raw_tokens,
        "extracted_sections": len(sections),
        "extracted_chars": extracted_chars,
        "extracted_tokens": extracted_tokens,
        "char_coverage_raw": char_ratio_raw,
        "total_chunks": len(chunks),
        "chunk_chars": chunk_chars,
        "chunk_tokens": chunk_tokens,
        "unique_chapters": len(chapters_seen),
        "unique_sections": len(sections_seen),
        "front_matter_sections": front_matter_sections,
        "front_matter_chars": front_matter_chars,
        "non_ascii_chars_removed_estimate": non_ascii_removed,
        "extract_time_s": round(extract_time, 1),
        "chunk_time_s": round(chunk_time, 1),
    }

    # If chunks seem low, add section-level detail
    avg_section_chars = extracted_chars / max(len(sections), 1)
    avg_chunk_chars = chunk_chars / max(len(chunks), 1)
    result["avg_section_chars"] = round(avg_section_chars)
    result["avg_chunk_chars"] = round(avg_chunk_chars)

    return result


def print_chapter_section_preview(book_name, relpath, max_samples=20):
    """Print first N chapter/section assignments to see if detection is working."""
    pdf_path = os.path.join(BOOKS_DIR, relpath)
    if not os.path.exists(pdf_path):
        return

    sections = extract_chapters(pdf_path)
    print(f"\n{'='*80}")
    print(f"CHAPTER/SECTION PREVIEW: {book_name}")
    print(f"{'='*80}")
    for i, s in enumerate(sections[:max_samples]):
        chars = len(s["text"])
        tokens = count_tokens(s["text"])
        print(f"  [{i:3d}] pg {s['page_number']:4d} | {s['chapter'][:60]:60s} | {s['section'][:40]:40s} | {chars:6d}c {tokens:4d}t")
    if len(sections) > max_samples:
        print(f"  ... and {len(sections) - max_samples} more sections")


def print_chapter_list(book_name, relpath):
    """Print all unique chapters detected."""
    pdf_path = os.path.join(BOOKS_DIR, relpath)
    if not os.path.exists(pdf_path):
        return

    sections = extract_chapters(pdf_path)
    chapters = {}
    for s in sections:
        ch = s["chapter"]
        if ch not in chapters:
            chapters[ch] = {"count": 0, "chars": 0, "pages": []}
        chapters[ch]["count"] += 1
        chapters[ch]["chars"] += len(s["text"])
        chapters[ch]["pages"].append(s["page_number"])

    print(f"\n{'='*80}")
    print(f"CHAPTER LIST: {book_name}")
    print(f"{'='*80}")
    for ch, info in sorted(chapters.items(), key=lambda x: min(x[1]["pages"])):
        tokens = count_tokens(info["text"] if isinstance(info, dict) else info)
        print(f"  {ch:60s} | {info['count']:4d} sections | {info['chars']:8,d}c | {info['pages'][0]:4d}-{info['pages'][-1]:4d}")


if __name__ == "__main__":
    print("=" * 80)
    print("EXTRACTION DIAGNOSTICS REPORT")
    print("=" * 80)

    all_results = []
    for book_name, relpath in DIAGNOSTIC_BOOKS:
        try:
            result = diag_book(book_name, relpath)
            all_results.append(result)
        except ValueError as e:
            all_results.append({"book": book_name, "error": str(e)})
        except Exception as e:
            all_results.append({"book": book_name, "error": f"{type(e).__name__}: {e}"})

    print("\n")
    print("=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    header = f"{'Book':40s} {'Pages':>6s} {'TxPg':>5s} {'RawC':>10s} {'Sect':>5s} {'Chnk':>5s} {'ChnC':>10s} {'Cov%':>6s} {'UniqCh':>5s} {'FroM':>5s}"
    print(header)
    print("-" * len(header))
    for r in all_results:
        if "error" in r:
            print(f"{r['book']:40s} ERROR: {r['error']}")
        else:
            cov = f"{r['char_coverage_raw']*100:.0f}%"
            print(f"{r['book']:40s} {r['total_pages']:6d} {r['pages_with_text']:5d} {r['total_raw_chars']:10,d} {r['extracted_sections']:5d} {r['total_chunks']:5d} {r['chunk_chars']:10,d} {cov:>6s} {r['unique_chapters']:5d} {r['front_matter_sections']:5d}")

    print("\n")
    total_raw = sum(r.get("total_raw_chars", 0) for r in all_results)
    total_extracted = sum(r.get("extracted_chars", 0) for r in all_results)
    total_chunks = sum(r.get("total_chunks", 0) for r in all_results)
    print(f"TOTAL raw chars: {total_raw:,}")
    print(f"TOTAL extracted chars: {total_extracted:,}")
    print(f"TOTAL chunks: {total_chunks:,}")
    print(f"OVERALL coverage: {total_extracted/max(total_raw,1)*100:.1f}%")

    # Detailed chapter/section previews for key books
    print("\n\n" + "=" * 80)
    print("DETAILED DIAGNOSTICS")
    print("=" * 80)

    for book_name, relpath in DIAGNOSTIC_BOOKS:
        try:
            print_chapter_list(book_name, relpath)
        except Exception as e:
            print(f"\nERROR previewing {book_name}: {e}")

    for book_name, relpath in DIAGNOSTIC_BOOKS:
        try:
            print_chapter_section_preview(book_name, relpath)
        except Exception as e:
            print(f"\nERROR previewing {book_name}: {e}")
