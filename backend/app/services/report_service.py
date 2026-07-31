import os
import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import UploadFile, BackgroundTasks

logger = logging.getLogger(__name__)
from datetime import datetime

from app.models.report import MedicalReport
from app.models.report_chunk import ReportChunk, LabValue
from app.models.biomarker import BiomarkerTracking, TimelineEvent, AIInsight
from app.ocr import ocr_manager
from app.core.config import settings
from app.core.queue import get_queue, get_connection
from app.services.classification_service import classification_service
from app.infrastructure.ai_provider_service import ai_provider
from app.infrastructure.embedding_service import embedding_service
from app.infrastructure.vector_store import vector_store
from app.services.health_score_engine import HealthScoreEngine
from app.services.risk_predictor import risk_predictor


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    async def upload(self, user_id: int, file: UploadFile) -> MedicalReport:
        file_bytes = await file.read()
        file_ext = os.path.splitext(file.filename)[1]
        file_id = str(uuid.uuid4())
        file_name = f"{file_id}{file_ext}"

        upload_dir = settings.UPLOAD_DIR
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, file_name)

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        report = MedicalReport(
            user_id=user_id,
            title=os.path.splitext(file.filename)[0],
            file_type=file.content_type or "application/octet-stream",
            file_path=file_path,
            original_filename=file.filename,
            status="processing",
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        ocr_result = ocr_manager.extract_structured(file_bytes, file.content_type or "")
        extracted = ocr_result.get("raw_text", "")
        if not extracted:
            report.status = "error"
            report.error_message = "OCR returned no text"
            self.db.commit()
            return report

        report.extracted_text = extracted

        classification_result = classification_service.classify(extracted, file.filename)
        report.document_type = classification_result.get("document_type", "General Medical Report")
        report.report_type = report.document_type

        structured = classification_service.extract_structured(extracted, report.document_type)
        report.structured_data = structured

        health_score = structured.get("health_score")
        if health_score is not None:
            report.health_score = min(100, max(0, int(health_score)))

        risk_scores = structured.get("risk_scores", {})
        if risk_scores:
            report.risk_scores = risk_scores

        meds = structured.get("medications", [])
        med_names = [m.get("name") for m in meds if m.get("name")]
        
        interaction_context = ""
        analysis_source = "AI"
        if len(med_names) > 1:
            from app.services.drug_service import DrugService
            ds = DrugService(self.db)
            db_interactions = ds.get_interactions(med_names)
            if db_interactions:
                interaction_context = "Drug Interactions found in Database:\n" + str(db_interactions)
                analysis_source = "Database"
            else:
                try:
                    from app.domain.medical_library.retriever import search as lib_search
                    query = f"drug interactions between {' and '.join(med_names)}"
                    rag_results = lib_search(query, top_k=3, use_hybrid=False)
                    if rag_results:
                        interaction_context = "Drug Interactions found in Medical Library (RAG):\n" + "\n".join([r.get("text", "") for r in rag_results])
                        analysis_source = "Medical Library (RAG)"
                except Exception as e:
                    logger.warning(f"RAG search failed for interactions: {e}")
        elif len(med_names) == 1:
            from app.services.hybrid_drug_service import HybridDrugService
            hds = HybridDrugService(self.db)
            drug_info = hds.hybrid_retrieve(med_names[0])
            drug_interactions = drug_info.drug.get("drug_interactions")
            if drug_interactions:
                interaction_context = f"Drug Interactions for {med_names[0]}:\n{drug_interactions}"
                source = drug_info.metadata.source_type.value
                analysis_source = "Database" if source == "verified" else "Medical Library (RAG)" if source == "hybrid" else "AI"

        analysis_prompt = (
            f"Document type: {report.document_type}\n"
            f"Extracted Document Text:\n---\n{extracted[:8000]}\n---\n\n"
            "Act as Sanjeevni AI, an advanced and experienced clinical medical copilot. "
            "You do not just extract text; you understand the document, verify information, explain it, and identify risks. "
            "Generate a comprehensive, clinician-style report with the following EXACT structure and emojis. Ensure it contains both a Medical View and a Patient-Friendly Explanation.\n\n"
            "# 📋 Medical Document Analysis\n\n"
            "## 1. 🧑‍⚕️ Patient Summary\n"
            "Provide a Markdown table with Fields: Document Type, Hospital, Visit Date, Patient, Age, Sex, Weight. (Fill in 'Not documented' if missing).\n\n"
            "## 2. 🩺 Diagnosis & Clinical Impression\n"
            "Include subheadings: **Chief Complaint**, **Provisional Diagnosis**, **Final Diagnosis**, and **Severity Assessment** (with a confidence level).\n\n"
            "## 3. 💊 Medication Explanation & Validation\n"
            "For each medication, create a numbered subheading (e.g., '### 1. Drug Name').\n"
            "Include bullet points for: **Purpose**, **Why prescribed**, **Dose**, **Frequency**, **Duration**, **Prescription Validation** (is dose/duration appropriate?), and **Common Side Effects**.\n\n"
            "## 4. 🚨 Drug Interaction Analysis\n"
            "Provide a Markdown table with 'Drugs' and 'Result', followed by 'Overall interaction risk: (e.g. 🟢 Low, 🟡 Moderate, 🔴 High)'.\n"
            f"IMPORTANT: Use the following reference context for interactions if available. If none, use your AI knowledge. You MUST explicitly state at the end of this section: 'Analysis performed using {analysis_source} reference.'\n"
            f"Reference Context: {interaction_context}\n\n"
            "## 5. ⚠️ Missing Clinical Information & Potential Red Flags\n"
            "List clinically important missing details (e.g., allergies, bite category) and potential red flags.\n\n"
            "## 6. 📈 Risk Assessment\n"
            "Provide a table of Conditions and Risk levels (e.g., 🔴 High, 🟠 Moderate, 🟡 Mild, 🟢 Low).\n\n"
            "## 7. 📚 Clinical Reasoning\n"
            "Explain the rationale behind the treatment plan like an expert clinician.\n\n"
            "## 8. 🔬 Evidence-Based Recommendations\n"
            "Provide evidence-based guidance (citing sources like DailyMed, OpenFDA, or clinical guidelines).\n\n"
            "## 9. 📅 Follow-up Timeline\n"
            "Provide a Markdown table with columns 'Visit' (e.g. Day 3, Day 7) and 'Purpose', acting as a checklist.\n\n"
            "## 10. 🗣️ Patient-Friendly Explanation\n"
            "A summary written in simple, non-medical language for the patient to easily understand their condition and what they need to do (e.g., wash wound, take meds, follow up).\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "- Return ONLY valid Markdown. Use bold drug names and bullet lists where appropriate."
        )
        report.ai_summary = ai_provider.generate_response(
            prompt=analysis_prompt,
            system_instruction="You are an expert medical AI assistant providing a detailed clinical analysis in Markdown.",
        )

        report.processed = True
        self.db.commit()
        self.db.refresh(report)

        from app.services.report_intelligence_service import ReportIntelligenceService
        try:
            intelligence = ReportIntelligenceService(self.db)
            intelligence.process_report(report.id, user_id)
        except Exception:
            pass

        self._store_biomarkers(report.id, user_id, structured)
        self._store_timeline_events(report.id, user_id, structured, report.document_type)
        self._store_insights(report.id, user_id, structured)
        self._store_in_vector_store(report.id, user_id, extracted, structured)

        return report

    async def upload_async(self, user_id: int, file: UploadFile, background_tasks: BackgroundTasks) -> MedicalReport:
        file_bytes = await file.read()
        file_ext = os.path.splitext(file.filename)[1]
        file_id = str(uuid.uuid4())
        file_name = f"{file_id}{file_ext}"

        upload_dir = settings.UPLOAD_DIR
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, file_name)

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        report = MedicalReport(
            user_id=user_id,
            title=os.path.splitext(file.filename)[0],
            file_type=file.content_type or "application/octet-stream",
            file_path=file_path,
            original_filename=file.filename,
            status="processing",
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        from app.workers.report_worker import process_report
        try:
            q = get_queue()
            q.enqueue(process_report, report.id)
        except Exception as e:
            logger.warning(f"Failed to enqueue report {report.id} to Redis (async). Falling back to FastAPI BackgroundTasks. Error: {e}")
            background_tasks.add_task(process_report, report.id)

        return report

    def get_status(self, report_id: int, user_id: int) -> Optional[MedicalReport]:
        return (
            self.db.query(MedicalReport)
            .filter(MedicalReport.id == report_id, MedicalReport.user_id == user_id)
            .first()
        )

    def _store_biomarkers(self, report_id: int, user_id: int, structured: dict):
        biomarkers = structured.get("biomarkers", [])
        lab_values = structured.get("lab_values", [])
        for item in biomarkers + lab_values:
            name = item.get("name") or item.get("test_name")
            if not name:
                continue
            raw_value = item.get("value")
            numeric_value = None
            if raw_value is not None:
                try:
                    numeric_value = float(raw_value)
                except (ValueError, TypeError):
                    numeric_value = None
            tracking = BiomarkerTracking(
                user_id=user_id,
                report_id=report_id,
                biomarker_name=name,
                value=numeric_value,
                value_text=str(raw_value or ""),
                unit=item.get("unit", ""),
                reference_range=item.get("reference_range", item.get("range", "")),
                is_abnormal=item.get("flag") not in (None, "", "normal", "NORMAL"),
                flag=item.get("flag"),
            )
            self.db.add(tracking)
        self.db.commit()

    def _store_timeline_events(self, report_id: int, user_id: int, structured: dict, doc_type: str):
        timeline_events = structured.get("timeline_events", [])
        for event in timeline_events:
            try:
                evt_date = datetime.fromisoformat(event["date"]) if event.get("date") else datetime.utcnow()
            except (ValueError, KeyError):
                evt_date = datetime.utcnow()
            te = TimelineEvent(
                user_id=user_id,
                report_id=report_id,
                event_type=event.get("type", doc_type.lower().replace(" ", "_")),
                title=event.get("event", f"{doc_type} Uploaded"),
                description=event.get("description", ""),
                severity=event.get("severity", "info"),
                event_date=evt_date,
            )
            self.db.add(te)

        diagnoses = structured.get("diagnosis", [])
        for d in diagnoses:
            if isinstance(d, str):
                te = TimelineEvent(
                    user_id=user_id,
                    report_id=report_id,
                    event_type="diagnosis",
                    title=d,
                    description=f"Diagnosed from {doc_type}",
                    severity="info",
                    event_date=datetime.utcnow(),
                )
                self.db.add(te)

        abnormal = structured.get("abnormal_values", [])
        for a in abnormal:
            te = TimelineEvent(
                user_id=user_id,
                report_id=report_id,
                event_type="abnormal_value",
                title=f"{a.get('test', 'Value')} is abnormal",
                description=f"{a.get('test')}: {a.get('value')} {a.get('unit')} — {a.get('severity', 'abnormal')}",
                severity=a.get("severity", "warning"),
                event_date=datetime.utcnow(),
            )
            self.db.add(te)

        if not timeline_events and not diagnoses and not abnormal:
            te = TimelineEvent(
                user_id=user_id,
                report_id=report_id,
                event_type="upload",
                title=f"{doc_type} Uploaded",
                description=f"Medical {doc_type.lower()} processed and analyzed",
                severity="info",
                event_date=datetime.utcnow(),
            )
            self.db.add(te)

        self.db.commit()

    def _store_insights(self, report_id: int, user_id: int, structured: dict):
        risk_scores = structured.get("risk_scores", {})
        for condition, score in risk_scores.items():
            if score is None:
                continue
            level = "good" if score < 30 else "attention" if score < 60 else "critical"
            label = condition.replace("_", " ").title()
            insight = AIInsight(
                user_id=user_id,
                report_id=report_id,
                insight_type="risk",
                title=f"{label} Risk: {int(score)}%",
                description=f"Your {label.lower()} risk score is {int(score)}%. {'Low risk.' if level == 'good' else 'Moderate risk — monitor closely.' if level == 'attention' else 'High risk — consult your doctor.'}",
                trend="stable",
                severity=level,
            )
            self.db.add(insight)

        abnormal = structured.get("abnormal_values", [])
        for a in abnormal:
            insight = AIInsight(
                user_id=user_id,
                report_id=report_id,
                insight_type="abnormal",
                title=f"{a.get('test')} is {a.get('severity', 'abnormal')}",
                description=f"{a.get('test')}: {a.get('value')} {a.get('unit')} — outside normal range.",
                trend="worsened",
                severity=a.get("severity", "warning"),
            )
            self.db.add(insight)

        follow_up = structured.get("follow_up_tests", [])
        for test in follow_up:
            insight = AIInsight(
                user_id=user_id,
                report_id=report_id,
                insight_type="follow_up",
                title=f"Follow-up: {test}",
                description=f"Recommended follow-up test based on report findings.",
                trend="stable",
                severity="info",
            )
            self.db.add(insight)

        self.db.commit()

    def _store_in_vector_store(self, report_id: int, user_id: int, text: str, structured: dict):
        try:
            summary_text = f"Report {report_id}: {structured.get('diagnosis', [])} | {structured.get('findings', [])} | Meds: {structured.get('medications', [])}"
            emb = embedding_service.embed(summary_text)
            vector_store.upsert(
                embedding_id=f"report_summary_{report_id}",
                embedding=emb,
                payload={
                    "type": "report_summary",
                    "report_id": report_id,
                    "user_id": user_id,
                    "document_type": structured.get("document_type", ""),
                    "diagnosis": structured.get("diagnosis", []),
                    "findings": structured.get("findings", []),
                },
            )
        except Exception:
            pass

    def get_user_reports(self, user_id: int) -> list[MedicalReport]:
        return (
            self.db.query(MedicalReport)
            .filter(MedicalReport.user_id == user_id)
            .order_by(MedicalReport.uploaded_at.desc())
            .all()
        )

    def get_report(self, report_id: int, user_id: int) -> Optional[MedicalReport]:
        return (
            self.db.query(MedicalReport)
            .filter(
                MedicalReport.id == report_id, MedicalReport.user_id == user_id
            )
            .first()
        )

    def delete_report(self, report_id: int, user_id: int) -> bool:
        report = self.get_report(report_id, user_id)
        if not report:
            return False
        if os.path.exists(report.file_path):
            os.remove(report.file_path)
        self.db.query(ReportChunk).filter(ReportChunk.report_id == report_id).delete()
        self.db.query(LabValue).filter(LabValue.report_id == report_id).delete()
        self.db.query(BiomarkerTracking).filter(BiomarkerTracking.report_id == report_id).delete()
        self.db.query(TimelineEvent).filter(TimelineEvent.report_id == report_id).delete()
        self.db.query(AIInsight).filter(AIInsight.report_id == report_id).delete()
        self.db.delete(report)
        self.db.commit()
        return True
