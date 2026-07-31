"""
Load existing DailyMed JSON files and store them in the database.
"""
import json
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.database import SessionLocal
from app.domain.dailymed.models import DrugDocument
from app.domain.dailymed.storage import store_drug_document
from app.models.drug_database import DrugEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("bulk_import")

json_dir = Path("data/dailymed_json")
files = sorted(json_dir.glob("*.json"))

db = SessionLocal()
try:
    existing = {r[0] for r in db.query(DrugEntry.generic_name).all()}
    logger.info(f"Existing drugs in DB: {len(existing)}")

    imported = 0
    skipped = 0
    failed = 0

    for fpath in files:
        drug_name = fpath.stem

        with open(fpath) as f:
            data = json.load(f)

        # Check if it has any clinical data at all
        has_data = False
        for section in ('clinical', 'safety', 'dosage', 'interactions', 'pregnancy', 'emergency'):
            sub = data.get(section, {})
            for k, v in sub.items():
                if v and isinstance(v, str) and len(v) > 20:
                    has_data = True
                    break
            if has_data:
                break

        if not has_data:
            logger.info(f"  SKIP {drug_name} (empty)")
            skipped += 1
            continue

        doc = DrugDocument(**data)
        ok = store_drug_document(doc, db=db)
        if ok:
            imported += 1
            logger.info(f"  OK   {drug_name}")
        else:
            failed += 1
            logger.warning(f"  FAIL {drug_name}")

    logger.info(f"\nDone: {imported} imported, {skipped} skipped, {failed} failed")
    logger.info(f"Total in DB: {len(existing)}")
finally:
    db.close()
