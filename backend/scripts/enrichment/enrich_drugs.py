"""Enrich sparse drug records from medical textbooks.

For each drug with no clinical data in PostgreSQL, searches the medical library
(textbooks, Qdrant vector store) for relevant content and extracts structured fields
to populate the DB record.

Usage:
    python scripts/enrichment/enrich_drugs.py                    # Enrich all sparse drugs
    python scripts/enrichment/enrich_drugs.py --limit 10          # Enrich first 10 only
    python scripts/enrichment/enrich_drugs.py --drug metformin    # Enrich a specific drug
    python scripts/enrichment/enrich_drugs.py --resume            # Skip already-enriched drugs
"""

import argparse
import logging
import re
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.models.drug_database import DrugEntry
from app.infrastructure.embedding_service import embedding_service
from app.infrastructure.vector_store import vector_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_drugs")

RICH_FIELDS = [
    "indications", "adult_dose", "contraindications",
    "common_side_effects", "mechanism_of_action", "warnings",
]


def _cap(text: str) -> str:
    text = text.strip()
    if text and text[0].islower():
        return text[0].upper() + text[1:]
    return text


def _clean_section_text(text: str) -> str:
    """Remove section number prefixes and clean up clinical text."""
    text = re.sub(r"^\d+\.?\s*\d*\s*", "", text)
    text = re.sub(r"\s+\(see\s+[^)]+\)", "", text)
    text = re.sub(r"\s+\[see\s+[^]]+\]", "", text)
    return text.strip()


def _mentions_drug(text: str, drug_name: str) -> bool:
    """Check if text actually mentions the drug by name (case-insensitive)."""
    return drug_name.lower() in text.lower()


def _is_index_content(text: str) -> bool:
    """Check if text is primarily index/reference data rather than clinical content."""
    stripped = text.strip()
    # Starts with comma + page numbers
    if re.match(r"^,\s*\d+", stripped):
        return True
    # Mostly page numbers and cross-references
    num_pages = len(re.findall(r"\d+–\d+", stripped))
    num_words = len(stripped.split())
    if num_words > 0 and num_pages / num_words > 0.15:
        return True
    # Contains only page references and drug names
    if re.match(r"^[A-Za-z\s]+,?\s*\d+", stripped) and len(stripped.split()) < 10:
        return True
    return False


def _get_matching_sentences(text: str, drug_name: str) -> list[str]:
    """Split text into sentences and return those mentioning the drug.
    If no sentence mentions the drug, return all sentences (text-level filter
    already ensures the overall text is relevant)."""
    sentences = re.split(r"(?<=[.!])\s+", text)
    results = [s.strip() for s in sentences if s.strip() and _mentions_drug(s, drug_name) and len(s.strip()) > 20]
    if results:
        return results
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def _extract_indications(texts: list[str], drug_name: str) -> str:
    """Extract a clean indications string from textbook passages."""
    sentences = []
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            if not s or len(s) < 15:
                continue
            lower = s.lower()
            if any(kw in lower for kw in ["indicated for", "indication", "used for",
                                           "used in the treatment", "effective for",
                                           "approved for", "first-line",
                                           "the drug is indicated", "is used",
                                           "is indicated", "is effective"]):
                sentences.append(s)
    if sentences:
        return " ".join(sentences[:3])
    conditions = []
    for t in texts:
        if _is_index_content(t):
            continue
        for s in _get_matching_sentences(t, drug_name):
            s = s.strip()
            if not s or len(s) < 20:
                continue
            if re.search(r"(?:treatment|management|therapy|indication)\s+(?:of|for)", s, re.IGNORECASE):
                conditions.append(s[:200])
    return " ".join(conditions[:2]) if conditions else ""


def _extract_mechanism(texts: list[str], drug_name: str) -> str:
    """Extract mechanism of action from textbook passages."""
    sentences = []
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            s = s.strip()
            if not s or len(s) < 20:
                continue
            lower = s.lower()
            if any(kw in lower for kw in ["mechanism of action", "acts by", "acts as",
                                           "inhibits", "blocks", "stimulates", "activates",
                                           "binds to", "antagonist", "agonist",
                                           "inhibition of", "blockade of"]):
                sentences.append(s)
    if sentences:
        best = max(sentences, key=len)
        return best[:500]
    return ""


def _extract_dosage(texts: list[str], drug_name: str) -> str:
    """Extract adult dosage from textbook passages."""
    sentences = []
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            s = s.strip()
            if not s or len(s) < 10:
                continue
            lower = s.lower()
            if any(kw in lower for kw in ["dosage", "dose", "dosing",
                                           "mg", "mcg", "gram", "daily dose",
                                           "administered", "given orally",
                                           "recommended dose", "usual dose"]):
                if re.search(r"\d+\s*(mg|mcg|g|ml|unit)", lower):
                    sentences.append(s)
    if sentences:
        return " ".join(sentences[:2])[:500]
    return ""


def _extract_drug_class(texts: list[str], drug_name: str) -> str:
    """Extract drug class from textbook passages."""
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            s = s.strip()
            lower = s.lower()
            if any(kw in lower for kw in ["is a", "belongs to", "class of",
                                           "is an", "are a class", "group of drugs",
                                           "type of"]):
                if len(s) < 200:
                    return s[:150]
    return ""


def _extract_contraindications(texts: list[str], drug_name: str) -> str:
    """Extract contraindications from textbook passages."""
    sentences = []
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            s = s.strip()
            if not s or len(s) < 15:
                continue
            lower = s.lower()
            if any(kw in lower for kw in ["contraindicated", "should not be used",
                                           "should be avoided", "not recommended in",
                                           "contraindication", "contraindications",
                                           "absolute contraindication"]):
                sentences.append(s)
    if sentences:
        return ". ".join(sentences[:3])[:500]
    return ""


def _extract_side_effects(texts: list[str], drug_name: str) -> str:
    """Extract side effects from textbook passages."""
    sentences = []
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            s = s.strip()
            if not s or len(s) < 15:
                continue
            lower = s.lower()
            if any(kw in lower for kw in ["adverse effect", "side effect",
                                           "adverse reaction", "common side",
                                           "most common", "may cause",
                                           "toxicity", "can cause"]):
                sentences.append(s)
    if sentences:
        return ". ".join(sentences[:3])[:500]
    return ""


def _extract_warnings(texts: list[str], drug_name: str) -> str:
    """Extract warnings from textbook passages."""
    sentences = []
    for t in texts:
        if _is_index_content(t):
            continue
        t_clean = _clean_section_text(t)
        for s in _get_matching_sentences(t_clean, drug_name):
            s = s.strip()
            if not s or len(s) < 15:
                continue
            lower = s.lower()
            if any(kw in lower for kw in ["warning", "caution", "precaution",
                                           "should be used with", "should be monitored",
                                           "risk of", "may increase the risk"]):
                sentences.append(s)
    if sentences:
        return ". ".join(sentences[:3])[:500]
    return ""


def _search_library(drug_name: str) -> list[str]:
    """Search the medical library for information about a drug.

    Returns only texts that mention the drug by name.
    """
    texts: list[str] = []
    query = f"{drug_name} pharmacology clinical indications dosage mechanism side effects contraindications"

    try:
        from app.domain.medical_library.retriever import search as lib_search
        results = lib_search(query, top_k=8, use_hybrid=False)
        if results:
            for r in results:
                text = r.get("text", "")
                if text and len(text) > 80 and _mentions_drug(text, drug_name):
                    texts.append(text)
    except Exception as e:
        logger.warning(f"  Library search failed: {e}")

    try:
        query_emb = embedding_service.embed(query)
        vec_results = vector_store.search(query_emb, top_k=5)
        for r in vec_results:
            payload = r.get("payload", {})
            text = payload.get("text", "") or payload.get("content", "")
            if text and len(text) > 80 and _mentions_drug(str(text), drug_name):
                texts.append(str(text))
    except Exception as e:
        logger.warning(f"  Vector search failed: {e}")

    return texts


def enrich_drug(drug: DrugEntry, session: Session) -> dict[str, Any]:
    """Enrich a single drug record from textbook content."""
    name = drug.generic_name or ""
    if not name:
        return {"status": "skipped", "reason": "no name"}

    texts = _search_library(name)

    if not texts:
        return {"status": "skipped", "reason": "no textbook content"}

    updates: dict[str, Any] = {}

    indications = _extract_indications(texts, name)
    if indications:
        updates["indications"] = indications

    mechanism = _extract_mechanism(texts, name)
    if mechanism:
        updates["mechanism_of_action"] = mechanism

    dosage = _extract_dosage(texts, name)
    if dosage:
        updates["adult_dose"] = dosage

    drug_class = _extract_drug_class(texts, name)
    if drug_class:
        updates["drug_class"] = drug_class

    contraindications = _extract_contraindications(texts, name)
    if contraindications:
        updates["contraindications"] = contraindications

    side_effects = _extract_side_effects(texts, name)
    if side_effects:
        updates["common_side_effects"] = side_effects

    warnings = _extract_warnings(texts, name)
    if warnings:
        updates["warnings"] = warnings

    if not updates:
        return {"status": "skipped", "reason": "no fields extracted"}

    try:
        for field, value in updates.items():
            setattr(drug, field, value)
        session.commit()
        return {"status": "enriched", "fields": list(updates.keys()), "drug": name}
    except Exception as e:
        session.rollback()
        return {"status": "error", "reason": str(e), "drug": name}


def main():
    parser = argparse.ArgumentParser(description="Enrich sparse drug records from textbooks")
    parser.add_argument("--limit", type=int, default=0, help="Max drugs to process (0 = all)")
    parser.add_argument("--drug", type=str, default="", help="Enrich a specific drug by name")
    parser.add_argument("--resume", action="store_true", help="Skip drugs that already have any rich fields")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Find drugs to enrich
        query = db.query(DrugEntry)

        if args.drug:
            query = query.filter(DrugEntry.generic_name.ilike(f"%{args.drug}%"))
        elif args.resume:
            # Skip drugs that already have enough data
            conditions = [getattr(DrugEntry, f).is_(None) for f in RICH_FIELDS]
            from sqlalchemy import and_
            query = query.filter(and_(*conditions))

        candidates = query.all()
        if args.limit > 0:
            candidates = candidates[:args.limit]

        logger.info(f"Found {len(candidates)} drugs to process")

        enriched = 0
        skipped = 0
        errors = 0

        for i, drug in enumerate(candidates):
            name = drug.generic_name or f"id={drug.id}"
            logger.info(f"[{i+1}/{len(candidates)}] {name}")

            result = enrich_drug(drug, db)

            if result["status"] == "enriched":
                enriched += 1
                logger.info(f"  ✅ Enriched with {len(result['fields'])} fields: {', '.join(result['fields'])}")
            elif result["status"] == "skipped":
                skipped += 1
                logger.info(f"  ⏭️ Skipped: {result.get('reason', '')}")
            else:
                errors += 1
                logger.warning(f"  ❌ Error: {result.get('reason', '')}")

            if (i + 1) % 25 == 0:
                logger.info(f"Progress: {i+1}/{len(candidates)} — enriched={enriched} skipped={skipped} errors={errors}")

        logger.info(f"\nDone! enriched={enriched} skipped={skipped} errors={errors} total={len(candidates)}")

    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
