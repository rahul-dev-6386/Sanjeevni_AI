import sys
import os

# Add backend directory to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from app.core.database import SessionLocal
from app.models.report import MedicalReport
from app.models.biomarker import BiomarkerTracking, TimelineEvent, AIInsight
from app.infrastructure.ai_provider_service import ai_provider
from app.services.classification_service import classification_service
from datetime import datetime

def main():
    db = SessionLocal()
    reports = db.query(MedicalReport).all()
    for report in reports:
        print(f"Reprocessing report {report.id}...")
        if not report.extracted_text:
            print("No extracted text, skipping.")
            continue

        # Re-classify and extract structured data
        try:
            classification_result = classification_service.classify(report.extracted_text, report.original_filename or "")
            report.document_type = classification_result.get("document_type", report.document_type or "General Medical Report")
            report.report_type = report.document_type

            structured = classification_service.extract_structured(report.extracted_text, report.document_type)
            report.structured_data = structured

            health_score = structured.get("health_score")
            if health_score is not None:
                report.health_score = min(100, max(0, int(health_score)))

            risk_scores = structured.get("risk_scores", {})
            if risk_scores:
                report.risk_scores = risk_scores
            print(f"  Re-classified as: {report.document_type}")
        except Exception as e:
            structured = report.structured_data or {}
            print(f"  Classification failed, using existing: {e}")

        analysis_prompt = (
            f"Document type: {report.document_type}\n"
            f"Extracted Document Text:\n---\n{report.extracted_text[:8000]}\n---\n\n"
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
        print(f"  Updated ai_summary for {report.id}")

        # Store intelligence data
        try:
            # Clear old intelligence data
            db.query(BiomarkerTracking).filter(BiomarkerTracking.report_id == report.id).delete()
            db.query(TimelineEvent).filter(TimelineEvent.report_id == report.id).delete()
            db.query(AIInsight).filter(AIInsight.report_id == report.id).delete()
            db.commit()

            # Store biomarkers
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
                    user_id=report.user_id,
                    report_id=report.id,
                    biomarker_name=name,
                    value=numeric_value,
                    value_text=str(raw_value or ""),
                    unit=item.get("unit", ""),
                    reference_range=item.get("reference_range", item.get("range", "")),
                    is_abnormal=item.get("flag") not in (None, "", "normal", "NORMAL"),
                    flag=item.get("flag"),
                )
                db.add(tracking)

            # Store timeline events
            timeline_events = structured.get("timeline_events", [])
            for event in timeline_events:
                try:
                    evt_date = datetime.fromisoformat(event["date"]) if event.get("date") else datetime.utcnow()
                except (ValueError, KeyError):
                    evt_date = datetime.utcnow()
                te = TimelineEvent(
                    user_id=report.user_id,
                    report_id=report.id,
                    event_type=event.get("type", report.document_type.lower().replace(" ", "_")),
                    title=event.get("event", f"{report.document_type} Uploaded"),
                    description=event.get("description", ""),
                    severity=event.get("severity", "info"),
                    event_date=evt_date,
                )
                db.add(te)

            # Store risk insights
            risk_scores = structured.get("risk_scores", {})
            for condition, score in risk_scores.items():
                if score is None:
                    continue
                level = "good" if score < 30 else "attention" if score < 60 else "critical"
                label = condition.replace("_", " ").title()
                insight = AIInsight(
                    user_id=report.user_id,
                    report_id=report.id,
                    insight_type="risk",
                    title=f"{label} Risk: {int(score)}%",
                    description=f"Your {label.lower()} risk score is {int(score)}%.",
                    trend="stable",
                    severity=level,
                )
                db.add(insight)

            db.commit()
            print(f"  Stored intelligence data for {report.id}")
        except Exception as e:
            db.rollback()
            print(f"  Failed to store intelligence data: {e}")

        # Process report intelligence (lab extraction from text)
        try:
            from app.services.report_intelligence_service import ReportIntelligenceService
            intelligence = ReportIntelligenceService(db)
            intelligence.process_report(report.id, report.user_id)
            print(f"  Processed report intelligence for {report.id}")
        except Exception as e:
            print(f"  Failed to process intelligence: {e}")

        report.processed = True
    db.commit()
    print("Done reprocessing.")

if __name__ == "__main__":
    main()
