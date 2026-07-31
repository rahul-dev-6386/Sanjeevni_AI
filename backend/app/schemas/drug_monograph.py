from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class ConfidenceScore(BaseModel):
    score: int = Field(..., ge=1, le=5, description="Confidence out of 5 stars")
    source: str = Field(..., description="The source responsible for this fact")
    notes: Optional[str] = Field(None, description="E.g., conflicts resolved or notes on partial data")

class AdverseEffects(BaseModel):
    common: List[str] = Field(default_factory=list)
    serious: List[str] = Field(default_factory=list)

class DrugIdentity(BaseModel):
    """Stage 1: Resolved drug identity."""
    generic_name: str
    rxcui: Optional[str] = None
    atc: Optional[str] = None
    brand_names: List[str] = Field(default_factory=list)

class DrugMonograph(BaseModel):
    """Stage 3 & 4: Structured, source-aware JSON for the drug monograph."""
    
    # Identity (Owner: RxNorm)
    identity: DrugIdentity
    
    # Classification & Status
    drug_class: Optional[str] = None
    prescription_status: Optional[str] = None

    # Overview
    overview: Optional[str] = None

    # Pharmacology (Owner: Textbooks)
    mechanism_of_action: Optional[str] = None
    pharmacokinetics: Optional[str] = None
    clinical_pearls: List[str] = Field(default_factory=list)

    # FDA/Clinical Data (Owner: DailyMed)
    approved_uses: List[str] = Field(default_factory=list)
    dosage: Dict[str, str] = Field(default_factory=dict, description="Indication -> Dosage mapping")
    contraindications: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list, description="General & Boxed Warnings")
    pregnancy: Optional[str] = None
    lactation: Optional[str] = None
    monitoring: Optional[str] = None
    storage: Optional[str] = None
    
    adverse_effects: AdverseEffects = Field(default_factory=AdverseEffects)
    drug_interactions: Dict[str, str] = Field(default_factory=dict, description="Interacting Drug -> Effect")

    # Stage 6 & 7: Validation & Confidence
    clinical_notes: List[str] = Field(default_factory=list, description="Contradictions, conflicts flagged by validators")
    evidence_sources: List[str] = Field(default_factory=list, description="List of successful sources (e.g. DailyMed, Textbooks)")
    field_confidence: Dict[str, ConfidenceScore] = Field(
        default_factory=dict, 
        description="Granular confidence for fields (e.g. 'mechanism_of_action': ConfidenceScore(5, 'Goodman & Gilman'))"
    )
