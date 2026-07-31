import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.drug_database import DrugEntry, DrugInteraction
from app.infrastructure.embedding_service import embedding_service
from app.infrastructure.vector_store import vector_store
from app.services.drug_sources import SOURCE_PRIORITY

logger = logging.getLogger("drug_service")

# text-embedding-3-small supports up to 8192 tokens (~32k chars for English)
MAX_EMBEDDING_CHARS = 24000

# All DrugEntry fields that can be serialized to the API
SERIALIZABLE_FIELDS = [
    "id",
    "generic_name", "brand_names", "drug_class",
    "pharmacologic_class", "therapeutic_class",
    "rxnorm_id", "atc_code", "unii", "cas_number",
    "indications", "off_label_uses",
    "mechanism_of_action", "pharmacodynamics", "pharmacokinetics",
    "onset_of_action", "duration_of_action", "half_life",
    "adult_dose", "pediatric_dose", "geriatric_dose",
    "renal_dose_adjustment", "hepatic_dose_adjustment",
    "maximum_dose", "dose_forms", "available_strengths",
    "administration", "storage_instructions",
    "preparation", "reconstitution", "compatibility",
    "administration_food_interactions",
    "contraindications", "boxed_warning", "warnings", "precautions",
    "pregnancy", "breastfeeding", "fertility", "driving_warning",
    "common_side_effects", "serious_side_effects",
    "side_effect_frequency", "monitoring",
    "drug_interactions", "food_interactions", "alcohol_interactions",
    "herbal_interactions", "disease_interactions",
    "required_monitoring", "laboratory_tests", "vital_signs", "follow_up",
    "patient_instructions", "missed_dose_instructions",
    "overdose_instructions", "disposal_instructions",
    "toxicity", "antidote", "poisoning_management",
    "guidelines", "clinical_trials", "references",
    "last_updated", "evidence_level",
    "tablet_image_url", "capsule_image_url",
    "package_image_url", "chemical_structure_url",
    "same_class", "same_mechanism", "alternatives",
    "biosimilars", "combination_products",
    "clinical_pearls", "common_mistakes", "faq",
    "monitoring_tips", "high_yield_points",
    "embedding_id", "data_sources",
]

# Legacy field mapping for backward compatibility
LEGACY_FIELDS = {
    "brand_name": "brand_names",
    "side_effects": None,  # split into common/serious
    "dosage_info": "adult_dose",
    "interactions": "drug_interactions",
    "pregnancy_category": "pregnancy",
}

TEXT_FOR_EMBEDDING_KEYS = [
    ("Generic Name", "generic_name"),
    ("Brand Names", lambda d: ", ".join(d["brand_names"]) if d.get("brand_names") else None),
    ("Drug Class", "drug_class"),
    ("Pharmacologic Class", "pharmacologic_class"),
    ("Therapeutic Class", "therapeutic_class"),
    ("Mechanism of Action", "mechanism_of_action"),
    ("Pharmacodynamics", "pharmacodynamics"),
    ("Pharmacokinetics", "pharmacokinetics"),
    ("Indications", "indications"),
    ("Off-Label Uses", "off_label_uses"),
    ("Contraindications", "contraindications"),
    ("Dosage", "adult_dose"),
    ("Pediatric Dose", "pediatric_dose"),
    ("Geriatric Dose", "geriatric_dose"),
    ("Renal Dose Adjustment", "renal_dose_adjustment"),
    ("Hepatic Dose Adjustment", "hepatic_dose_adjustment"),
    ("Maximum Dose", "maximum_dose"),
    ("Administration", "administration"),
    ("Boxed Warning", "boxed_warning"),
    ("Warnings", "warnings"),
    ("Precautions", "precautions"),
    ("Common Side Effects", "common_side_effects"),
    ("Serious Side Effects", "serious_side_effects"),
    ("Drug Interactions", "drug_interactions"),
    ("Food Interactions", "food_interactions"),
    ("Alcohol Interactions", "alcohol_interactions"),
    ("Herbal Interactions", "herbal_interactions"),
    ("Disease Interactions", "disease_interactions"),
    ("Monitoring", "monitoring"),
    ("Required Monitoring", "required_monitoring"),
    ("Laboratory Tests", "laboratory_tests"),
    ("Pregnancy", "pregnancy"),
    ("Breastfeeding", "breastfeeding"),
    ("Fertility", "fertility"),
    ("Driving Warning", "driving_warning"),
    ("Patient Instructions", "patient_instructions"),
    ("Missed Dose", "missed_dose_instructions"),
    ("Overdose", "overdose_instructions"),
    ("Toxicity", "toxicity"),
    ("Antidote", "antidote"),
    ("Clinical Pearls", "clinical_pearls"),
    ("Evidence Level", "evidence_level"),
]


class DrugService:
    def __init__(self, db: Session):
        self.db = db

    # ── Multi-source merge ──

    def search_all_sources(self, drug_name: str) -> dict[str, Any]:
        """Query all data sources in priority order and merge results."""
        result: dict[str, Any] = {}
        data_sources: dict[str, list[str]] = {}

        for source_cls in SOURCE_PRIORITY:
            try:
                source = source_cls()
                source_data = source.search_by_name(drug_name)
                if source_data and source_data.get("generic_name"):
                    # Track which fields came from this source
                    for key in source_data:
                        if source_data[key] is not None:
                            if key not in data_sources:
                                data_sources[key] = []
                            data_sources[key].append(source.source_name)

                    # Merge into result (fill only None fields)
                    result = AbstractDrugSource.merge(result, source_data)

                    # Update generic_name on first find for subsequent source searches
                    if not result.get("generic_name"):
                        result["generic_name"] = source_data.get("generic_name")
            except Exception as e:
                logger.warning(f"{source_cls.__name__} failed for {drug_name}: {e}")
                continue

        if result and data_sources:
            result["data_sources"] = data_sources

        return result

    # ── Store ──

    def store_drug(self, drug_data: dict) -> Optional[DrugEntry]:
        """Store drug data from any source. Creates new entry or merges into existing."""
        try:
            return self._store_drug_impl(drug_data)
        except Exception as e:
            logger.warning(f"store_drug failed: {e}")
            self.db.rollback()
            return None

    def _store_drug_impl(self, drug_data: dict) -> Optional[DrugEntry]:
        generic_name = drug_data.get("generic_name")
        if not generic_name:
            return None

        generic_name = generic_name[:500]

        existing = (
            self.db.query(DrugEntry)
            .filter(DrugEntry.generic_name == generic_name)
            .first()
        )

        if existing:
            merged = False
            for key in SERIALIZABLE_FIELDS:
                if key in ("id", "embedding_id", "ingested_at", "data_sources"):
                    continue
                old_val = getattr(existing, key, None)
                new_val = drug_data.get(key)
                if old_val is None and new_val is not None:
                    setattr(existing, key, new_val)
                    merged = True
            if merged:
                text = self._build_drug_text(self._entry_to_dict(existing))[:MAX_EMBEDDING_CHARS]
                emb = embedding_service.embed_document(text)
                existing.embedding_id = f"drug_{generic_name.lower().replace(' ', '_')}"[:255]
                vector_store.upsert(
                    embedding_id=existing.embedding_id,
                    embedding=emb["embedding"],
                    payload=self._vector_payload(existing),
                )
                self.db.commit()
            return existing

        text_for_embedding = self._build_drug_text(drug_data)[:MAX_EMBEDDING_CHARS]
        embedding_data = embedding_service.embed_document(text_for_embedding)
        embedding_id = f"drug_{generic_name.lower().replace(' ', '_')}"[:255]

        entry = DrugEntry(generic_name=generic_name, embedding_id=embedding_id)
        for key in SERIALIZABLE_FIELDS:
            if key in ("id", "generic_name", "embedding_id", "ingested_at"):
                continue
            val = drug_data.get(key)
            if val is not None:
                setattr(entry, key, val)

        self.db.add(entry)
        self.db.flush()

        vector_store.upsert(
            embedding_id=embedding_id,
            embedding=embedding_data["embedding"],
            payload=self._vector_payload(entry),
        )
        self.db.commit()
        return entry

    # ── Search ──

    def search_drug(self, query: str) -> list[dict]:
        """Search drugs by exact/ILIKE match on generic_name then brand_names.

        Returns richer entries (more populated fields) first.
        NEVER returns unrelated drugs — vector search is only used with a
        confidence threshold and only when the query partially matches.
        """
        from sqlalchemy import cast, String, func

        q = f"%{query}%"
        direct = (
            self.db.query(DrugEntry)
            .filter(DrugEntry.generic_name.ilike(q))
            .all()
        )
        if direct:
            def _richness(entry: DrugEntry) -> int:
                score = 0
                for field in ("indications", "contraindications", "side_effects",
                              "warnings", "drug_interactions", "mechanism_of_action",
                              "adult_dose", "boxed_warning"):
                    if getattr(entry, field, None):
                        score += 1
                return score
            direct.sort(key=_richness, reverse=True)
            return [self._entry_to_dict(d) for d in direct[:5]]

        brand_matches = (
            self.db.query(DrugEntry)
            .filter(func.lower(cast(DrugEntry.brand_names, String)).ilike(q))
            .limit(3)
            .all()
        )
        if brand_matches:
            return [self._entry_to_dict(d) for d in brand_matches]

        # No exact/ILIKE match — try vector search only if query partially
        # resembles a known drug name (avoids returning "Digoxin" for "Dolo")
        query_lower = query.lower().strip()
        name_prefixes = (
            self.db.query(DrugEntry.generic_name)
            .filter(
                DrugEntry.generic_name.ilike(f"{query_lower[:3]}%")
            )
            .limit(1)
            .all()
        )
        if not name_prefixes:
            # Query doesn't start like any known drug — return empty
            return []

        query_emb = embedding_service.embed(query)
        results = vector_store.search(query_emb, top_k=3)
        enriched = []
        for r in results:
            if r["payload"].get("type") == "drug":
                score = r.get("score", 0)
                # Confidence threshold: reject scores below 0.7
                if score < 0.7:
                    continue
                generic_name = r["payload"].get("generic_name")
                if generic_name:
                    entry = (
                        self.db.query(DrugEntry)
                        .filter(DrugEntry.generic_name == generic_name)
                        .first()
                    )
                    if entry:
                        d = self._entry_to_dict(entry)
                        d["score"] = score
                        enriched.append(d)
        return enriched

    # ── Interactions ──

    def get_interactions(self, drug_names: list[str]) -> list[dict]:
        """Look up interactions between the given drugs."""
        results = []
        for i, a in enumerate(drug_names):
            for b in drug_names[i + 1:]:
                interaction = (
                    self.db.query(DrugInteraction)
                    .filter(
                        ((DrugInteraction.drug_a_generic.ilike(a)) &
                         (DrugInteraction.drug_b_generic.ilike(b))) |
                        ((DrugInteraction.drug_a_generic.ilike(b)) &
                         (DrugInteraction.drug_b_generic.ilike(a)))
                    )
                    .first()
                )
                if interaction:
                    results.append({
                        "drugs": [interaction.drug_a_generic, interaction.drug_b_generic],
                        "severity": interaction.severity,
                        "mechanism": interaction.mechanism,
                        "clinical_effect": interaction.clinical_effect,
                        "management": interaction.management,
                        "references": interaction.references,
                    })
        return results

    def count(self) -> int:
        return self.db.query(DrugEntry).count()

    # ── Helpers ──

    def _build_drug_text(self, drug_data: dict) -> str:
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

    def _vector_payload(self, entry: DrugEntry) -> dict:
        return {
            "type": "drug",
            "generic_name": entry.generic_name,
            "brand_name": entry.brand_name or "",
            "drug_class": entry.drug_class or "",
            "pharmacologic_class": entry.pharmacologic_class or "",
            "rxnorm_id": entry.rxnorm_id or "",
            "atc_code": entry.atc_code or "",
        }

    def _entry_to_dict(self, entry: DrugEntry) -> dict:
        """Serialize a DrugEntry to a flat dict with all fields."""
        result = {}
        for field in SERIALIZABLE_FIELDS:
            val = getattr(entry, field, None)
            if val is not None:
                result[field] = val
        return result

    def store_interaction(self, interaction_data: dict) -> DrugInteraction:
        """Store a drug interaction record."""
        existing = (
            self.db.query(DrugInteraction)
            .filter(
                DrugInteraction.drug_a_generic.ilike(interaction_data["drug_a"]),
                DrugInteraction.drug_b_generic.ilike(interaction_data["drug_b"]),
            )
            .first()
        )
        if existing:
            return existing
        interaction = DrugInteraction(
            drug_a_generic=interaction_data["drug_a"],
            drug_b_generic=interaction_data["drug_b"],
            severity=interaction_data["severity"],
            mechanism=interaction_data.get("mechanism"),
            clinical_effect=interaction_data.get("clinical_effect"),
            management=interaction_data.get("management"),
            references=interaction_data.get("references"),
            evidence_level=interaction_data.get("evidence_level"),
            source=interaction_data.get("source"),
        )
        self.db.add(interaction)
        self.db.commit()
        return interaction


from app.services.drug_sources.base import AbstractDrugSource  # noqa: E402
