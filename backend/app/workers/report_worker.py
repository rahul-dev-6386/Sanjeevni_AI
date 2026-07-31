import logging
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.infrastructure.ai_provider_service import ai_provider
from app.infrastructure.embedding_provider import get_embedding_provider
from app.models.biomarker import BiomarkerTracking, TimelineEvent, AIInsight
from app.models.report import MedicalReport
from app.models.user_report_chunk import UserReportChunk
from app.ocr import ocr_manager
from app.services.classification_service import classification_service

logger = logging.getLogger("report_worker")

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def _chunk_semantically(text: str, max_words: int = 300, overlap: int = 50) -> list[str]:
    if not text:
        return []
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(words):
            break
        start = end - overlap
    return chunks if chunks else [text]


def _store_biomarkers(db, report_id, user_id, structured):
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
        db.add(tracking)
    db.commit()


def _store_timeline_events(db, report_id, user_id, structured, doc_type):
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
        db.add(te)

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
            db.add(te)

    if not timeline_events and not diagnoses:
        te = TimelineEvent(
            user_id=user_id,
            report_id=report_id,
            event_type="upload",
            title=f"{doc_type} Uploaded",
            description=f"Medical {doc_type.lower()} processed and analyzed",
            severity="info",
            event_date=datetime.utcnow(),
        )
        db.add(te)

    db.commit()


def _store_insights(db, report_id, user_id, structured):
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
        db.add(insight)
    db.commit()


def process_report(report_id: int) -> None:
    logger.info(f"Processing report {report_id}")
    db: Session = SessionLocal()
    try:
        report = db.query(MedicalReport).filter(MedicalReport.id == report_id).first()
        if not report:
            logger.error(f"Report {report_id} not found")
            return

        if report.status == "ready":
            logger.info(f"Report {report_id} already processed")
            return

        report.status = "processing"
        db.commit()

        file_bytes = open(report.file_path, "rb").read()
        file_type = report.file_type or "application/octet-stream"

        ocr_result = ocr_manager.extract_structured(file_bytes, file_type)
        extracted = ocr_result.get("raw_text", "")
        if not extracted:
            report.status = "error"
            report.error_message = "OCR returned no text"
            db.commit()
            return

        report.extracted_text = extracted

        classification_result = classification_service.classify(extracted, report.original_filename or "")
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

        analysis_prompt = (
            f"Document type: {report.document_type}\n"
            f"Extracted Document Text:\n---\n{extracted[:8000]}\n---\n\n"
            "Act as Sanjeevni AI, an advanced and experienced clinical medical copilot. "
            "You do not just extract text; you understand the document, verify information, explain it, and identify risks. "
            "Generate a comprehensive, clinician-style report with the following EXACT structure and emojis. Ensure it contains both a Medical View and a Patient-Friendly Explanation.\n\n"
            "# 📋 Medical Document Analysis\n\n"
            "## 1. 🧑\u200d⚕️ Patient Summary\n"
            "Provide a Markdown table with Fields: Document Type, Hospital, Visit Date, Patient, Age, Sex, Weight. (Fill in 'Not documented' if missing).\n\n"
            "## 2. 🩺 Diagnosis & Clinical Impression\n"
            "Include subheadings: **Chief Complaint**, **Provisional Diagnosis**, **Final Diagnosis**, and **Severity Assessment** (with a confidence level).\n\n"
            "## 3. 💊 Medication Explanation & Validation\n"
            "For each medication, create a numbered subheading (e.g., '### 1. Drug Name').\n"
            "Include bullet points for: **Purpose**, **Why prescribed**, **Dose**, **Frequency**, **Duration**, **Prescription Validation** (is dose/duration appropriate?), and **Common Side Effects**.\n\n"
            "## 4. 🚨 Drug Interaction Analysis\n"
            "Provide a Markdown table with 'Drugs' and 'Result', followed by 'Overall interaction risk: (e.g. 🟢 Low, 🟡 Moderate, 🔴 High)'.\n\n"
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

        # Store biomarkers, timeline, and insights
        try:
            _store_biomarkers(db, report.id, report.user_id, structured)
            _store_timeline_events(db, report.id, report.user_id, structured, report.document_type)
            _store_insights(db, report.id, report.user_id, structured)
        except Exception as e:
            logger.warning(f"Failed to store intelligence data for report {report_id}: {e}")

        # Process report intelligence (lab values, embeddings)
        try:
            from app.services.report_intelligence_service import ReportIntelligenceService
            intelligence = ReportIntelligenceService(db)
            intelligence.process_report(report.id, report.user_id)
        except Exception as e:
            logger.warning(f"Failed to process intelligence for report {report_id}: {e}")

        report.processed = True
        db.commit()

        db.refresh(report)

        provider = get_embedding_provider()
        chunks = _chunk_semantically(extracted)
        chunk_models = []
        for i, chunk_text in enumerate(chunks):
            embedding = provider.embed(chunk_text)
            chunk_model = UserReportChunk(
                user_id=report.user_id,
                report_id=report.id,
                chunk_index=i,
                content=chunk_text,
                embedding=embedding,
                report_type=report.document_type,
                language="en",
            )
            chunk_models.append(chunk_model)

        db.add_all(chunk_models)
        db.commit()

        report.status = "ready"
        report.processing_completed_at = datetime.utcnow()
        db.commit()

        logger.info(f"Report {report_id} processed: {len(chunks)} chunks, {len(chunk_models)} stored")

    except Exception as e:
        logger.exception(f"Failed to process report {report_id}: {e}")
        db.rollback()
        report = db.query(MedicalReport).filter(MedicalReport.id == report_id).first()
        if report:
            report.status = "error"
            report.error_message = str(e)
            db.commit()
    finally:
        db.close()
