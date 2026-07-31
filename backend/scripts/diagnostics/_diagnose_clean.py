"""Clean diagnostic report - one table per book."""
import sys, os, re, fitz, tiktoken, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.domain.medical_library.pdf_extractor import extract_chapters, CHAPTER_PATTERN
from app.domain.medical_library.chunker import chunk_all_sections

tokenizer = tiktoken.get_encoding("cl100k_base")
BOOKS_DIR = "/teamspace/studios/this_studio/Medico/books"

BOOKS = [
    ("Harrison's Principles of Internal Medicine", "Disease Knowledge/Harrisons-Principles-of-Internal-Medicine-20th-Edition-Vol.1-Vol.2-Part-1.pdf"),
    ("Davidson's Principles and Practice of Medicine", "Disease Knowledge/Davidsons-Principles-Practice-of-Medicine-PDFDrive.com-.pdf"),
    ("Current Medical Diagnosis and Treatment 2025", "Disease Knowledge/current-medical-diagnosis-and-treatment-2025-1.pdf"),
    ("The Merck Manual of Diagnosis and Therapy", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ("Oxford Handbook of Clinical and Laboratory Investigation", "Report Intelligence/Oxford-Handbook-of-Clinical-and-Laboratory-Investigation.pdf"),
    ("Goodman & Gilman's The Pharmacological Basis of Therapeutics", "Pharmacology/Goodman-Gilmans-The-Pharmacological-Basis-of-Therapeutics-11th-Edition-2006.pdf"),
    ("Basic & Clinical Pharmacology", "Pharmacology/Basic-Clinical-Pharmacology-2018.pdf"),
    ("Oxford Handbook of Clinical Medicine", "Clinical Practice/8205Oxford Handbook of Clinical Medicine 10th 2017 Edition_SamanSarKo - Copy.pdf"),
]

def diag(book_name, relpath):
    pdf_path = os.path.join(BOOKS_DIR, relpath)
    if not os.path.exists(pdf_path):
        return {"book": book_name, "status": "FILE NOT FOUND"}

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_with_text = 0
    raw_chars = 0
    for i in range(total_pages):
        t = doc[i].get_text("text").strip()
        if t:
            pages_with_text += 1
            raw_chars += len(doc[i].get_text("text"))
    doc.close()

    if pages_with_text == 0:
        return {"book": book_name, "status": "OCR REQUIRED", "total_pages": total_pages, "pages_with_text": 0}

    sections = extract_chapters(pdf_path)
    for s in sections:
        s["book"] = book_name
    chunks = chunk_all_sections(sections)

    extracted_chars = sum(len(s["text"]) for s in sections)
    extracted_words = sum(len(s["text"].split()) for s in sections)
    chapters_seen = len(set(s["chapter"] for s in sections))

    # Count chapter hits/misses
    doc2 = fitz.open(pdf_path)
    ch_hits, ch_misses = 0, 0
    for i in range(len(doc2)):
        for line in doc2[i].get_text("text").split("\n"):
            s = line.strip()
            if "Chapter" in s or "CHAPTER" in s:
                if CHAPTER_PATTERN.match(s):
                    ch_hits += 1
                else:
                    ch_misses += 1
    doc2.close()

    return {
        "book": book_name,
        "status": "OK",
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
        "raw_chars": raw_chars,
        "extracted_chars": extracted_chars,
        "extracted_words": extracted_words,
        "coverage_pct": round(extracted_chars / max(raw_chars, 1) * 100, 1),
        "sections": len(sections),
        "chunks": len(chunks),
        "unique_chapters": chapters_seen,
        "chapter_detection_hits": ch_hits,
        "chapter_detection_misses": ch_misses,
    }

results = []
for name, path in BOOKS:
    r = diag(name, path)
    results.append(r)

# Print report
print("=" * 100)
print("EXTRACTION DIAGNOSTIC REPORT")
print("=" * 100)
for r in results:
    print(f"\n{'─'*100}")
    print(f"  BOOK: {r['book']}")
    print(f"{'─'*100}")
    if r['status'] != 'OK':
        print(f"  STATUS: {r['status']}")
        if 'total_pages' in r:
            print(f"  Total pages: {r['total_pages']}")
        continue
    print(f"  {'Metric':40s} {'Value':>15s}")
    print(f"  {'─'*55}")
    print(f"  {'Total pages':40s} {r['total_pages']:>15,d}")
    print(f"  {'Pages with extractable text':40s} {r['pages_with_text']:>15,d}")
    print(f"  {'Raw characters':40s} {r['raw_chars']:>15,d}")
    print(f"  {'Extracted characters':40s} {r['extracted_chars']:>15,d}")
    print(f"  {'Extracted words':40s} {r['extracted_words']:>15,d}")
    print(f"  {'Text coverage':40s} {r['coverage_pct']:>13.1f}%")
    print(f"  {'Sections detected':40s} {r['sections']:>15,d}")
    print(f"  {'Chunks generated':40s} {r['chunks']:>15,d}")
    print(f"  {'Unique chapters':40s} {r['unique_chapters']:>15,d}")
    print(f"  {'Chapter regex hits':40s} {r['chapter_detection_hits']:>15,d}")
    print(f"  {'Chapter regex misses':40s} {r['chapter_detection_misses']:>15,d}")

print(f"\n{'='*100}")
print("SUMMARY")
print(f"{'='*100}")
print(f"{'Book':40s} {'Pages':>6s} {'TxPg':>5s} {'RawCh':>9s} {'ExtCh':>9s} {'Cov%':>6s} {'Sect':>5s} {'Chnk':>6s} {'Chap':>5s} {'ChHits':>6s} {'ChMiss':>6s}")
print(f"{'─'*100}")
total_chunks = 0
total_raw = 0
total_ext = 0
for r in results:
    if r['status'] != 'OK':
        if 'total_pages' in r:
            print(f"{r['book']:40s} {r['total_pages']:6d} {'OCR':>5s} {'─':>9s} {'─':>9s} {'─':>6s} {'─':>5s} {'─':>6s} {'─':>5s} {'─':>6s} {'─':>6s}")
        else:
            print(f"{r['book']:40s} {'MISS':>6s} {'─':>5s} {'─':>9s} {'─':>9s} {'─':>6s} {'─':>5s} {'─':>6s} {'─':>5s} {'─':>6s} {'─':>6s}")
        continue
    print(f"{r['book']:40s} {r['total_pages']:6d} {r['pages_with_text']:5d} {r['raw_chars']:9,d} {r['extracted_chars']:9,d} {r['coverage_pct']:5.1f}% {r['sections']:5d} {r['chunks']:6d} {r['unique_chapters']:5d} {r['chapter_detection_hits']:6d} {r['chapter_detection_misses']:6d}")
    total_chunks += r['chunks']
    total_raw += r['raw_chars']
    total_ext += r['extracted_chars']

print(f"{'─'*100}")
print(f"{'TOTAL':40s} {'':6s} {'':5s} {total_raw:9,d} {total_ext:9,d} {total_ext/max(total_raw,1)*100:5.1f}% {'':5s} {total_chunks:6d}")
print()
