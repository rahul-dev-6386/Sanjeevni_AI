import re
import logging
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.profile import PatientProfile
from app.models.metrics import DailyMetric
from app.models.medication import Medication
from app.models.report import MedicalReport
from app.services.medical_knowledge_service import MedicalKnowledgeService
from app.infrastructure.pubmed_service import PubMedService
from app.services.drug_service import DrugService
from app.services.report_intelligence_service import ReportIntelligenceService
from app.services.citation_engine import CitationEngine
from app.services.context_fusion_service import ContextFusionService
from app.infrastructure.ai_provider_service import ai_provider
from app.infrastructure.vector_store import vector_store
from app.infrastructure.embedding_service import embedding_service
from app.models.report_chunk import ReportChunk
from app.domain.medical_library import retriever as library_retriever


class IntentType(str, Enum):
    GENERAL_MEDICAL = "general_medical"
    PATIENT_HISTORY = "patient_history"
    REPORT_ANALYSIS = "report_analysis"
    METRICS_ANALYSIS = "metrics_analysis"
    DRUG_QUERY = "drug_query"
    EMERGENCY = "emergency"
    MULTI_SOURCE = "multi_source"


EMERGENCY_KEYWORDS = [
    "chest pain", "heart attack", "stroke", "severe bleeding",
    "suicidal", "want to die", "self-harm", "difficulty breathing",
    "anaphylaxis", "unconscious", "not breathing", "choking",
    "severe burn", "poisoning", "overdose", "can't breathe",
]

REPORT_KEYWORDS = [
    "lab", "blood test", "report", "result", "biomarker",
    "cholesterol", "hemoglobin", "a1c", "glucose", "creatinine",
]

DRUG_KEYWORDS = [
    "drug", "medication", "medicine", "dosage", "side effect",
    "interaction", "prescription", "tablet", "pill", "dose",
]

METRICS_KEYWORDS = [
    "sleep", "water", "exercise", "weight", "step", "mood",
    "trend", "pattern", "score", "activity",
]

HISTORY_KEYWORDS = [
    "my history", "my condition", "my profile", "my disease",
    "my allergy", "my health", "tell me about me",
]


class QueryRouter:
    def __init__(self, db: Session):
        self.db = db
        self.knowledge_service = MedicalKnowledgeService(db)
        self.pubmed_service = PubMedService(db)
        self.drug_service = DrugService(db)
        self.report_intelligence = ReportIntelligenceService(db)

    def classify_intent(self, query: str) -> IntentType:
        query_lower = query.lower().strip()

        for kw in EMERGENCY_KEYWORDS:
            if kw in query_lower:
                return IntentType.EMERGENCY

        has_report = any(kw in query_lower for kw in REPORT_KEYWORDS)
        has_drug = any(kw in query_lower for kw in DRUG_KEYWORDS)
        has_metrics = any(kw in query_lower for kw in METRICS_KEYWORDS)
        has_history = any(kw in query_lower for kw in HISTORY_KEYWORDS)

        if has_history:
            return IntentType.PATIENT_HISTORY
        if has_report:
            return IntentType.REPORT_ANALYSIS
        if has_drug:
            return IntentType.DRUG_QUERY
        if has_metrics:
            return IntentType.METRICS_ANALYSIS

        multi_count = sum([has_report, has_drug, has_metrics, has_history])
        if multi_count >= 2:
            return IntentType.MULTI_SOURCE

        return IntentType.GENERAL_MEDICAL

    def route(self, query: str, user_id: int, use_reranker: bool = False) -> dict:
        intent = self.classify_intent(query)
        citations = CitationEngine()

        if intent == IntentType.EMERGENCY:
            return {
                "intent": "emergency",
                "response": (
                    "⚠️ **EMERGENCY DETECTED**\n\n"
                    "Your message suggests you may be experiencing a medical emergency. "
                    "Please call your local emergency services immediately.\n\n"
                    "- **Do not wait** for an online response\n"
                    "- Call 911 (US) or your local emergency number\n"
                    "- If you're with someone, ask them to stay with you\n\n"
                    "I'm an AI assistant and cannot provide emergency medical help. "
                    "Please seek immediate professional medical attention."
                ),
                "citations": [],
            }

        if intent == IntentType.PATIENT_HISTORY:
            return self._handle_patient_history(user_id, citations)

        if intent == IntentType.REPORT_ANALYSIS:
            return self._handle_report_analysis(query, user_id, citations)

        if intent == IntentType.DRUG_QUERY:
            return self._handle_drug_query(query, citations)

        if intent == IntentType.METRICS_ANALYSIS:
            return self._handle_metrics_analysis(query, user_id, citations)

        if intent == IntentType.MULTI_SOURCE:
            return self._handle_multi_source(query, user_id, citations)

        return self._handle_general_medical(query, user_id, citations, use_reranker)

    def _handle_patient_history(self, user_id: int, citations: CitationEngine) -> dict:
        profile = (
            self.db.query(PatientProfile)
            .filter(PatientProfile.user_id == user_id)
            .first()
        )
        reports = (
            self.db.query(MedicalReport)
            .filter(MedicalReport.user_id == user_id)
            .order_by(MedicalReport.uploaded_at.desc())
            .limit(5)
            .all()
        )
        medications = (
            self.db.query(Medication)
            .filter(Medication.user_id == user_id, Medication.active == True)
            .all()
        )

        parts = ["## Patient Health Summary\n"]
        if profile:
            if profile.date_of_birth:
                parts.append(f"- **Age:** {(date.today().year - profile.date_of_birth.year)}")
            if profile.gender:
                parts.append(f"- **Gender:** {profile.gender.value if hasattr(profile.gender, 'value') else profile.gender}")
            if profile.chronic_diseases:
                parts.append(f"- **Chronic Conditions:** {', '.join(profile.chronic_diseases)}")
            if profile.allergies:
                parts.append(f"- **Allergies:** {', '.join(profile.allergies)}")
            if profile.blood_type:
                parts.append(f"- **Blood Type:** {profile.blood_type}")

        if medications:
            med_list = [f"{m.name} ({m.dosage}, {m.frequency})" for m in medications]
            parts.append(f"\n- **Current Medications:** {'; '.join(med_list)}")
            for m in medications:
                citations.add_drug(m.name)

        if reports:
            parts.append(f"\n- **Recent Reports:** {len(reports)} reports available")
            for r in reports[:3]:
                parts.append(f"  - {r.title or r.original_filename} ({r.uploaded_at.strftime('%Y-%m-%d') if r.uploaded_at else 'N/A'})")
                citations.add_report_finding(r.title or "Medical Report")

        from datetime import date
        response = "\n".join(parts)
        return {
            "intent": "patient_history",
            "response": response + citations.format_all(),
            "citations": citations.to_dict_list(),
        }

    def _handle_report_analysis(self, query: str, user_id: int, citations: CitationEngine) -> dict:
        latest_report = (
            self.db.query(MedicalReport)
            .filter(MedicalReport.user_id == user_id, MedicalReport.processed == True)
            .order_by(MedicalReport.uploaded_at.desc())
            .first()
        )
        if not latest_report:
            return {
                "intent": "report_analysis",
                "response": "No processed reports found. Upload a medical report first.",
                "citations": [],
            }

        labs = self.report_intelligence.get_lab_values(latest_report.id, user_id)
        for lab in labs:
            citations.add_report_finding(lab["test_name"], lab.get("flag"))

        knowledge_results = self.knowledge_service.search(query, top_k=3)
        for kr in knowledge_results:
            citations.add_guideline(kr.get("specialty", "medical"), kr["title"], kr.get("url"))

        response_parts = [f"## Report Analysis: {latest_report.title or latest_report.original_filename}\n"]
        response_parts.append(f"**{len(labs)}** lab values extracted.")

        # Fetch report chunks for richer context
        try:
            query_emb = embedding_service.embed(query)
            report_chunk_results = vector_store.search(
                query_emb,
                top_k=3,
                payload_filter={
                    "type": "report",
                    "report_id": latest_report.id,
                    "user_id": user_id,
                },
            )
            if report_chunk_results:
                response_parts.append(f"\n**Relevant Report Excerpts:**")
                for rc in report_chunk_results:
                    chunk = (
                        self.db.query(ReportChunk)
                        .filter(
                            ReportChunk.report_id == latest_report.id,
                            ReportChunk.chunk_index == rc["payload"]["chunk_index"],
                        )
                        .first()
                    )
                    if chunk and chunk.content.strip():
                        response_parts.append(f"> {chunk.content[:300]}...")
        except Exception as e:
            logger.warning(f"Could not search report chunks: {e}")

        abnormal = [l for l in labs if l.get("is_abnormal")]
        if abnormal:
            response_parts.append(f"\n**Abnormal Values ({len(abnormal)}):**")
            for lab in abnormal:
                response_parts.append(f"- {lab['test_name']}: {lab['value_text']} {lab['unit']} ({lab['flag']}, ref: {lab['reference_range']})")

        normal = [l for l in labs if not l.get("is_abnormal")]
        if normal:
            response_parts.append(f"\n**Normal Values ({len(normal)}):**")
            for lab in normal[:5]:
                response_parts.append(f"- {lab['test_name']}: {lab['value_text']} {lab['unit']}")

        response = "\n".join(response_parts)
        return {
            "intent": "report_analysis",
            "response": response + citations.format_all(),
            "citations": citations.to_dict_list(),
        }

    def _handle_drug_query(self, query: str, citations: CitationEngine) -> dict:
        drug_results = self.drug_service.search_drug(query)
        if drug_results:
            drug = drug_results[0]
            citations.add_drug(drug["generic_name"], drug.get("brand_name"))

            parts = [f"## Drug Information: {drug['generic_name']}\n"]
            if drug.get("brand_name"):
                parts.append(f"**Brand Name:** {drug['brand_name']}")
            if drug.get("drug_class"):
                parts.append(f"**Class:** {drug['drug_class']}")
            if drug.get("indications"):
                parts.append(f"\n**Indications:** {drug['indications']}")
            if drug.get("contraindications"):
                parts.append(f"\n**Contraindications:** {drug['contraindications']}")
            if drug.get("side_effects"):
                parts.append(f"\n**Side Effects:** {drug['side_effects']}")
            if drug.get("dosage_info"):
                parts.append(f"\n**Dosage:** {drug['dosage_info']}")
            if drug.get("interactions"):
                parts.append(f"\n**Interactions:** {drug['interactions']}")

            return {
                "intent": "drug_query",
                "response": "\n".join(parts) + citations.format_all(),
                "citations": citations.to_dict_list(),
            }

        pubmed_results = self.pubmed_service.search_local(query, top_k=3)
        for pr in pubmed_results:
            citations.add_pubmed(pr["title"], pr["pmid"], pr.get("journal"))

        if pubmed_results:
            parts = [f"## Drug Information\nNo exact drug match found. Here are relevant research articles:\n"]
            for pr in pubmed_results[:3]:
                parts.append(f"- **{pr['title']}** ({pr.get('journal', 'N/A')})")
            return {
                "intent": "drug_query",
                "response": "\n".join(parts) + citations.format_all(),
                "citations": citations.to_dict_list(),
            }

        return {
            "intent": "drug_query",
            "response": "No drug information found. Please consult a pharmacist or physician.",
            "citations": [],
        }

    def _handle_metrics_analysis(self, query: str, user_id: int, citations: CitationEngine) -> dict:
        from datetime import date, timedelta
        start = date.today() - timedelta(days=30)
        metrics = (
            self.db.query(DailyMetric)
            .filter(DailyMetric.user_id == user_id, DailyMetric.date >= start)
            .order_by(DailyMetric.date)
            .all()
        )

        if not metrics:
            return {
                "intent": "metrics_analysis",
                "response": "No metrics data available for the last 30 days. Start tracking your daily health metrics.",
                "citations": [],
            }

        sleep = [m.sleep_hours for m in metrics if m.sleep_hours]
        water = [m.water_ml for m in metrics if m.water_ml]
        exercise = [m.exercise_min for m in metrics if m.exercise_min]

        parts = [f"## Metrics Summary (Last {len(metrics)} days)\n"]
        if sleep:
            avg_sleep = sum(sleep) / len(sleep)
            parts.append(f"- **Sleep:** Avg {avg_sleep:.1f}h/day (target: 7-9h)")
        if water:
            avg_water = sum(water) / len(water)
            parts.append(f"- **Water:** Avg {avg_water:.0f}ml/day (target: 2000ml)")
        if exercise:
            avg_exercise = sum(exercise) / len(exercise)
            parts.append(f"- **Exercise:** Avg {avg_exercise:.0f}min/day (target: 30min)")

        kwargs = {"specialty": "nutrition", "title": "Physical Activity Guidelines", "url": "https://www.who.int/publications/i/item/9789240015128"}
        citations.add_guideline(**kwargs)

        return {
            "intent": "metrics_analysis",
            "response": "\n".join(parts) + citations.format_all(),
            "citations": citations.to_dict_list(),
        }

    def _handle_general_medical(self, query: str, user_id: int, citations: CitationEngine, use_reranker: bool = False) -> dict:
        knowledge_results = self.knowledge_service.search(query, top_k=5)
        for kr in knowledge_results:
            citations.add_guideline(kr.get("specialty", "medical"), kr["title"], kr.get("url"))

        pubmed_results = self.pubmed_service.search_local(query, top_k=3)
        for pr in pubmed_results:
            citations.add_pubmed(pr["title"], pr["pmid"], pr.get("journal"))

        # Use ContextFusionService for unified textbook + user report retrieval
        fusion = ContextFusionService(self.db)
        fusion_result = fusion.retrieve(
            query=query,
            user_id=user_id,
            top_k_textbooks=8,
            top_k_user=5,
        )

        context_parts = []
        used_books = set()

        if knowledge_results:
            for kr in knowledge_results[:3]:
                text = kr.get("content", "").strip()
                if text:
                    context_parts.append(text[:1000])

        if pubmed_results:
            for pr in pubmed_results[:2]:
                text = pr.get("content", "").strip()
                if text:
                    context_parts.append(text[:1000])

        for ctx in fusion_result.contexts:
            if ctx["source"] == "user_report_chunks":
                text = ctx.get("content", "").strip()
                if text:
                    context_parts.append(f"[User's Medical Data] {text[:1000]}")
                    citations.add_report_finding(f"Report #{ctx.get('report_id', '?')}", None)
            elif ctx["source"] in ("textbook", "textbook_library"):
                text = ctx.get("content", "").strip()
                book = ctx.get("title", "")
                if book:
                    used_books.add(book)
                if text:
                    context_parts.append(text[:1000])

        if not context_parts:
            return {
                "intent": "general_medical",
                "response": "I don't have enough medical knowledge on this topic yet. Consult your healthcare provider.",
                "citations": [],
            }

        # Deduplicate context
        seen = set()
        deduped = []
        for text in context_parts:
            fp = text.lower().strip()[:150]
            if fp not in seen:
                seen.add(fp)
                deduped.append(text)
        context = "\n\n".join(deduped)

        return {
            "intent": "general_medical",
            "response": context,
            "citations": citations.to_dict_list(),
        }

    def _handle_multi_source(self, query: str, user_id: int, citations: CitationEngine) -> dict:
        report_result = self._handle_report_analysis(query, user_id, citations)
        drug_result = self._handle_drug_query(query, citations)
        metrics_result = self._handle_metrics_analysis(query, user_id, citations)
        patient_result = self._handle_patient_history(user_id, citations)

        parts = ["## Multi-Source Analysis\n"]
        for result in [patient_result, report_result, metrics_result]:
            if result["citations"] or "No" not in result["response"][:3]:
                parts.append(result["response"])
                parts.append("")

        if not parts:
            return self._handle_general_medical(query, user_id, citations)

        return {
            "intent": "multi_source",
            "response": "\n".join(parts),
            "citations": citations.to_dict_list(),
        }
