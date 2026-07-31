import logging
from typing import List, Dict, Any, Optional

from app.schemas.drug_monograph import (
    DrugMonograph,
    DrugIdentity,
    ConfidenceScore,
    AdverseEffects
)

logger = logging.getLogger("drug_validation")

class DrugValidationService:
    """
    Stage 2-7: Drug Validation & Extractor Service
    Enforces Strict Source Ownership, rejects drug contamination, 
    identifies contradictions, and assigns field-level confidence scores.
    """

    # Ownership Mapping
    OWNER_TEXTBOOK = ["mechanism_of_action", "pharmacokinetics", "clinical_pearls"]
    OWNER_DAILYMED = ["approved_uses", "dosage", "contraindications", "warnings", "adverse_effects", "pregnancy", "lactation", "storage"]
    OWNER_SHARED = ["overview", "drug_interactions", "monitoring"]

    def __init__(self, cleaner_service: 'EvidenceCleanerService'):
        self.cleaner_service = cleaner_service

    def build_monograph(self, identity: DrugIdentity, textbook_chunks: List[Dict[str, Any]], dailymed_data: Optional[Dict[str, Any]] = None) -> DrugMonograph:
        """
        Takes raw retrieved data, applies source enforcement, validates, 
        and outputs the deterministic structured JSON.
        """
        # 1. Initialize the Monograph
        monograph = DrugMonograph(identity=identity)
        
        # 2. Extract Textbook Pharmacology using Agent 1 (EvidenceCleanerService)
        textbook_sources = set()
        clean_chunks = []
        for chunk in textbook_chunks:
            source = chunk.get("source_book", "Medical Textbook")
            text = chunk.get("text", "").strip()
            
            # Contamination Validator (Stage 6)
            if self._has_cross_drug_contamination(identity.generic_name, text):
                monograph.clinical_notes.append(f"Flagged a {source} excerpt containing references to other drugs. Excluded to prevent contamination.")
                continue
            
            textbook_sources.add(source)
            clean_chunks.append(text)
            
        if clean_chunks:
            cleaned_evidence = self.cleaner_service.clean_textbook_chunks(identity.generic_name, clean_chunks)
            self._apply_cleaned_textbook_evidence(monograph, cleaned_evidence, textbook_sources)

        # 3. Extract FDA Data from DailyMed (If available)
        dailymed_used = False
        if dailymed_data:
            dailymed_used = True
            self._extract_dailymed_fields(monograph, dailymed_data)
        
        # 4. Add Successful Sources
        if dailymed_used:
            monograph.evidence_sources.append("DailyMed")
        monograph.evidence_sources.extend(list(textbook_sources))
        if not monograph.evidence_sources:
            monograph.evidence_sources.append("No verified sources found")

        # 5. Calculate Confidence (Stage 7)
        self._calculate_confidence(monograph, dailymed_used, bool(textbook_chunks))
        
        return monograph

    def _has_cross_drug_contamination(self, target_drug: str, text: str) -> bool:
        """Checks if a chunk focuses heavily on a completely different generic drug."""
        target_lower = target_drug.lower().split()[0]
        text_lower = text.lower()
        
        known_drugs = [
            "sildenafil", "tadalafil", "vardenafil", "avanafil",
            "metformin", "lisinopril", "atorvastatin", "warfarin", "digoxin",
            "ibuprofen", "amoxicillin", "omeprazole", "losartan", "amlodipine",
            "nitroglycerin", "verapamil", "diltiazem", "milrinone", "cilostazol",
            "hydrochlorothiazide", "furosemide", "spironolactone",
        ]
        
        for other_drug in known_drugs:
            if other_drug == target_lower:
                continue
            # If another major drug is mentioned 3+ times, flag it.
            if text_lower.count(other_drug) >= 3:
                return True
        return False

    def _apply_cleaned_textbook_evidence(self, mono: DrugMonograph, evidence: 'CleanedTextbookEvidence', sources: set):
        """Applies the structured data from Agent 1 into the Monograph"""
        source_str = ", ".join(list(sources)) if sources else "Medical Textbooks"
        
        if evidence.mechanism_of_action:
            mono.mechanism_of_action = evidence.mechanism_of_action
            mono.field_confidence["mechanism_of_action"] = ConfidenceScore(score=4, source=source_str)
            
        if evidence.pharmacokinetics:
            mono.pharmacokinetics = evidence.pharmacokinetics
            mono.field_confidence["pharmacokinetics"] = ConfidenceScore(score=4, source=source_str)
            
        if evidence.clinical_pearls:
            mono.clinical_pearls = evidence.clinical_pearls
            
        # Optional: interactions if not handled by DailyMed
        if evidence.interactions and not mono.drug_interactions:
            for i in evidence.interactions:
                mono.drug_interactions[i] = "See prescribing information"
            mono.field_confidence["drug_interactions"] = ConfidenceScore(score=3, source=source_str)

    def _extract_dailymed_fields(self, mono: DrugMonograph, data: Dict[str, Any]):
        """Extracts FDA fields from DailyMed/DB schema"""
        if data.get("indications"):
            mono.approved_uses = [data["indications"]]
            mono.field_confidence["approved_uses"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("adult_dose") or data.get("dosage_info"):
            dose = data.get("adult_dose") or data.get("dosage_info")
            if dose:
                mono.dosage["General"] = dose
                mono.field_confidence["dosage"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("contraindications"):
            mono.contraindications = [data["contraindications"]]
            mono.field_confidence["contraindications"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("warnings") or data.get("boxed_warning"):
            warnings = []
            if data.get("boxed_warning"):
                warnings.append("BOXED WARNING: " + data["boxed_warning"])
            if data.get("warnings"):
                warnings.append(data["warnings"])
            mono.warnings = warnings
            mono.field_confidence["warnings"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("common_side_effects"):
            mono.adverse_effects.common = [data["common_side_effects"]]
        if data.get("serious_side_effects"):
            mono.adverse_effects.serious = [data["serious_side_effects"]]
        if mono.adverse_effects.common or mono.adverse_effects.serious:
            mono.field_confidence["adverse_effects"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("drug_interactions"):
            mono.drug_interactions["General"] = data["drug_interactions"]
            mono.field_confidence["drug_interactions"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("pregnancy"):
            mono.pregnancy = data["pregnancy"]
            mono.field_confidence["pregnancy"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("breastfeeding"):
            mono.lactation = data["breastfeeding"]
            mono.field_confidence["lactation"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("storage_instructions"):
            mono.storage = data["storage_instructions"]
            mono.field_confidence["storage"] = ConfidenceScore(score=5, source="DailyMed")
            
        if data.get("drug_class"):
            mono.drug_class = data["drug_class"]
            
        if data.get("prescription_status"):
            mono.prescription_status = data["prescription_status"]

    def _calculate_confidence(self, mono: DrugMonograph, has_dailymed: bool, has_textbook: bool):
        """
        Validates missing fields and assigns default scores.
        """
        # MoA owned by Textbooks
        if not mono.mechanism_of_action:
            if has_textbook:
                mono.clinical_notes.append("Mechanism of Action was not clearly identified in the available textbook sources.")
            
        # Dosage owned by DailyMed
        if not mono.dosage:
            if has_dailymed:
                mono.clinical_notes.append("Specific dosage information was missing from the FDA product label.")
            else:
                mono.clinical_notes.append("Dosage information is strictly sourced from DailyMed/FDA labels, which were unavailable.")
