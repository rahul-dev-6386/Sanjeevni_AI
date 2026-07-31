import sys
import os
import json
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.drug_database import DrugEntry

def check_db():
    db = SessionLocal()
    try:
        drug = db.query(DrugEntry).filter(DrugEntry.generic_name.ilike('%acetaminophen%')).first()
        if drug:
            print(f"Generic Name: {drug.generic_name}")
            print(f"Warnings: {bool(drug.warnings)}")
            print(f"Boxed Warning: {bool(drug.boxed_warning)}")
            print(f"Contraindications: {bool(drug.contraindications)}")
            print(f"Common SE: {bool(drug.common_side_effects)}")
            print(f"Serious SE: {bool(drug.serious_side_effects)}")
            print(f"Interactions: {bool(drug.drug_interactions)}")
            print(f"Pregnancy: {bool(drug.pregnancy)}")
        else:
            print("Drug not found in DB")
    finally:
        db.close()

if __name__ == "__main__":
    check_db()
