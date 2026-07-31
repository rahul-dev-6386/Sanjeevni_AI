"""
WHO Essential Medicines List ingestion script.

Reads the curated WHO EML drug list, queries all 4 data sources
(DailyMed → OpenFDA → RxNorm → MedlinePlus) for each drug, merges
results field-by-field, stores them in the database, and generates
embeddings.

Usage:
    python scripts/ingestion/ingest_who_eml.py
    python scripts/ingestion/ingest_who_eml.py --dry-run
    python scripts/ingestion/ingest_who_eml.py --limit 50
    python scripts/ingestion/ingest_who_eml.py --reindex
    python scripts/ingestion/ingest_who_eml.py --enrich-only
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from app.services.drug_service import DrugService


DRUG_LIST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "drug_lists",
    "who_essential_medicines.json",
)


def load_drug_list() -> list[dict]:
    with open(DRUG_LIST_PATH) as f:
        return json.load(f)


def ingest_all(
    dry_run: bool = False,
    limit: int | None = None,
    enrich_only: bool = False,
):
    drugs = load_drug_list()
    if limit:
        drugs = drugs[:limit]

    if enrich_only:
        print(
            f"Enrich-only mode: updating {len(drugs)} existing drugs from all sources..."
        )
    else:
        print(f"Importing {len(drugs)} drugs from WHO Essential Medicines List...")

    if dry_run:
        print("\nDRY RUN — no changes will be made\n")
        for i, d in enumerate(drugs):
            name = d["generic_name"]
            atc = d.get("atc_code", "")
            atc_str = f"  ATC: {atc}" if atc else ""
            print(f"  [{i+1}/{len(drugs)}] {name}{atc_str}")
        print(f"\nWould import {len(drugs)} drugs")
        return

    db = SessionLocal()
    try:
        service = DrugService(db)
        count = 0
        skipped = 0
        errors = 0

        for i, drug in enumerate(drugs):
            drug_name = drug["generic_name"]
            try:
                existing = None
                if enrich_only:
                    from app.models.drug_database import DrugEntry

                    existing = (
                        db.query(DrugEntry)
                        .filter(DrugEntry.generic_name.ilike(drug_name))
                        .first()
                    )
                    if not existing:
                        print(
                            f"  [{i+1}/{len(drugs)}] {drug_name}  — Not in DB, skipping"
                        )
                        skipped += 1
                        continue

                prefix = "  ✓" if existing else "  +"
                print(f"{prefix} [{i+1}/{len(drugs)}] {drug_name} ...", end=" ", flush=True)

                merged = service.search_all_sources(drug_name)

                if not merged.get("generic_name"):
                    print("No data")
                    skipped += 1
                    continue

                merged["generic_name"] = drug_name

                if drug.get("atc_code") and not merged.get("atc_code"):
                    merged["atc_code"] = drug["atc_code"]
                if drug.get("formulation") and not merged.get("dose_forms"):
                    merged["dose_forms"] = drug["formulation"]

                stored = service.store_drug(merged)
                if stored:
                    sources = merged.get("data_sources", {})
                    used = set()
                    for fields in sources.values():
                        used.update(fields)
                    source_list = ", ".join(sorted(used))
                    if existing:
                        print(f"Enriched ({source_list})")
                    else:
                        print(f"Stored ({source_list})")
                    count += 1
                else:
                    print("Store failed")
                    errors += 1

                time.sleep(0.3)

            except Exception as e:
                print(f"Error: {e}")
                db.rollback()
                errors += 1
                time.sleep(1.0)

        total = service.count()
        print(f"\n{'='*50}")
        print(f"Imported: {count}   Skipped: {skipped}   Errors: {errors}")
        print(f"Total drugs in database: {total}")

    finally:
        db.close()


def reindex_embeddings():
    print("\nRe-indexing all existing drugs...")
    db = SessionLocal()
    try:
        from app.infrastructure.embedding_service import embedding_service
        from app.infrastructure.vector_store import vector_store
        from app.models.drug_database import DrugEntry

        service = DrugService(db)
        drugs = db.query(DrugEntry).all()
        print(f"Found {len(drugs)} drugs to re-index")

        for drug in drugs:
            try:
                text = service._build_drug_text(service._entry_to_dict(drug))[:24000]
                emb = embedding_service.embed_document(text)
                vector_store.upsert(
                    embedding_id=drug.embedding_id,
                    embedding=emb["embedding"],
                    payload=service._vector_payload(drug),
                )
                print(f"  ✓ {drug.generic_name}")
            except Exception as e:
                print(f"  ✗ {drug.generic_name}: {e}")

        print("Re-indexing complete")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest WHO Essential Medicines List into the drug database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print drug list without making any changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to N drugs (useful for testing)",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Only update drugs already in the database (skip new)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Re-generate embeddings for all existing drugs after import",
    )
    args = parser.parse_args()

    ingest_all(
        dry_run=args.dry_run,
        limit=args.limit,
        enrich_only=args.enrich_only,
    )

    if args.reindex:
        reindex_embeddings()
