import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models.drug_database import DrugEntry
from app.schemas.drug_monograph import DrugIdentity

logger = logging.getLogger("drug_resolver")

class DrugResolverService:
    """
    Stage 1: Drug Resolver
    Maps user queries (brands, misspellings, abbreviations) into a 
    standardized Generic Identity (Generic Name, RxCUI, ATC) before 
    retrieval begins.
    """
    def __init__(self, db: Session):
        self.db = db

    def resolve(self, query: str) -> Optional[DrugIdentity]:
        """
        Attempts to resolve a raw text query to a canonical drug identity.
        Uses PostgreSQL indexed fields (generic_name, brand_name, etc).
        """
        if not query or not query.strip():
            return None

        clean_query = query.strip().lower()
        
        # 1. Exact match on generic_name
        entry = self.db.query(DrugEntry).filter(
            func.lower(DrugEntry.generic_name) == clean_query
        ).first()

        # 2. Match on brand_names (JSON) or legacy brand_name
        if not entry:
            entry = self.db.query(DrugEntry).filter(
                or_(
                    func.lower(DrugEntry.brand_name).contains(clean_query),
                    func.lower(DrugEntry.generic_name).contains(clean_query)
                )
            ).first()

        if entry:
            # Reconstruct brand names
            brands = []
            if entry.brand_names and isinstance(entry.brand_names, list):
                brands = entry.brand_names
            elif entry.brand_name:
                brands = [b.strip() for b in entry.brand_name.split(",")]
            
            # Remove duplicates while preserving order
            seen = set()
            brands = [b for b in brands if not (b in seen or seen.add(b))]

            return DrugIdentity(
                generic_name=entry.generic_name.title(),
                rxcui=entry.rxnorm_id or entry.rxcui,
                atc=entry.atc_code,
                brand_names=brands
            )

        # Fallback: if we can't find it in the DB, we might still want to 
        # allow the query to pass through as a generic search for the next layers.
        # But for the true deterministic pipeline, we should probably return a basic 
        # identity struct so Stage 2 can try to find it in textbooks.
        return DrugIdentity(
            generic_name=query.title()
        )
