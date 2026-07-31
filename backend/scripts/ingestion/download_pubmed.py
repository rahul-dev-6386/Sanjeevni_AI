import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings
from app.core.database import SessionLocal
from app.infrastructure.pubmed_service import PubMedService


PUBMED_QUERIES = [
    "diabetes mellitus type 2 management guidelines",
    "hypertension treatment guidelines 2024",
    "cardiovascular disease prevention",
    "chronic kidney disease management",
    "asthma management guidelines",
    "thyroid disorders clinical practice",
    "obesity management guidelines",
    "mental health depression treatment",
    "nutrition dietary guidelines chronic disease",
    "vaccination immunology preventive medicine",
    "sleep disorders clinical management",
    "pain management clinical guidelines",
    "antibiotic stewardship guidelines",
    "women's health pregnancy guidelines",
    "pediatric growth development guidelines",
]


def download_pubmed():
    print(f"Downloading PubMed articles for {len(PUBMED_QUERIES)} topics...")
    db = SessionLocal()
    try:
        service = PubMedService(db)
        total_articles = 0
        for query in PUBMED_QUERIES:
            try:
                articles = service.search_and_fetch(query, max_results=10)
                if articles:
                    service.store_articles(articles)
                    total_articles += len(articles)
                    print(f"  ✓ '{query}': {len(articles)} articles")
                else:
                    print(f"  - '{query}': no results")
            except Exception as e:
                print(f"  ✗ '{query}': error - {e}")

        count = service.count()
        print(f"\nTotal: {total_articles} articles fetched, {count} stored in database")
    finally:
        db.close()


if __name__ == "__main__":
    download_pubmed()
