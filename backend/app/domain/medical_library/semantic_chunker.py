import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger("medical_library.semantic_chunker")

# Common medical semantic headers that should NOT be split across chunks
SEMANTIC_HEADERS = [
    re.compile(r"^\s*(mechanism of action|mechanism)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(pharmacokinetics|pk)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(adverse effects|side effects)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(dosage|administration|dose)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(contraindications)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(clinical pearls|pearls)\s*$", re.IGNORECASE),
]

class SemanticChunker:
    """
    Stage 2 & 4: Semantic Document Parsing and Chunking
    Chunks documents by semantic boundaries (headers, sections) instead of arbitrary token limits.
    Ensures important sections (like Mechanism, Dosage) are kept intact.
    """
    def __init__(self, max_chunk_length: int = 4000):
        # We use a character limit as a proxy for tokens (approx 1000 tokens)
        self.max_chunk_length = max_chunk_length
        
    def _is_semantic_header(self, line: str) -> bool:
        """Detects if a line is a major medical section header."""
        for pattern in SEMANTIC_HEADERS:
            if pattern.match(line):
                return True
        return False
        
    def chunk_pages(self, pages: List[str], book_name: str) -> List[Dict[str, Any]]:
        """
        Takes clean page texts and chunks them semantically.
        Returns a list of dictionaries with text and basic structural metadata.
        """
        logger.info(f"Semantically chunking {len(pages)} pages from {book_name}")
        chunks = []
        
        current_chunk_lines = []
        current_chunk_length = 0
        
        for page_text in pages:
            lines = page_text.split("\n")
            for line in lines:
                line_len = len(line)
                
                # If we encounter a semantic header and the chunk is already reasonably sized, split here
                if self._is_semantic_header(line) and current_chunk_length > 1000:
                    chunks.append({
                        "text": "\n".join(current_chunk_lines),
                        "book": book_name
                    })
                    current_chunk_lines = []
                    current_chunk_length = 0
                    
                # Try to split cleanly at empty lines if we are past ideal length (3000 chars)
                if current_chunk_length > 3000 and not line.strip():
                    chunks.append({"text": "\n".join(current_chunk_lines), "book": book_name})
                    current_chunk_lines = []
                    current_chunk_length = 0
                    
                # HARD FORCE SPLIT if it exceeds max_chunk_length (8000)
                if current_chunk_length + line_len > 8000:
                    chunks.append({"text": "\n".join(current_chunk_lines), "book": book_name})
                    current_chunk_lines = []
                    current_chunk_length = 0
                    
                current_chunk_lines.append(line)
                current_chunk_length += line_len + 1 # +1 for newline
                
        # Append the last chunk
        if current_chunk_lines:
             chunks.append({
                "text": "\n".join(current_chunk_lines),
                "book": book_name
             })
             
        return chunks
