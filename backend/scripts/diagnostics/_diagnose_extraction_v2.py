"""
Focused extraction diagnostics:
1. Chapter detection: what regex matches are being made
2. Section splitting: how pages merge into sections
3. Content loss: text before/after extraction per page
"""

import sys, os, re, time, fitz, tiktoken
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.domain.medical_library.pdf_extractor import CHAPTER_PATTERN, SECTION_PATTERN, HEADER_FOOTER_PATTERNS, _clean_text, RUNNING_HEADER_THRESHOLD

tokenizer = tiktoken.get_encoding("cl100k_base")
BOOKS_DIR = "/teamspace/studios/this_studio/Medico/books"
EXTRACTION_LOG_DIR = "/tmp/extraction_diag"
os.makedirs(EXTRACTION_LOG_DIR, exist_ok=True)

DIAGNOSTIC_BOOKS = [
    ("Harrison's", "Disease Knowledge/Harrisons-Principles-of-Internal-Medicine-20th-Edition-Vol.1-Vol.2-Part-1.pdf"),
    ("Current D&T 2025", "Disease Knowledge/current-medical-diagnosis-and-treatment-2025-1.pdf"),
    ("Merck Manual", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ("Oxford Clinical Lab", "Report Intelligence/Oxford-Handbook-of-Clinical-and-Laboratory-Investigation.pdf"),
    ("Goodman & Gilman's", "Pharmacology/Goodman-Gilmans-The-Pharmacological-Basis-of-Therapeutics-11th-Edition-2006.pdf"),
    ("Basic Clinical Pharma", "Pharmacology/Basic-Clinical-Pharmacology-2018.pdf"),
    ("Oxford Clinical Med", "Clinical Practice/8205Oxford Handbook of Clinical Medicine 10th 2017 Edition_SamanSarKo - Copy.pdf"),
]


def inspect_chapter_detection(pdf_path, max_pages=50):
    """Inspect first N pages: what does CHAPTER_PATTERN match vs miss?"""
    doc = fitz.open(pdf_path)
    results = []
    for i in range(min(max_pages, len(doc))):
        page = doc[i]
        text = page.get_text("text")
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            cm = CHAPTER_PATTERN.match(stripped)
            sm = SECTION_PATTERN.match(stripped)
            if cm:
                results.append(("PAGE", i+1, "CHAPTER_MATCH", stripped[:120]))
            elif sm:
                results.append(("PAGE", i+1, "SECTION_MATCH", stripped[:120]))
            # Also note likely chapter lines that DON'T match
            elif any(kw in stripped for kw in ["Chapter", "CHAPTER", "Section", "SECTION", "Part"]):
                results.append(("PAGE", i+1, "MISSED_CHAPTER", stripped[:120]))
    doc.close()
    return results


def inspect_extraction_vs_raw(pdf_path, sample_pages=5):
    """Compare raw text vs extracted text for specific pages."""
    doc = fitz.open(pdf_path)
    report = []
    # Sample from beginning, middle, end
    total = len(doc)
    samples = [0, min(5, total-1), total//3, total//2, 2*total//3, total-1]
    samples = [s for s in samples if s < total][:sample_pages]

    # Now run the full extraction to see what happens per-page
    from app.domain.medical_library.pdf_extractor import extract_chapters
    sections = extract_chapters(pdf_path)
    # Build page->extracted mapping
    extracted_by_page = {}
    for s in sections:
        pg = s["page_number"]
        if pg not in extracted_by_page:
            extracted_by_page[pg] = s["text"]
        else:
            extracted_by_page[pg] += s["text"]

    for pg_idx in samples:
        pg_num = pg_idx + 1
        raw = doc[pg_idx].get_text("text")
        raw_clean = _clean_text(raw)
        extracted = extracted_by_page.get(pg_num, "")
        report.append({
            "page": pg_num,
            "raw_chars": len(raw),
            "raw_clean_chars": len(raw_clean),
            "extracted_chars": len(extracted),
            "raw_tokens": len(tokenizer.encode(raw_clean)),
            "extracted_tokens": len(tokenizer.encode(extracted)),
            "raw_preview": raw_clean[:500],
            "extracted_preview": extracted[:500],
        })
    doc.close()
    return report


def count_chapter_occurrences(pdf_path):
    """Show every occurrence of 'Chapter' or 'Section' text and whether it matched."""
    doc = fitz.open(pdf_path)
    matches = {"chapter_hits": 0, "section_hits": 0, "chapter_misses": 0}
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                continue
            if "Chapter" in s or "CHAPTER" in s:
                if CHAPTER_PATTERN.match(s):
                    matches["chapter_hits"] += 1
                else:
                    matches["chapter_misses"] += 1
                    if matches["chapter_misses"] <= 30:
                        print(f"  pg{i+1} MISSED_CHAPTER: {s[:150]}")
    doc.close()
    return matches


def measure_chunker_loss(pdf_path):
    """Measure how much content chunker produces vs what sections have."""
    from app.domain.medical_library.pdf_extractor import extract_chapters
    from app.domain.medical_library.chunker import chunk_all_sections, CHUNK_SIZE, CHUNK_OVERLAP

    sections = extract_chapters(pdf_path)
    chars_in = sum(len(s["text"]) for s in sections)
    tokens_in = sum(len(tokenizer.encode(s["text"])) for s in sections)

    chunks = chunk_all_sections(sections)
    chars_out = sum(len(c["text"]) for c in chunks)
    tokens_out = sum(len(tokenizer.encode(c["text"])) for c in chunks)

    return {
        "sections": len(sections),
        "chunks": len(chunks),
        "chars_in": chars_in,
        "chars_out": chars_out,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "ratio_chars": chars_out / max(chars_in, 1),
        "ratio_tokens": tokens_out / max(tokens_in, 1),
    }


def measure_cleaner_loss(pdf_path):
    """Measure how much _clean_text and header/footer filtering removes."""
    doc = fitz.open(pdf_path)
    total_raw = 0
    total_clean = 0
    total_lines_filtered = 0
    total_lines_raw = 0
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        total_raw += len(text)
        total_clean += len(_clean_text(text))
        lines = text.split("\n")
        for line in lines:
            s = line.strip()
            if not s:
                continue
            total_lines_raw += 1
            if any(p.match(s) for p in HEADER_FOOTER_PATTERNS):
                if not CHAPTER_PATTERN.match(s) and not SECTION_PATTERN.match(s):
                    total_lines_filtered += 1
    doc.close()
    return {
        "total_raw_chars": total_raw,
        "total_clean_chars": total_clean,
        "chars_loss_pct": (1 - total_clean / max(total_raw, 1)) * 100,
        "total_lines_raw": total_lines_raw,
        "total_lines_filtered": total_lines_filtered,
        "filtered_pct": total_lines_filtered / max(total_lines_raw, 1) * 100,
    }


def inspect_section_merging(pdf_path, max_pages=40):
    """Show raw page-by-page chapter/section detection to understand merging."""
    doc = fitz.open(pdf_path)
    print(f"{'Page':>6s} | {'Chars':>6s} | {'Chapter Match':70s} | {'Section Match':70s}")
    print("-" * 160)
    for i in range(min(max_pages, len(doc))):
        text = doc[i].get_text("text")
        lines = text.split("\n")
        chap_match = ""
        sec_match = ""
        for line in lines:
            s = line.strip()
            if not s:
                continue
            cm = CHAPTER_PATTERN.match(s)
            if cm:
                chap_match = s[:70]
            sm = SECTION_PATTERN.match(s)
            if sm:
                sec_match = s[:70]
        print(f"{i+1:6d} | {len(text):6d} | {chap_match:70s} | {sec_match:70s}")
    doc.close()


def inspect_paragraph_breaks(pdf_path, max_sections=3):
    """Inspect how sections are split by paragraphs."""
    from app.domain.medical_library.pdf_extractor import extract_chapters
    from app.domain.medical_library.chunker import chunk_section, CHUNK_SIZE
    
    sections = extract_chapters(pdf_path)
    print(f"\nSection paragraph structure (up to {max_sections} sections):")
    for idx, s in enumerate(sections[:max_sections]):
        paras = re.split(r"\n\s*\n", s["text"])
        print(f"\n  Section {idx}: chapter={s['chapter'][:40]} page={s['page_number']}")
        print(f"    Total chars: {len(s['text'])}, paragraphs: {len(paras)}")
        for pi, p in enumerate(paras[:5]):
            print(f"    Para {pi}: {len(p):6d}c {len(tokenizer.encode(p)):4d}t | {p[:100]}")
        if len(paras) > 5:
            print(f"    ... and {len(paras)-5} more paragraphs")
        chunks = chunk_section(s)
        print(f"    -> {len(chunks)} chunks")


if __name__ == "__main__":
    print("=" * 80)
    print("EXTRACTION DIAGNOSTICS - FOCUSED ANALYSIS")
    print("=" * 80)

    for book_name, relpath in DIAGNOSTIC_BOOKS:
        pdf_path = os.path.join(BOOKS_DIR, relpath)
        if not os.path.exists(pdf_path):
            print(f"\n{'='*60}\n{book_name}: FILE NOT FOUND\n{'='*60}")
            continue

        print(f"\n{'='*60}")
        print(f"BOOK: {book_name}")
        print(f"{'='*60}")

        # 1. Filing system
        print("\n--- 1. CHAPTER DETECTION ANALYSIS ---")
        try:
            matches = count_chapter_occurrences(pdf_path)
            print(f"  Chapter hits: {matches['chapter_hits']}, misses: {matches['chapter_misses']}")
            if matches['chapter_misses'] > matches['chapter_hits']:
                print(f"  WARNING: More misses than hits! Chapter detection is failing on this book.")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 2. Inspect first 30 pages for merge behavior
        print(f"\n--- 2. SECTION MERGE BEHAVIOR (first 30 pages) ---")
        try:
            inspect_section_merging(pdf_path, max_pages=30)
        except Exception as e:
            print(f"  ERROR: {e}")

        # 3. Cleaner loss
        print(f"\n--- 3. CLEANER/LINE FILTERING LOSS ---")
        try:
            cl = measure_cleaner_loss(pdf_path)
            print(f"  Raw chars: {cl['total_raw_chars']:,}")
            print(f"  Clean chars: {cl['total_clean_chars']:,}")
            print(f"  Loss from cleaning: {cl['chars_loss_pct']:.1f}%")
            print(f"  Lines filtered as headers/footers: {cl['total_lines_filtered']} / {cl['total_lines_raw']} ({cl['filtered_pct']:.1f}%)")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 4. Full pipeline measurement
        print(f"\n--- 4. CHUNKER LOSS ---")
        try:
            mc = measure_chunker_loss(pdf_path)
            print(f"  Sections: {mc['sections']}, Chunks: {mc['chunks']}")
            print(f"  Chars: {mc['chars_in']:,} in -> {mc['chars_out']:,} out ({mc['ratio_chars']*100:.1f}%)")
            print(f"  Tokens: {mc['tokens_in']:,} in -> {mc['tokens_out']:,} out ({mc['ratio_tokens']*100:.1f}%)")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 5. Paragraph structure
        print(f"\n--- 5. SECTION PARAGRAPH STRUCTURE ---")
        try:
            inspect_paragraph_breaks(pdf_path, max_sections=3)
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)
