"""
Reindex all drugs from PostgreSQL into Qdrant with current embedding model.
Does NOT call external APIs. Does NOT modify PostgreSQL data.
Only regenerates vector embeddings for the medical_knowledge collection.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.drug_database import DrugEntry
from app.infrastructure.embedding_service import embedding_service
from app.infrastructure.vector_store import vector_store
from app.services.drug_service import DrugService, TEXT_FOR_EMBEDDING_KEYS, MAX_EMBEDDING_CHARS


def build_drug_text(drug_data: dict) -> str:
    """Build a rich text block for embedding from all available fields."""
    parts = []
    for label, field in TEXT_FOR_EMBEDDING_KEYS:
        if isinstance(field, str):
            val = drug_data.get(field)
        else:
            val = field(drug_data)
        if val:
            parts.append(f"{label}: {val}")
    return "\n\n".join(parts)


def entry_to_dict(entry: DrugEntry) -> dict:
    """Serialize a DrugEntry to a flat dict with all fields."""
    result = {}
    for col in DrugEntry.__table__.columns:
        val = getattr(entry, col.name, None)
        if val is not None:
            result[col.name] = val
    return result


def vector_payload(entry: DrugEntry) -> dict:
    """Create the payload for Qdrant vector storage."""
    return {
        "type": "drug",
        "generic_name": entry.generic_name,
        "brand_name": entry.brand_name or "",
        "drug_class": entry.drug_class or "",
        "pharmacologic_class": entry.pharmacologic_class or "",
        "rxnorm_id": entry.rxnorm_id or "",
        "atc_code": entry.atc_code or "",
    }


def reindex_all():
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        drugs = db.query(DrugEntry).all()
        total = len(drugs)
        print(f"Found {total} drugs in PostgreSQL")
        print(f"Embedding model: {settings.EMBEDDING_MODEL}")
        print(f"Embedding dimension: {settings.EMBEDDING_DIMENSION}")
        print(f"Qdrant collection: {settings.QDRANT_COLLECTION}")
        print()

        success = 0
        failed = 0
        failed_drugs = []

        for i, drug in enumerate(drugs):
            try:
                drug_dict = entry_to_dict(drug)
                drug_text = build_drug_text(drug_dict)[:MAX_EMBEDDING_CHARS]

                if not drug_text.strip():
                    print(f"  [{i+1}/{total}] SKIP  {drug.generic_name} (empty text)")
                    failed += 1
                    failed_drugs.append((drug.generic_name, "empty text"))
                    continue

                emb = embedding_service.embed_document(drug_text)
                embedding = emb["embedding"]

                if len(embedding) != settings.EMBEDDING_DIMENSION:
                    print(f"  [{i+1}/{total}] FAIL  {drug.generic_name} (dim={len(embedding)}, expected={settings.EMBEDDING_DIMENSION})")
                    failed += 1
                    failed_drugs.append((drug.generic_name, f"wrong dim {len(embedding)}"))
                    continue

                vector_store.upsert(
                    embedding_id=drug.embedding_id,
                    embedding=embedding,
                    payload=vector_payload(drug),
                )

                success += 1
                if (i + 1) % 50 == 0 or (i + 1) == total:
                    print(f"  [{i+1}/{total}] progress: {success} ok, {failed} failed")

            except Exception as e:
                failed += 1
                failed_drugs.append((drug.generic_name, str(e)))
                print(f"  [{i+1}/{total}] ERROR {drug.generic_name}: {e}")
                time.sleep(0.5)

        print(f"\n{'='*60}")
        print(f"REINDEX COMPLETE")
        print(f"{'='*60}")
        print(f"Drugs found:    {total}")
        print(f"Embedded:       {success}")
        print(f"Failed:         {failed}")
        if failed_drugs:
            print(f"\nFailed drugs:")
            for name, reason in failed_drugs[:20]:
                print(f"  - {name}: {reason}")

        # Verify Qdrant count
        from qdrant_client import QdrantClient
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        info = client.get_collection(settings.QDRANT_COLLECTION)
        print(f"\nQdrant {settings.QDRANT_COLLECTION}:")
        print(f"  Points: {info.points_count}")
        print(f"  Dimension: {info.config.params.vectors.size}")
        print(f"  Status: {info.status}")

        return success, failed

    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    reindex_all()
