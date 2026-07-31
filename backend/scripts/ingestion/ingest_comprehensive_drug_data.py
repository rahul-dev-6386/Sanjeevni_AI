"""
Comprehensive drug data ingestion script.

Queries all configured sources (DailyMed → OpenFDA → RxNorm → MedlinePlus)
in priority order, merges results, stores them in the database, and
generates embeddings.

Usage:
    python scripts/ingestion/ingest_comprehensive_drug_data.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from app.services.drug_service import DrugService
from app.services.drug_sources import SOURCE_PRIORITY

# 100+ commonly prescribed medications
COMMON_DRUGS = [
    # Diabetes & Endocrine
    "metformin", "insulin glargine", "insulin lispro", "sitagliptin",
    "empagliflozin", "liraglutide", "levothyroxine", "methimazole",
    "prednisone", "dexamethasone", "hydrocortisone",

    # Cardiovascular
    "lisinopril", "losartan", "amlodipine", "metoprolol", "carvedilol",
    "atenolol", "diltiazem", "verapamil", "hydrochlorothiazide",
    "furosemide", "spironolactone", "atorvastatin", "rosuvastatin",
    "simvastatin", "pravastatin", "ezetimibe", "fenofibrate",
    "warfarin", "clopidogrel", "apixaban", "rivaroxaban",
    "digoxin", "nitroglycerin", "isosorbide mononitrate",

    # GI
    "omeprazole", "pantoprazole", "esomeprazole", "rabeprazole",
    "ranitidine", "famotidine", "metoclopramide", "ondansetron",
    "loperamide", "bismuth subsalicylate", "mesalamine",
    "ursodiol", "lactulose", "polyethylene glycol",

    # Respiratory
    "albuterol", "salmeterol", "fluticasone", "budesonide",
    "montelukast", "tiotropium", "ipratropium", "theophylline",

    # CNS / Psychiatric
    "sertraline", "fluoxetine", "escitalopram", "citalopram",
    "paroxetine", "duloxetine", "venlafaxine", "bupropion",
    "mirtazapine", "trazodone", "quetiapine", "olanzapine",
    "risperidone", "aripiprazole", "haloperidol", "lithium",
    "clonazepam", "alprazolam", "lorazepam", "diazepam",
    "zolpidem", "eszopiclone", "methylphenidate", "amphetamine",
    "donepezil", "memantine", "levodopa", "ropinirole",

    # Pain & Inflammation
    "ibuprofen", "naproxen", "diclofenac", "celecoxib",
    "acetaminophen", "tramadol", "oxycodone", "morphine",
    "hydromorphone", "fentanyl", "methadone", "buprenorphine",
    "gabapentin", "pregabalin", "cyclobenzaprine", "baclofen",

    # Antibiotics & Anti-infectives
    "amoxicillin", "amoxicillin clavulanate", "azithromycin",
    "clarithromycin", "doxycycline", "minocycline", "ciprofloxacin",
    "levofloxacin", "sulfamethoxazole trimethoprim",
    "metronidazole", "clindamycin", "vancomycin", "linezolid",
    "nitrofurantoin", "fluconazole", "terbinafine", "acyclovir",
    "oseltamivir", "remdesivir",

    # Oncology & Immunomodulators
    "methotrexate", "hydroxychloroquine", "sulfasalazine",
    "azathioprine", "mycophenolate", "tacrolimus", "cyclosporine",

    # Hematology
    "aspirin", "enoxaparin", "heparin", "tranexamic acid",

    # Urology
    "tamsulosin", "finasteride", "dutasteride", "oxybutynin",

    # Ophthalmology
    "latanoprost", "timolol", "dorzolamide", "brimonidine",

    # Vitamins & Electrolytes
    "potassium chloride", "magnesium oxide", "folic acid",
    "cyanocobalamin", "cholecalciferol",
]


def ingest_all():
    print(f"Ingesting {len(COMMON_DRUGS)} drugs from multiple sources...")
    db = SessionLocal()
    try:
        service = DrugService(db)
        count = 0
        errors = 0

        for i, drug_name in enumerate(COMMON_DRUGS):
            try:
                print(f"\n[{i+1}/{len(COMMON_DRUGS)}] {drug_name}")

                # Try local DB first by exact generic_name match
                from app.models.drug_database import DrugEntry
                existing_entry = db.query(DrugEntry).filter(DrugEntry.generic_name.ilike(drug_name)).first()
                if existing_entry:
                    field_count_before = len([c for c in DrugEntry.__table__.columns if getattr(existing_entry, c.name, None) is not None])
                    # Re-query sources to enrich existing entry
                    merged = service.search_all_sources(drug_name)
                    if merged.get("generic_name"):
                        stored = service.store_drug(merged)
                        if stored:
                            field_count_after = len([c for c in DrugEntry.__table__.columns if getattr(stored, c.name, None) is not None])
                            delta = field_count_after - field_count_before
                            if delta > 0:
                                print(f"  ✓ Updated ({delta} new fields, total {field_count_after})")
                            else:
                                print(f"  ✓ Already in database ({field_count_before} fields)")
                        else:
                            print(f"  ✓ Already in database ({field_count_before} fields)")
                    else:
                        print(f"  ✓ Already in database ({field_count_before} fields)")
                    count += 1
                    continue

                # Query all sources
                merged = service.search_all_sources(drug_name)
                if merged.get("generic_name"):
                    stored = service.store_drug(merged)
                    if stored:
                        sources = merged.get("data_sources", {})
                        used = set()
                        for fields in sources.values():
                            used.update(fields)
                        print(f"  ✓ Stored ({len(used)} sources: {', '.join(sorted(used))})")
                        count += 1
                    else:
                        print(f"  - Store failed")
                else:
                    print(f"  - No data from any source")

                # Be nice to APIs
                time.sleep(0.3)

            except Exception as e:
                print(f"  ✗ Error: {e}")
                errors += 1
                time.sleep(1.0)

        total = service.count()
        print(f"\n{'='*50}")
        print(f"Complete: {count} ingested, {errors} errors")
        print(f"Total in database: {total}")
    finally:
        db.close()


def reindex_embeddings():
    """Regenerate embeddings for all existing drugs from their stored data."""
    print("\nRe-indexing all existing drugs...")
    db = SessionLocal()
    try:
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
    from app.models.drug_database import DrugEntry
    from app.infrastructure.embedding_service import embedding_service
    from app.infrastructure.vector_store import vector_store

    ingest_all()

    import sys
    if "--reindex" in sys.argv:
        reindex_embeddings()
