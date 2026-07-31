import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from app.domain.medical_library.pdf_extractor import extract_chapters
from app.domain.medical_library.chunker import chunk_all_sections
from app.domain.medical_library.embedder import embed_texts
from app.domain.medical_library import indexer

logger = logging.getLogger("medical_library")

BOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "books",
)

BOOK_MAP: dict[str, list[tuple[str, str]]] = {
    "diseases": [
        ("Harrison's Principles of Internal Medicine", "Disease Knowledge/Harrisons-Principles-of-Internal-Medicine-20th-Edition-Vol.1-Vol.2-Part-1.pdf"),
        ("Davidson's Principles and Practice of Medicine", "Disease Knowledge/Davidsons-Principles-Practice-of-Medicine-PDFDrive.com-.pdf"),
        ("Current Medical Diagnosis and Treatment 2025", "Disease Knowledge/current-medical-diagnosis-and-treatment-2025-1.pdf"),
        ("The Merck Manual of Diagnosis and Therapy", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ],
    "laboratory": [
        ("Oxford Handbook of Clinical and Laboratory Investigation", "Report Intelligence/Oxford-Handbook-of-Clinical-and-Laboratory-Investigation.pdf"),
        ("The Merck Manual of Diagnosis and Therapy", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ],
    "pharmacology": [
        ("Goodman & Gilman's The Pharmacological Basis of Therapeutics", "Pharmacology/Goodman-Gilmans-The-Pharmacological-Basis-of-Therapeutics-11th-Edition-2006.pdf"),
        ("Basic & Clinical Pharmacology", "Pharmacology/Basic-Clinical-Pharmacology-2018.pdf"),
    ],
    "clinical_practice": [
        ("Oxford Handbook of Clinical Medicine", "Clinical Practice/8205Oxford Handbook of Clinical Medicine 10th 2017 Edition_SamanSarKo - Copy.pdf"),
    ],
}


def process_book(book_name: str, pdf_rel_path: str, collection: str) -> dict:
    """Process a single book: extract, chunk, embed, upload.
    Returns dict with book_name, sections, chunks_generated, embeddings_generated, vectors_uploaded."""
    result = {
        "book_name": book_name,
        "sections": 0,
        "chunks_generated": 0,
        "embeddings_generated": 0,
        "vectors_uploaded": 0,
    }

    pdf_path = os.path.join(BOOKS_DIR, pdf_rel_path)
    if not os.path.exists(pdf_path):
        logger.warning(f"Book not found: {pdf_path}")
        return result

    logger.info(f"Processing: {book_name}")

    t0 = time.time()
    
    # Stage 1: PDF Cleaner
    from app.domain.medical_library.pdf_cleaner import PDFCleaner
    cleaner = PDFCleaner(pdf_path)
    clean_pages = cleaner.extract_clean_text()
    
    # Stage 2 & 4: Semantic Chunker
    from app.domain.medical_library.semantic_chunker import SemanticChunker
    chunker = SemanticChunker()
    chunks = chunker.chunk_pages(clean_pages, book_name)
    
    # Stage 3: Metadata Extraction
    from app.domain.medical_library.metadata_extractor import MetadataExtractor
    extractor = MetadataExtractor()
    enriched_chunks = [extractor.enrich_chunk(c) for c in chunks]
    
    # Filter out index and toc pages completely
    valid_chunks = [c for c in enriched_chunks if c["metadata"]["content_type"] == "content"]
    
    result["chunks_generated"] = len(valid_chunks)
    logger.info(f"  Created {len(valid_chunks)} chunks ({time.time()-t0:.1f}s)")

    if not valid_chunks:
        return result

    # Rename valid_chunks to chunks for downstream
    chunks = valid_chunks
    client = indexer.get_client()
    batch_size = 128
    total_uploaded = 0
    total_embedded = 0
    t0 = time.time()

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]
        vectors = embed_texts(texts)
        total_embedded += len(vectors)
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(vectors)} vectors for {len(batch)} texts "
                f"(batch starting at chunk {i})"
            )
        indexer.upload_batch(client, collection, batch, vectors, global_start_index=i)
        total_uploaded += len(batch)
        elapsed = time.time() - t0
        rate = total_uploaded / elapsed if elapsed > 0 else 0
        logger.info(f"  {total_uploaded}/{len(chunks)} chunks ({elapsed:.1f}s, {rate:.1f} chunks/s)")

    result["embeddings_generated"] = total_embedded
    result["vectors_uploaded"] = total_uploaded
    logger.info(f"Done: {book_name} -> {total_uploaded} chunks in {time.time()-t0:.1f}s")
    return result


def run_ingestion(collections: Optional[list[str]] = None, max_workers: int = 1):
    """Run ingestion for all books. Default max_workers=1 to avoid GPU race conditions."""
    client = indexer.get_client()
    # Delete and recreate collections for clean state
    indexer.reset_client()
    import shutil
    qdrant_path = indexer.QDRANT_PATH
    if os.path.exists(qdrant_path):
        shutil.rmtree(qdrant_path)
    client = indexer.get_client()
    indexer.init_collections(client)

    targets = []
    for coll, books in BOOK_MAP.items():
        if collections and coll not in collections:
            continue
        for book_name, pdf_rel in books:
            if book_name == "Davidson's Principles and Practice of Medicine":
                logger.info(f"Skipping {book_name} (OCR required)")
                continue
            targets.append((book_name, pdf_rel, coll))

    logger.info(f"Ingesting {len(targets)} book entries sequentially")
    logger.info(f"ThreadPoolExecutor max_workers={max_workers}")

    books_report = []
    total_chunks = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_book, *t): t for t in targets}
        for f in as_completed(futures):
            t = futures[f]
            try:
                r = f.result()
                books_report.append(r)
                total_chunks += r["vectors_uploaded"]
                logger.info(f"  -> {t[0]}: {r['chunks_generated']} chunks, {r['vectors_uploaded']} uploaded")
            except Exception as e:
                logger.error(f"  -> {t[0]} FAILED: {e}")
                import traceback
                logger.error(traceback.format_exc())

    logger.info(f"\n{'='*60}")
    logger.info("BOOK INGESTION REPORT")
    logger.info(f"{'='*60}")
    logger.info(f"{'Book':50s} {'Sect':>5s} {'Chnk':>5s} {'Emb':>5s} {'Upld':>5s}")
    logger.info(f"{'-'*70}")
    total_report = {"sections": 0, "chunks_generated": 0, "embeddings_generated": 0, "vectors_uploaded": 0}
    for r in books_report:
        logger.info(f"{r['book_name']:50s} {r['sections']:5d} {r['chunks_generated']:5d} {r['embeddings_generated']:5d} {r['vectors_uploaded']:5d}")
        for k in total_report:
            total_report[k] += r[k]
    logger.info(f"{'-'*70}")
    logger.info(f"{'TOTAL':50s} {total_report['sections']:5d} {total_report['chunks_generated']:5d} {total_report['embeddings_generated']:5d} {total_report['vectors_uploaded']:5d}")

    logger.info(f"\n=== Ingestion complete: {total_chunks} total chunks ===")
    stats = indexer.get_stats(client)
    logger.info(f"Collection stats: {json.dumps(stats, indent=2)}")

    # Validate
    logger.info(f"\n{'='*60}")
    logger.info("VALIDATION: generated_chunks vs stored_vectors")
    logger.info(f"{'='*60}")
    for r in books_report:
        expected = r["vectors_uploaded"]
        book = r["book_name"]
        # Find collection for this book
        coll = None
        for c, blist in BOOK_MAP.items():
            for bn, _ in blist:
                if bn == book:
                    coll = c
                    break
        if coll:
            stored = indexer.collection_count(client, coll)
            # Count only this book's points in the collection
            actual_stored = 0
            offset = None
            while True:
                results, offset = client.scroll(
                    collection_name=coll,
                    limit=1000,
                    offset=offset,
                    with_payload=["source_book"],
                    with_vectors=False,
                )
                if not results:
                    break
                actual_stored += sum(1 for pt in results if pt.payload.get("source_book") == book)
                if offset is None:
                    break
            logger.info(f"  {book:50s} uploaded={expected:5d} stored={actual_stored:5d} diff={expected - actual_stored:+5d}")

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    run_ingestion()
