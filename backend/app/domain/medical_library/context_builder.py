import logging
from typing import List, Dict, Any
import json
from app.infrastructure.ai_provider_service import AIProviderService

logger = logging.getLogger("medical_library.context_builder")

CLEANER_SYSTEM_PROMPT = """You are an Expert Medical Evidence Cleaner (Agent 1).
Your ONLY responsibility is to analyze raw retrieved medical text chunks and extract a clean, structured JSON object containing verified facts.

YOUR TASKS:
1. Remove OCR artifacts.
2. Remove page numbers, table references, and index entries.
3. Remove unrelated diseases or drugs.
4. Deduplicate facts. Mention each fact only once.
5. Synthesize the facts into a highly structured clinical summary.
6. If a piece of information is missing, leave the field null or empty. Do NOT invent facts.

IMPORTANT: Do NOT write prose paragraphs for the user. ONLY output the raw extracted facts in valid JSON format matching the schema.
"""

class ContextBuilder:
    """
    Stage 11: Context Building (Agent 1)
    Takes raw, noisy RAG chunks from textbooks and uses an LLM to clean, deduplicate, 
    and classify them into a pristine structured JSON object for the Medical Writer.
    """
    def __init__(self, ai_provider: AIProviderService):
        self.ai_provider = ai_provider

    def build_clean_context(self, query: str, chunks: List[Dict]) -> Dict[str, Any]:
        if not chunks:
            return {}

        combined_text = "\n\n---\n\n".join([c.get("text", "") for c in chunks])[:8000]
        
        prompt = (
            f"USER QUERY: {query}\n\n"
            f"RAW RETRIEVED CHUNKS:\n{combined_text}\n\n"
            f"Extract and organize the evidence into a clean JSON structure relevant to the query. "
            f"Include fields like overview, causes, symptoms, diagnosis, treatment, and pearls (if applicable)."
        )

        try:
            result = self.ai_provider._execute(
                request_type="context_builder",
                method="generate_structured",
                prompt=prompt,
                system_instruction=CLEANER_SYSTEM_PROMPT,
                use_cache=False,
                use_rag_models=True, # Use the RAG formatting model chain
            )

            if result.success:
                if isinstance(result.data, dict) and result.data and "error" not in result.data:
                    logger.info("Context Builder successfully extracted clean evidence.")
                    return result.data
                # Sometimes the AI returns well-structured text even though JSON parsing failed
                # Wrap the raw content as overview so the formatter can still use it
                if result.content and len(result.content.strip()) > 30:
                    logger.info("Context Builder returned non-JSON content; wrapping as overview.")
                    return {"overview": result.content.strip()[:4000]}

            logger.warning(f"Context Builder failed to extract structured JSON: {result.error}")
            # Fallback: build a minimal structure from the raw chunks
            return {"overview": combined_text[:3000]}

        except Exception as e:
            logger.error(f"Context Builder error: {e}")
            return {"overview": combined_text[:3000]}
