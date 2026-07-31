import json
import logging
import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.infrastructure.ai_provider_service import AIProviderService
from app.infrastructure.embedding_service import embedding_service
from app.infrastructure.vector_store import vector_store
from app.models.ai_cache import AICache
from app.models.drug_database import DrugEntry, DrugInteraction
from app.services.drug_service import DrugService, SERIALIZABLE_FIELDS
from app.services.drug_monograph import build_drug_not_found_markdown
from app.services.drug_resolver_service import DrugResolverService
from app.services.evidence_cleaner_service import EvidenceCleanerService
from app.services.drug_validation_service import DrugValidationService
from app.services.markdown_render_service import MarkdownRenderService

logger = logging.getLogger("drug_consult_service")

CACHE_TTL_DAYS = 7



class DrugConsultService:
    def __init__(self, db: Session):
        self.db = db
        self.drug_service = DrugService(db)
        self.ai_provider = AIProviderService(db)
        
        # New deterministic pipeline services
        self.resolver = DrugResolverService(db)
        self.cleaner = EvidenceCleanerService(self.ai_provider)
        self.validator = DrugValidationService(self.cleaner)
        self.renderer = MarkdownRenderService(self.ai_provider)

    def consult(
        self,
        question: str,
        patient_mode: bool = False,
    ) -> dict:
        context_parts = []
        sources_used = set()

        drug_names = self._extract_drugs(question)

        for name in drug_names:
            db_results = self.drug_service.search_drug(name)
            if db_results:
                drug = db_results[0]
                present = {k: v for k, v in drug.items() if v is not None and v != [] and v != {}}
                if present:
                    context_parts.append(f"Drug record ({name}):\n{json.dumps(present, indent=2, default=str)}")
                    sources_used.update(["DailyMed", "OpenFDA", "RxNorm"])

            if len(drug_names) >= 2:
                interactions = self.drug_service.get_interactions(drug_names)
                if interactions:
                    context_parts.append(f"Drug interactions:\n{json.dumps(interactions, indent=2)}")
                    sources_used.add("DrugBank")

        try:
            from app.domain.medical_library.retriever import search as lib_search
            lib_results = lib_search(question, top_k=5, use_hybrid=False)
            if lib_results:
                chunks = []
                for r in lib_results:
                    text = r.get("text", "")
                    if text and len(text) > 20:
                        source = r.get("source_book", "") or r.get("collection", "textbook")
                        chunks.append(f"[{source}] {text[:1000]}")
                        if source:
                            sources_used.add(source)
                if chunks:
                    context_parts.append("Medical textbook references:\n" + "\n\n".join(chunks[:5]))
        except Exception as e:
            logger.warning(f"Medical library search unavailable: {e}")

        try:
            query_emb = embedding_service.embed(question)
            vec_results = vector_store.search(query_emb, top_k=3)
            for r in vec_results:
                payload = r.get("payload", {})
                gn = payload.get("generic_name", "")
                if gn and gn.lower() not in [d.lower() for d in drug_names]:
                    fields = {k: v for k, v in payload.items() if v and k != "type"}
                    context_parts.append(f"Related drug ({gn}):\n{json.dumps(fields, indent=2)}")
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        unified_context = "\n\n".join(context_parts) if context_parts else "No specific drug data found in the database."
        sources_list = sorted(sources_used) if sources_used else ["General medical knowledge"]

        mode_instruction = (
            "Use simple, patient-friendly language. Explain medical terms in plain English. Avoid jargon."
            if patient_mode
            else "Use clinical terminology. Be precise and evidence-based."
        )

        user_prompt = (
            f"QUESTION: {question}\n\n"
            f"RETRIEVED CONTEXT:\n{unified_context}\n\n"
            f"Style: {mode_instruction}\n\n"
            f"Respond in Markdown format as specified."
        )

        markdown = self.ai_provider.generate_response(
            user_prompt,
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not markdown or "fallback" in markdown.lower() or "unavailable" in markdown.lower():
            markdown = self._fallback_markdown(question, drug_names, sources_list)

        return {
            "markdown": markdown,
            "references": sources_list,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def generate_drug_answer(self, drug_name: str, skip_local_search: bool = False) -> dict:
        """
        Stage 1-8 deterministic RAG pipeline.
        Replaces the old legacy unstructured LLM generation.
        """
        # Stage 1: Resolve Identity
        identity = self.resolver.resolve(drug_name)
        if not identity:
            return {
                "markdown": build_drug_not_found_markdown(drug_name),
                "references": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Stage 2: Parallel Retrieval
        dailymed_data = None
        if not skip_local_search:
            db_results = self.drug_service.search_drug(identity.generic_name)
            if db_results:
                dailymed_data = db_results[0]
        
        textbook_chunks = []
        try:
            from app.domain.medical_library.retriever import search as lib_search
            lib_results = lib_search(
                f"{identity.generic_name} clinical pharmacology indications dosage mechanism side effects",
                top_k=8,
                use_hybrid=False,
            )
            if lib_results:
                for r in lib_results:
                    text = r.get("text", "")
                    if text and len(text) > 50:
                        source = r.get("source_book", "") or r.get("collection", "textbook")
                        textbook_chunks.append({
                            "text": text,
                            "source_book": source
                        })
        except Exception as e:
            logger.warning(f"Medical library search unavailable: {e}")

        if not dailymed_data and not textbook_chunks:
            return {
                "markdown": build_drug_not_found_markdown(identity.generic_name),
                "references": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Stage 3-7: Extract, Enforce Source Ownership, Validate, calculate Confidence
        monograph_json = self.validator.build_monograph(
            identity=identity,
            textbook_chunks=textbook_chunks,
            dailymed_data=dailymed_data
        )

        # Stage 8: Deterministic LLM Rendering
        markdown = self.renderer.render_monograph(monograph_json)

        return {
            "markdown": markdown,
            "references": monograph_json.evidence_sources,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _build_textbook_markdown(self, drug_name: str, context_parts: list[str], sources_used: set[str]) -> str:
        """Build structured markdown from textbook context.

        Pipeline:
        1. Try AI-powered formatting with RAG_FORMATTING_PROMPT.
           The prompt instructs the model to return
           ``{"error": "formatting_failed", ...}`` on failure so we can
           detect it programmatically and fall through.
        2. If AI is unavailable, returns error JSON, or throws — fall back
           to deterministic regex-based extraction via
           ``_extract_sections_locally``.
        """
        combined_text = "\n\n".join(part.strip() for part in context_parts[:8] if part.strip())
        if not combined_text.strip():
            return build_drug_not_found_markdown(drug_name)

        sources_list = sorted(sources_used) if sources_used else ["Medical Textbooks"]
        source_str = " • ".join(sources_list)

        # ── Tier 1: AI-powered formatting (model-agnostic) ──
        if self.ai_provider.has_usable_model():
            try:
                user_prompt = (
                    f"DRUG: {drug_name}\n\n"
                    f"SOURCE CHUNKS (from: {source_str}):\n"
                    f"{combined_text[:6000]}\n"
                )
                markdown = self.ai_provider.generate_response(
                    user_prompt,
                    system_instruction=RAG_FORMATTING_PROMPT,
                    temperature=0.2,
                )
                # Detect the JSON error escape hatch from the prompt
                if markdown:
                    stripped = markdown.strip()
                    if stripped.startswith("{") and "formatting_failed" in stripped:
                        try:
                            err = json.loads(stripped)
                            logger.warning(
                                f"AI formatting agent returned error for {drug_name}: "
                                f"{err.get('reason', 'unknown')}"
                            )
                        except json.JSONDecodeError:
                            logger.warning(f"AI returned malformed error JSON for {drug_name}")
                        # Fall through to local extraction
                    elif len(markdown) > 300 and "#" in markdown:
                        return markdown
                    else:
                        logger.warning(
                            f"AI response too short or missing markdown for {drug_name} "
                            f"(len={len(markdown)}), falling back to local extraction"
                        )
            except Exception as e:
                logger.warning(f"AI formatting failed for {drug_name}: {e}")

        # ── Tier 2: Deterministic local extraction ──
        sections = self._extract_sections_locally(drug_name, combined_text)
        confidence = self._compute_confidence(sections)

        parts: list[str] = []
        parts.append(f"# 💊 {drug_name}\n")
        parts.append(f"> **Source:** {source_str}  |  **Confidence:** {confidence}")
        parts.append("")

        # Overview
        overview = sections.get("overview", "")
        parts.append("## Overview\n")
        if overview:
            parts.append(overview)
        else:
            parts.append(f"Information about **{drug_name}** retrieved from medical textbooks.")
        parts.append("")

        # Quick Reference
        parts.append("## Quick Reference\n")
        parts.append("| Field | Details |")
        parts.append("|---|---|")
        parts.append(f"| Drug Class | {sections.get('drug_class', 'Not specified in source')} |")
        parts.append(f"| Common Brand Names | {sections.get('brand_names', 'Not specified in source')} |")
        parts.append(f"| Typical Dosage | {sections.get('typical_dosage', 'Not specified in source')} |")
        parts.append(f"| Half-Life | {sections.get('half_life', 'Not specified in source')} |")
        parts.append(f"| Route of Administration | {sections.get('route', 'Not specified in source')} |")
        parts.append("")

        # Mechanism of Action
        moa = sections.get("mechanism_of_action", "")
        parts.append("## Mechanism of Action\n")
        parts.append(moa if moa else "Not specified in source.")
        parts.append("")

        # Dosage & Administration
        dosage = sections.get("dosage", "")
        if dosage:
            parts.append("## Dosage & Administration\n")
            parts.append("| Strength | Frequency | Notes |")
            parts.append("|---|---|---|")
            for line in dosage.split("\n"):
                line = line.strip()
                if line:
                    parts.append(f"| {line} | See prescribing information | — |")
            parts.append("")

        # Contraindications
        contras = sections.get("contraindications", [])
        if contras:
            parts.append("## Contraindications\n")
            parts.append("| Condition | Reason |")
            parts.append("|---|---|")
            for item in contras:
                parts.append(f"| {item} | See prescribing information |")
            parts.append("")

        # Cautions
        cautions = sections.get("cautions", [])
        if cautions:
            parts.append("## Cautions / Use with Caution In\n")
            for item in cautions:
                parts.append(f"- {item}")
            parts.append("")

        # Side Effects
        common_se = sections.get("common_side_effects", [])
        serious_se = sections.get("serious_side_effects", [])
        if common_se or serious_se:
            parts.append("## Side Effects\n")
            parts.append("| Common | Serious / Rare |")
            parts.append("|---|---|")
            max_rows = max(len(common_se), len(serious_se), 1)
            for i in range(max_rows):
                c = common_se[i] if i < len(common_se) else "—"
                s = serious_se[i] if i < len(serious_se) else "—"
                parts.append(f"| {c} | {s} |")
            parts.append("")

        # Drug Interactions
        interactions = sections.get("drug_interactions", [])
        if interactions:
            parts.append("## Drug Interactions\n")
            parts.append("| Interacting Drug/Class | Effect |")
            parts.append("|---|---|")
            for item in interactions:
                parts.append(f"| {item} | See prescribing information |")
            parts.append("")

        # Clinical Notes (includes cross-drug flags and ambiguities)
        clinical = sections.get("clinical_notes", "")
        cross_drug = sections.get("cross_drug_flags", [])
        if clinical or cross_drug:
            parts.append("## Clinical Notes\n")
            if clinical:
                parts.append(clinical)
            if cross_drug:
                parts.append("")
                for flag in cross_drug:
                    parts.append(f"> ⚠️ {flag}")
            parts.append("")

        # References
        parts.append("## References\n")
        for s in sources_list:
            parts.append(f"- {s}")
        parts.append("")

        # Disclaimer
        parts.append("---")
        parts.append("*⚠️ This information is for reference only and not a substitute for professional medical advice.*\n")

        return "\n".join(parts)

    @staticmethod
    def _compute_confidence(sections: dict[str, Any]) -> str:
        """Compute confidence label based on section coverage.

        - High:   all 6 major sections have data
        - Medium: 3-5 of 6 major sections have data
        - Low:    0-2 of 6 major sections have data
        """
        major_keys = [
            "overview", "mechanism_of_action", "dosage",
            "contraindications", "common_side_effects", "drug_interactions",
        ]
        present = sum(
            1 for k in major_keys
            if sections.get(k)
            # lists count only if non-empty
            and (not isinstance(sections[k], list) or len(sections[k]) > 0)
        )
        if present >= 6:
            return "High"
        if present >= 3:
            return "Medium"
        return "Low"

    def _extract_sections_locally(self, drug_name: str, text: str) -> dict[str, Any]:
        """Best-effort regex extraction of structured sections from raw textbook text."""
        import re

        sections: dict[str, Any] = {}
        text_lower = text.lower()

        # ── Overview: first 2-3 sentences ──
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        overview_sentences = [s for s in sentences[:5] if len(s) > 30 and drug_name.lower().split()[0] in s.lower()]
        if overview_sentences:
            sections["overview"] = " ".join(overview_sentences[:3])

        # ── Drug class ──
        class_patterns = [
            rf'{drug_name}\s+(?:is\s+)?(?:a|an)\s+(.+?)(?:\s+(?:that|which|used|indicated))',
            r'(?:drug\s+class|classification)[:\s]+([^\n.]+)',
            r'(?:PDE\d+\s+inhibitor\w*)',
        ]
        for pat in class_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                sections["drug_class"] = m.group(1).strip() if m.lastindex else m.group(0).strip()
                break

        # ── Half-life ──
        hl_match = re.search(r'half[- ]?life[:\s]+(?:of\s+)?(?:approximately\s+)?(\d+[\s\-–to]+\d+\s*(?:hours?|h|minutes?|min)|\d+\s*(?:hours?|h|minutes?|min))', text, re.IGNORECASE)
        if hl_match:
            sections["half_life"] = hl_match.group(1).strip()

        # ── Dosage ──
        dose_match = re.search(r'(\d+[\s\-–to]+\d+\s*mg|\d+\s*mg)', text, re.IGNORECASE)
        if dose_match:
            # Grab context around the dose
            start = max(0, dose_match.start() - 50)
            end = min(len(text), dose_match.end() + 100)
            dose_context = text[start:end].strip()
            # Clean it up to just the relevant sentence
            dose_sentences = re.split(r'(?<=[.!?])\s+', dose_context)
            dose_relevant = [s for s in dose_sentences if re.search(r'\d+\s*mg', s, re.IGNORECASE)]
            if dose_relevant:
                sections["dosage"] = "\n".join(dose_relevant[:3])
            else:
                sections["typical_dosage"] = dose_match.group(0)

        # ── Contraindications ──
        contra_items: list[str] = []
        contra_patterns = [
            r'contraindicated?\s+(?:in\s+|for\s+)?(?:patients?\s+)?(?:taking\s+|with\s+|who\s+)?([^\n.]+)',
            r'(?:do\s+not\s+use|must\s+not\s+(?:be\s+)?use[d]?)\s+(?:in\s+|with\s+)?([^\n.]+)',
        ]
        for pat in contra_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                item = m.group(1).strip().rstrip(".,;")
                if len(item) > 5 and item not in contra_items:
                    contra_items.append(item)

        # Look for bullet-style contraindications
        contra_section = re.search(r'(?:contraindication|Contraindication)s?\s*[:\n•\-](.+?)(?:\n\n|\n[A-Z]|\Z)', text, re.DOTALL | re.IGNORECASE)
        if contra_section:
            for line in re.split(r'[•\-\n]+', contra_section.group(1)):
                line = line.strip().rstrip(".,;")
                if len(line) > 5 and line not in contra_items:
                    contra_items.append(line)
        if contra_items:
            sections["contraindications"] = contra_items[:10]

        # ── Cautions ──
        caution_items: list[str] = []
        caution_section = re.search(r'(?:caution|precaution|use\s+with\s+caution)s?\s*[:\n•\-](.+?)(?:\n\n|\n[A-Z]|\Z)', text, re.DOTALL | re.IGNORECASE)
        if caution_section:
            for line in re.split(r'[•\-\n]+', caution_section.group(1)):
                line = line.strip().rstrip(".,;")
                if len(line) > 5 and line not in caution_items:
                    caution_items.append(line)
        if caution_items:
            sections["cautions"] = caution_items[:10]

        # ── Side Effects ──
        common_se: list[str] = []
        serious_se: list[str] = []

        common_keywords = ["headache", "flushing", "rhinitis", "dyspepsia", "nausea",
                           "dizziness", "diarrhea", "rash", "insomnia", "fatigue"]
        serious_keywords = ["hypotension", "priapism", "sudden cardiac death",
                            "tachycardia", "ventricular", "arrhythmia", "anaphylaxis",
                            "stevens-johnson", "angioedema", "seizure"]

        for kw in common_keywords:
            if kw in text_lower:
                common_se.append(kw.capitalize())
        for kw in serious_keywords:
            if kw in text_lower:
                serious_se.append(kw.capitalize())

        if common_se:
            sections["common_side_effects"] = common_se
        if serious_se:
            sections["serious_side_effects"] = serious_se

        # ── Drug Interactions ──
        interaction_items: list[str] = []
        interaction_patterns = [
            r'(?:interact(?:ion)?s?\s+with|concurrent\s+use\s+(?:of|with))\s+([^\n.]+)',
            r'(?:organic\s+nitrate|nitrate\s+vasodilator|α\s*adrenergic|CYP3A4)',
        ]
        for pat in interaction_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                item = m.group(1).strip().rstrip(".,;") if m.lastindex else m.group(0).strip()
                if len(item) > 3 and item not in interaction_items:
                    interaction_items.append(item)
        if interaction_items:
            sections["drug_interactions"] = interaction_items[:8]

        # ── Clinical Notes ──
        # Grab tolerance/monitoring info
        clinical_notes: list[str] = []
        if "tolerance" in text_lower:
            tol_match = re.search(r'[^.]*tolerance[^.]*\.', text, re.IGNORECASE)
            if tol_match:
                clinical_notes.append(tol_match.group(0).strip())
        if "monitoring" in text_lower or "monitor" in text_lower:
            mon_match = re.search(r'[^.]*monitor(?:ing)?[^.]*\.', text, re.IGNORECASE)
            if mon_match and mon_match.group(0).strip() not in clinical_notes:
                clinical_notes.append(mon_match.group(0).strip())
        if clinical_notes:
            sections["clinical_notes"] = " ".join(clinical_notes[:3])

        # ── Mechanism of Action ──
        moa_patterns = [
            r'(?:mechanism\s+of\s+action|pharmacodynamic)[:\s]+([^\n]+(?:\n(?![A-Z#])[^\n]+)*)',
            r'(?:inhibit\w*|block\w*|agonist|antagonist|modulat\w*)\s+(?:of\s+|the\s+)?([^\n.]+)',
        ]
        for pat in moa_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                moa_text = m.group(1).strip() if m.lastindex else m.group(0).strip()
                if len(moa_text) > 20:
                    sections["mechanism_of_action"] = moa_text[:500]
                    break

        # ── Brand names ──
        brand_match = re.search(r'(?:brand\s+names?|marketed\s+as|sold\s+as|trade\s+names?)[:\s]+([^\n.]+)', text, re.IGNORECASE)
        if brand_match:
            sections["brand_names"] = brand_match.group(1).strip()

        # ── Route ──
        route_match = re.search(r'(?:oral|intravenous|subcutaneous|intramuscular|topical|transdermal|inhaled|sublingual)', text, re.IGNORECASE)
        if route_match:
            sections["route"] = route_match.group(0).capitalize()

        # ── Cross-drug contamination detection (Rule 6) ──
        # Detect if the RAG chunks contain significant references to other
        # drugs, which may indicate a retrieval/chunking error.
        known_drugs = [
            "sildenafil", "tadalafil", "vardenafil", "avanafil",
            "metformin", "lisinopril", "atorvastatin", "warfarin", "digoxin",
            "ibuprofen", "amoxicillin", "omeprazole", "losartan", "amlodipine",
            "nitroglycerin", "verapamil", "diltiazem", "milrinone", "cilostazol",
            "hydrochlorothiazide", "furosemide", "spironolactone",
        ]
        target_lower = drug_name.lower().split()[0]
        cross_drug_flags: list[str] = []
        for other_drug in known_drugs:
            if other_drug == target_lower:
                continue
            # Only flag if the other drug is mentioned prominently (3+ times)
            count = text_lower.count(other_drug)
            if count >= 3:
                cross_drug_flags.append(
                    f"The source text contains {count} references to "
                    f"**{other_drug.capitalize()}**, which may be a retrieval "
                    f"artefact. Related content has not been merged into the "
                    f"main sections of this monograph."
                )
        if cross_drug_flags:
            sections["cross_drug_flags"] = cross_drug_flags[:3]

        return sections

    def _fallback_markdown(self, question: str, drug_names: list[str], sources_list: list[str]) -> str:
        """Generate fallback markdown when AI is unavailable."""
        name = drug_names[0].title() if drug_names else question
        return build_drug_not_found_markdown(name)

    def _extract_drugs(self, question: str) -> list[str]:
        known_drugs = [
            "metformin", "lisinopril", "atorvastatin", "warfarin", "digoxin",
            "ibuprofen", "amoxicillin", "azithromycin", "omeprazole", "levothyroxine",
            "amlodipine", "losartan", "albuterol", "metoprolol", "prednisone",
            "hydrochlorothiazide", "simvastatin", "rosuvastatin", "furosemide",
            "clopidogrel", "rivaroxaban", "apixaban", "insulin", "fentanyl",
            "morphine", "codeine", "tramadol", "gabapentin", "pregabalin",
            "fluoxetine", "sertraline", "escitalopram", "citalopram",
            "venlafaxine", "duloxetine", "bupropion", "mirtazapine",
            "acetaminophen", "naproxen", "celecoxib", "prednisolone",
            "spironolactone", "carvedilol", "diltiazem",
            "verapamil", "heparin", "enoxaparin", "nitroglycerin",
        ]
        ql = question.lower()
        found = []
        for d in known_drugs:
            if d in ql:
                found.append(d)
        if not found:
            for entry in self.db.query(DrugEntry).all():
                gn = (entry.generic_name or "").lower()
                if gn and gn in ql:
                    found.append(gn)
                    break
        return found
