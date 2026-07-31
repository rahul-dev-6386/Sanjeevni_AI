import logging
from typing import Dict, Any, List
import json
from app.infrastructure.ai_provider_service import AIProviderService

logger = logging.getLogger("medical_library.formatter")

WRITER_SYSTEM_PROMPT = """You are an Expert Medical Writer (Agent 2).
Your ONLY responsibility is to take a structured JSON object containing verified medical facts and render it into a beautiful, user-friendly markdown page.

YOUR TASKS:
1. You will receive a clean JSON object containing evidence.
2. Render the information into a highly professional markdown format.
3. Use modern medical formatting (bullet points, clear headers, bold text for diseases/drugs).
4. NEVER invent facts. If a section is empty in the JSON, do not include it.
5. NEVER mention the JSON, the retrieval process, or "Agent 1". Act as if you are the author of a Medscape or UpToDate article.

FORMATTING RULES:
- Use H2 (##) for main sections
- Use bullet points for symptoms, causes, etc.
- Use **bold** for key terms
- Keep paragraphs very short (1-3 sentences)
"""

class RAGFormatter:
    """
    Stage 12: Output (Agent 2)
    Takes the pristine structured JSON from ContextBuilder and uses the LLM 
    to render it into a perfect, hallucination-free UI markdown response.
    """
    def __init__(self, ai_provider: AIProviderService):
        self.ai_provider = ai_provider

    def generate_final_markdown(self, query: str, clean_context: Dict[str, Any], intent: str) -> str:
        prompt = (
            f"USER QUERY: {query}\n\n"
            f"INTENT CATEGORY: {intent}\n\n"
            f"VERIFIED CLINICAL EVIDENCE (JSON):\n{json.dumps(clean_context, indent=2)}\n\n"
            f"Render this evidence into a polished, professional medical response. Do not add unsupported facts."
        )

        try:
            result = self.ai_provider._execute(
                request_type="rag_formatter",
                method="generate_response",
                prompt=prompt,
                system_instruction=WRITER_SYSTEM_PROMPT,
                temperature=0.3,
                use_cache=False,
            )
            
            if result.success and result.content:
                logger.info("Formatter successfully generated markdown.")
                return result.content
            else:
                logger.warning(f"Formatter failed to generate markdown: {result.error}")
                return ""  # Return empty string so answer_generator falls back to ai_failed mode
                
        except Exception as e:
            logger.error(f"Formatter error: {e}")
            return ""  # Return empty string so answer_generator falls back to ai_failed mode
