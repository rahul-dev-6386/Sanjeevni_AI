from sqlalchemy.orm import Session
from typing import Optional, Generator
import json

from app.models.chat import ChatSession, ChatMessage
from app.models.memory import MemoryEntry
from app.models.profile import PatientProfile
from app.models.metrics import DailyMetric
from app.models.medication import Medication
from app.models.report import MedicalReport
from app.infrastructure.ai_provider_service import ai_provider
from app.services.safety_service import SafetyService
from app.services.query_router import QueryRouter
from app.services.context_fusion_service import ContextFusionService


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.safety = SafetyService()

    def create_session(self, user_id: int, title: str = "New Chat") -> ChatSession:
        session = ChatSession(user_id=user_id, title=title)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_user_sessions(self, user_id: int) -> list[ChatSession]:
        return (
            self.db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )

    def get_session_messages(self, session_id: int) -> list[ChatMessage]:
        return (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
            .all()
        )

    def send_message(self, session_id: int, user_id: int, content: str):
        safety_result = self.safety.check_message(content)
        if safety_result["emergency"]:
            user_msg = ChatMessage(session_id=session_id, role="user", content=content)
            self.db.add(user_msg)
            emergency_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=safety_result["message"],
            )
            self.db.add(emergency_msg)
            self.db.commit()
            return {"emergency": True, "message": safety_result["message"]}

        user_msg = ChatMessage(session_id=session_id, role="user", content=content)
        self.db.add(user_msg)

        router = QueryRouter(self.db)
        route_result = router.route(content, user_id)

        if route_result["intent"] == "emergency":
            self.db.commit()
            return {"emergency": True, "message": route_result["response"]}

        patient_summary = self._build_patient_summary(user_id)
        history = self.get_session_messages(session_id)
        conversation_context = self._build_conversation_context(history)

        system_prompt = (
            "You are **Medico AI**. You are an evidence-based medical assistant. "
            "You provide structured, scannable health information from medical guidelines, research, and patient data. "
            "You are NOT a doctor and must NEVER claim to provide definitive diagnoses or prescriptions. "
            "Always include a disclaimer where appropriate. "
            "Use the patient's health profile to personalize your response.\n\n"
            "## Formatting Rules\n\n"
            "Never return large paragraphs. Always use:\n"
            "- `# Main heading` at the top\n"
            "- `## Sections` with relevant emoji (use sparingly)\n"
            "- `### Subsections` when needed\n"
            "- Bullet lists and numbered lists\n"
            "- Markdown tables when comparing values\n"
            "- Blockquotes (`>`) for important notes or red flags\n"
            "- **Bold** for diseases, medications, and laboratory tests\n"
            "- Emojis sparingly (only: 🩺📊⚠️✅🚨💬📚) to improve scanning\n\n"
            "Keep answers visually structured. The user should understand the answer within 10 seconds.\n\n"
            "Use this template for general medical answers:\n"
            "- `# Short Answer` — 2-3 sentence explanation\n"
            "- `## 🩺 What It Means` — explain simply\n"
            "- `## 📊 Key Findings` — bullet list\n"
            "- `## 📋 Interpretation` — table when possible\n"
            "- `## ⚠️ Possible Causes` — grouped Common / Less Common\n"
            "- `## ✅ What You Can Do` — actionable advice\n"
            "- `## 🚨 Seek Medical Care Immediately If` — bullet list\n"
            "- `## 💬 If You Have Your Results` — ask for specific values\n"
            "- `## 📚 References` — sources used\n\n"
            f"## Patient Profile\n{patient_summary}"
        )

        if route_result.get("response"):
            citations_text = ""
            if route_result.get("citations"):
                citations_text = "\n\n📚 **Retrieved Sources:**\n"
                for c in route_result["citations"]:
                    url = f" ({c['url']})" if c.get("url") else ""
                    citations_text += f"- {c['title']} — *{c['source']}*{url}\n"
            system_prompt += f"\n\n## Retrieved Medical Knowledge\n{route_result['response']}{citations_text}"

        ai_response = ai_provider.generate_chat_response(
            message=content,
            context=conversation_context,
            system_instruction=system_prompt,
        )

        if route_result["citations"]:
            ai_response += "\n\n---\n📚 **Sources:**\n"
            seen = set()
            for c in route_result["citations"]:
                key = (c["source"], c["title"])
                if key not in seen:
                    seen.add(key)
                    url = f" ({c['url']})" if c.get("url") else ""
                    ai_response += f"- {c['title']} — *{c['source']}*{url}\n"

        assistant_msg = ChatMessage(
            session_id=session_id, role="assistant", content=ai_response
        )
        self.db.add(assistant_msg)

        session = (
            self.db.query(ChatSession)
            .filter(ChatSession.id == session_id)
            .first()
        )
        if session:
            from sqlalchemy.sql import func
            session.updated_at = func.now()

        self.db.commit()

        return {"emergency": False, "message": ai_response}

    def stream_response(self, session_id: int, user_id: int, content: str) -> Generator[str, None, None]:
        safety_result = self.safety.check_message(content)
        if safety_result["emergency"]:
            yield f"data: {json.dumps({'type': 'error', 'content': safety_result['message']})}\n\n"
            return

        user_msg = ChatMessage(session_id=session_id, role="user", content=content)
        self.db.add(user_msg)
        self.db.flush()

        router = QueryRouter(self.db)
        route_result = router.route(content, user_id)

        if route_result["intent"] == "emergency":
            self.db.commit()
            yield f"data: {json.dumps({'type': 'error', 'content': route_result['response']})}\n\n"
            return

        patient_summary = self._build_patient_summary(user_id)
        history = self.get_session_messages(session_id)
        conversation_context = self._build_conversation_context(history)

        system_prompt = (
            "You are **Medico AI**. You are an evidence-based medical assistant. "
            "You provide structured, scannable health information from medical guidelines, research, and patient data. "
            "You are NOT a doctor and must NEVER claim to provide definitive diagnoses or prescriptions. "
            "Always include a disclaimer where appropriate. "
            "Use the patient's health profile to personalize your response.\n\n"
            "## Formatting Rules\n\n"
            "Never return large paragraphs. Always use:\n"
            "- `# Main heading` at the top\n"
            "- `## Sections` with relevant emoji (use sparingly)\n"
            "- `### Subsections` when needed\n"
            "- Bullet lists and numbered lists\n"
            "- Markdown tables when comparing values\n"
            "- Blockquotes (`>`) for important notes or red flags\n"
            "- **Bold** for diseases, medications, and laboratory tests\n"
            "- Emojis sparingly (only: 🩺📊⚠️✅🚨💬📚) to improve scanning\n\n"
            "Keep answers visually structured. The user should understand the answer within 10 seconds.\n\n"
            "Use this template for general medical answers:\n"
            "- `# Short Answer` — 2-3 sentence explanation\n"
            "- `## 🩺 What It Means` — explain simply\n"
            "- `## 📊 Key Findings` — bullet list\n"
            "- `## 📋 Interpretation` — table when possible\n"
            "- `## ⚠️ Possible Causes` — grouped Common / Less Common\n"
            "- `## ✅ What You Can Do` — actionable advice\n"
            "- `## 🚨 Seek Medical Care Immediately If` — bullet list\n"
            "- `## 💬 If You Have Your Results` — ask for specific values\n"
            "- `## 📚 References` — sources used\n\n"
            f"## Patient Profile\n{patient_summary}"
        )

        if route_result.get("response"):
            citations_text = ""
            if route_result.get("citations"):
                citations_text = "\n\n📚 **Retrieved Sources:**\n"
                for c in route_result["citations"]:
                    url = f" ({c['url']})" if c.get("url") else ""
                    citations_text += f"- {c['title']} — *{c['source']}*{url}\n"
            system_prompt += f"\n\n## Retrieved Medical Knowledge\n{route_result['response']}{citations_text}"

        full_response = ""
        try:
            for token in ai_provider.generate_chat_response_stream(
                message=content,
                context=conversation_context,
                system_instruction=system_prompt,
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'content': 'AI temporarily unavailable. Please try again.'})}\n\n"
            self.db.rollback()
            return

        if route_result["citations"]:
            citations_text = "\n\n---\n📚 **Sources:**\n"
            seen = set()
            for c in route_result["citations"]:
                key = (c["source"], c["title"])
                if key not in seen:
                    seen.add(key)
                    url = f" ({c['url']})" if c.get("url") else ""
                    citations_text += f"- {c['title']} — *{c['source']}*{url}\n"
            full_response += citations_text
            yield f"data: {json.dumps({'type': 'citations', 'content': citations_text})}\n\n"

        assistant_msg = ChatMessage(
            session_id=session_id, role="assistant", content=full_response
        )
        self.db.add(assistant_msg)

        session = (
            self.db.query(ChatSession)
            .filter(ChatSession.id == session_id)
            .first()
        )
        if session:
            from sqlalchemy.sql import func
            session.updated_at = func.now()

        self.db.commit()
        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id})}\n\n"

    def _build_patient_summary(self, user_id: int) -> str:
        profile = (
            self.db.query(PatientProfile)
            .filter(PatientProfile.user_id == user_id)
            .first()
        )
        memory_entries = (
            self.db.query(MemoryEntry)
            .filter(MemoryEntry.user_id == user_id)
            .all()
        )
        recent_metrics = (
            self.db.query(DailyMetric)
            .filter(DailyMetric.user_id == user_id)
            .order_by(DailyMetric.date.desc())
            .limit(7)
            .all()
        )
        medications = (
            self.db.query(Medication)
            .filter(Medication.user_id == user_id, Medication.active == True)
            .all()
        )
        recent_reports = (
            self.db.query(MedicalReport)
            .filter(MedicalReport.user_id == user_id)
            .order_by(MedicalReport.uploaded_at.desc())
            .limit(5)
            .all()
        )

        summary_parts = []

        if profile:
            if profile.chronic_diseases:
                summary_parts.append(
                    f"Chronic Conditions: {', '.join(profile.chronic_diseases)}"
                )
            if profile.allergies:
                summary_parts.append(f"Allergies: {', '.join(profile.allergies)}")
            if profile.date_of_birth:
                from datetime import date
                today = date.today()
                age = today.year - profile.date_of_birth.year
                summary_parts.append(f"Age: {age}")

        if medications:
            med_list = [
                f"{m.name} ({m.dosage}, {m.frequency})" for m in medications
            ]
            summary_parts.append(f"Current Medications: {'; '.join(med_list)}")

        if recent_metrics:
            avg_sleep = sum(
                (m.sleep_hours or 0) for m in recent_metrics if m.sleep_hours
            ) / max(
                sum(1 for m in recent_metrics if m.sleep_hours), 1
            )
            avg_water = sum(
                (m.water_ml or 0) for m in recent_metrics if m.water_ml
            ) / max(sum(1 for m in recent_metrics if m.water_ml), 1)
            summary_parts.append(f"Average Sleep: {avg_sleep:.1f} hours/day")
            summary_parts.append(f"Average Water Intake: {avg_water:.0f} ml/day")

        if recent_reports:
            report_summary = []
            for r in recent_reports:
                parts = [f"{r.report_type.upper()} report ({r.uploaded_at.strftime('%b %d, %Y')})"]
                if r.ai_summary:
                    parts.append(f"summary: {r.ai_summary[:200]}")
                if r.health_score is not None:
                    parts.append(f"health score: {r.health_score}/10")
                if r.risk_scores:
                    parts.append(f"risk scores: available")
                report_summary.append("; ".join(parts))
            summary_parts.append(f"Recent Medical Reports:\n" + "\n".join(f"  - {s}" for s in report_summary))

        for entry in memory_entries:
            summary_parts.append(f"{entry.key}: {entry.value}")

        return "\n".join(summary_parts) if summary_parts else "No patient data available."

    def _build_conversation_context(self, messages: list[ChatMessage]) -> str:
        context = "## Conversation History\n"
        for msg in messages[-10:]:
            context += f"{msg.role.capitalize()}: {msg.content}\n"
        return context
