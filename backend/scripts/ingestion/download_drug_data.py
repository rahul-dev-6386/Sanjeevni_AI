import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from app.services.drug_service import DrugService


COMMON_DRUGS = [
    "metformin", "lisinopril", "atorvastatin", "amlodipine", "omeprazole",
    "levothyroxine", "metoprolol", "losartan", "albuterol", "hydrochlorothiazide",
    "simvastatin", "aspirin", "ibuprofen", "acetaminophen", "prednisone",
    "warfarin", "clopidogrel", "furosemide", "spironolactone", "gabapentin",
    "sertraline", "fluoxetine", "escitalopram", "duloxetine", "venlafaxine",
    "insulin glargine", "insulin lispro", "sitagliptin", "empagliflozin", "liraglutide",
    "rosuvastatin", "fenofibrate", "carvedilol", "diltiazem", "verapamil",
    "montelukast", "fluticasone", "tiotropium", "pantoprazole", "ranitidine",
    "tramadol", "oxycodone", "morphine", "fentanyl", "diazepam",
    "alprazolam", "lorazepam", "clonazepam", "methylphenidate", "donepezil",
]


def download_drug_data():
    print(f"Downloading drug data for {len(COMMON_DRUGS)} common medications...")
    db = SessionLocal()
    try:
        service = DrugService(db)
        count = 0
        for drug_name in COMMON_DRUGS:
            try:
                drug_data = service.search_openfda(drug_name)
                if drug_data and drug_data.get("generic_name"):
                    service.store_drug(drug_data)
                    count += 1
                    display = drug_data.get("brand_name") or drug_data.get("generic_name")
                    print(f"  ✓ {display}")
                else:
                    print(f"  - {drug_name}: no data")
            except Exception as e:
                print(f"  ✗ {drug_name}: {e}")

        total = service.count()
        print(f"\nDownloaded: {count} drugs, {total} total in database")
    finally:
        db.close()


if __name__ == "__main__":
    download_drug_data()
