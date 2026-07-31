import logging
from typing import Dict, Any

logger = logging.getLogger("medical_library.metadata_extractor")

class MetadataExtractor:
    """
    Stage 3: Metadata Generation
    Analyzes a semantic chunk and attaches structural metadata
    to enable precise filtering (e.g., dropping index chunks).
    """
    
    def _detect_content_type(self, text: str) -> str:
        """Determines if the chunk is content, toc, figure, or index."""
        text_lower = text.lower()
        if "table of contents" in text_lower[:200]:
            return "toc"
        if text_lower.startswith("figure") or text_lower.startswith("fig."):
            return "figure"
        if "index" in text_lower[:100] and len(text) < 1000:
            return "index"
        return "content"
        
    def _extract_disease_or_drug(self, text: str) -> str:
        """Basic heuristic to extract the primary topic (can be enhanced with NLP/LLM later)."""
        # In a full production system, we'd use SpaCy or an LLM NER here.
        # For now, we look at the first line assuming it's a section header.
        first_line = text.split("\n")[0].strip()
        if len(first_line) < 50:
            return first_line
        return ""

    def enrich_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Adds structured metadata to the chunk dictionary."""
        text = chunk["text"]
        
        content_type = self._detect_content_type(text)
        topic = self._extract_disease_or_drug(text)
        
        chunk["metadata"] = {
            "book": chunk.get("book", "Unknown"),
            "content_type": content_type,
            "topic": topic,
            "char_count": len(text)
        }
        return chunk
