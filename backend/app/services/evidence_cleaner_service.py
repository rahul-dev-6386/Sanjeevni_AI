import logging
from typing import Any, Dict, List
from pydantic import BaseModel, Field
import json

from app.infrastructure.ai_provider_service import AIProviderService

logger = logging.getLogger("evidence_cleaner")

CLEANER_SYSTEM_PROMPT = """You are an Expert Clinical Evidence Cleaner (Agent 1).
Your ONLY responsibility is to analyze raw retrieved medical text chunks and extract a clean, structured JSON object.

YOUR TASKS:
1. Remove OCR artifacts (e.g. "Vardenaﬁ l" -> "Vardenafil").
2. Remove page numbers, table references, and index entries (e.g. "See page 12", "Figure 5.2").
3. Remove unrelated drug information (e.g. if the target drug is Sildenafil, ignore paragraphs about Nitroglycerin unless explicitly described as a drug interaction).
4. Deduplicate facts. Mention each fact only once.
5. Classify facts into the requested JSON sections.
6. If a piece of information is missing, leave the field null or empty. Do NOT invent facts.

IMPORTANT: Do NOT write a monograph. Do NOT write prose paragraphs. ONLY output the raw extracted facts in valid JSON format.
"""

class CleanedTextbookEvidence(BaseModel):
    mechanism_of_action: str = Field(default="", description="Mechanism of action of the drug")
    pharmacokinetics: str = Field(default="", description="Pharmacokinetics, half-life, protein binding, metabolism, etc.")
    clinical_pearls: List[str] = Field(default_factory=list, description="Unique clinical insights or important observations")
    interactions: List[str] = Field(default_factory=list, description="Drug-drug interactions")
    adverse_effects: List[str] = Field(default_factory=list, description="Side effects mentioned in textbooks")

class EvidenceCleanerService:
    """
    Agent 1: Evidence Cleaner
    Takes raw, noisy RAG chunks and uses an LLM to clean, deduplicate, 
    and classify them into structured JSON.
    """
    def __init__(self, ai_provider: AIProviderService):
        self.ai_provider = ai_provider

    def clean_textbook_chunks(self, target_drug: str, chunks: List[str]) -> CleanedTextbookEvidence:
        if not chunks:
            return CleanedTextbookEvidence()

        combined_text = "\n\n---\n\n".join(chunks)[:6000] # Limit size for context window
        
        prompt = (
            f"TARGET DRUG: {target_drug}\n\n"
            f"RAW TEXTBOOK CHUNKS:\n{combined_text}\n\n"
            f"Extract the evidence into JSON matching the provided schema."
        )

        try:
            # We use generate_response with JSON mode if supported, or just ask it to return JSON
            result = self.ai_provider.generate_response(
                prompt=prompt,
                system_instruction=CLEANER_SYSTEM_PROMPT,
                temperature=0.1
            )
            
            # Very basic JSON extraction from response
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL | re.IGNORECASE)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Attempt to parse the whole string
                json_str = result.strip()
                if not json_str.startswith("{"):
                    json_str = "{" + json_str.split("{", 1)[-1]
                if not json_str.endswith("}"):
                    json_str = json_str.rsplit("}", 1)[0] + "}"
                    
            data = json.loads(json_str)
            
            # Robust extraction to handle LLM hallucinations (lists/dicts instead of strings)
            moa = data.get("mechanism_of_action", "")
            if isinstance(moa, list): moa = " ".join(str(x) for x in moa)
            elif isinstance(moa, dict): moa = json.dumps(moa)
            elif not isinstance(moa, str): moa = str(moa)
                
            pk = data.get("pharmacokinetics", "")
            if isinstance(pk, list): pk = " ".join(str(x) for x in pk)
            elif isinstance(pk, dict): pk = json.dumps(pk)
            elif not isinstance(pk, str): pk = str(pk)
            
            return CleanedTextbookEvidence(
                mechanism_of_action=moa,
                pharmacokinetics=pk,
                clinical_pearls=data.get("clinical_pearls", []) if isinstance(data.get("clinical_pearls"), list) else [],
                interactions=data.get("interactions", []) if isinstance(data.get("interactions"), list) else [],
                adverse_effects=data.get("adverse_effects", []) if isinstance(data.get("adverse_effects"), list) else []
            )
        except Exception as e:
            logger.error(f"Evidence Cleaner failed: {e}")
            return CleanedTextbookEvidence()
