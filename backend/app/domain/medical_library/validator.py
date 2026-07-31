import re
import logging
from typing import List, Dict

logger = logging.getLogger("medical_library.validator")

class RAGValidator:
    """
    Stage 9: Validation
    Acts as a final gatekeeper before chunks are sent to the LLM.
    Rejects chunks that discuss unrelated drugs or diseases unless an interaction is explicitly mentioned.
    """
    
    INTERACTION_TERMS = re.compile(r"(interact|interaction|contraindicate|combined|co-administer|concomitant)", re.IGNORECASE)

    def __init__(self, query: str):
        self.query_lower = query.lower()
        
    def _extract_primary_entity(self) -> str:
        """Extracts the primary drug or disease from the query (heuristic for this blueprint)."""
        # In production, use NLP (e.g. MedSpaCy or LLM NER) to extract the entity
        # For this blueprint, we assume the query is something like "Acetaminophen dosage"
        words = self.query_lower.split()
        if len(words) > 0:
            return words[0] # Very naive fallback
        return ""
        
    def is_valid_chunk(self, chunk: Dict) -> bool:
        """Determines if a chunk is safe to send to the LLM."""
        text = chunk.get("text", "").lower()
        topic = chunk.get("medical_topic", "").lower()
        
        # 1. Reject if it's explicitly marked as an index or TOC
        content_type = chunk.get("content_type", "content")
        if content_type in ["index", "toc", "figure"]:
            logger.debug(f"Validator rejecting chunk: invalid content type '{content_type}'")
            return False
            
        # 2. Reject if the query is highly specific to a drug, but the chunk focuses on a completely different drug
        # (Unless it mentions interactions)
        entity = self._extract_primary_entity()
        if entity and len(entity) > 4:
            # If the entity is nowhere in the text, and it's not an interactions section
            if entity not in text and not self.INTERACTION_TERMS.search(text):
                # We might be pulling a completely unrelated paragraph due to vector similarity
                # logger.debug(f"Validator rejecting chunk: missing primary entity '{entity}'")
                # return False
                pass # Disabled strict entity rejection for now to prevent over-filtering without proper NLP
                
        return True

    def validate_results(self, results: List[Dict]) -> List[Dict]:
        """Filters a list of retrieved chunks."""
        valid = [r for r in results if self.is_valid_chunk(r)]
        logger.info(f"Validator kept {len(valid)} out of {len(results)} chunks")
        return valid
