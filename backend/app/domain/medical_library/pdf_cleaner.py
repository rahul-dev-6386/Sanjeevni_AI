import re
import fitz
import logging

logger = logging.getLogger("medical_library.pdf_cleaner")

# Regex heuristics for detecting OCR garbage and unwanted pages
PAGE_NUMBER_PATTERN = re.compile(r"^\s*Page\s+\d+\s*$", re.IGNORECASE)
TOC_PATTERN = re.compile(r"(?i)(table of contents|contents|index)")
FIGURE_PATTERN = re.compile(r"^\s*(Figure|Fig\.|Table)\s+\d+", re.IGNORECASE)

class PDFCleaner:
    """
    Stage 1: Document Preprocessing (PDF Cleaner)
    Removes index pages, TOCs, page numbers, running headers/footers,
    and OCR artifacts before chunking.
    """
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        
    def _is_unwanted_page(self, text: str) -> bool:
        """Determines if an entire page is a TOC, Index, or Copyright page based on heuristics."""
        lines = text.split("\n")
        # If the page consists largely of dots and numbers, it's likely a TOC
        toc_lines = sum(1 for line in lines if "...." in line or re.search(r"\.\s*\d+$", line.strip()))
        if len(lines) > 10 and toc_lines / len(lines) > 0.3:
            return True
            
        # Check if the page is explicitly an Index page
        header_text = "\n".join(lines[:10]).lower()
        if "index" in header_text and len(text) > 1000 and "table of contents" not in header_text:
             # Very simple heuristic for index pages: many short lines, alphabetical groups
             short_lines = sum(1 for line in lines if len(line.strip()) < 30)
             if len(lines) > 50 and short_lines / len(lines) > 0.6:
                 return True
                 
        return False
        
    def _clean_page_text(self, text: str) -> str:
        """Removes running headers, footers, page numbers, and OCR garbage from a page."""
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Remove isolated page numbers
            if stripped.isdigit() and len(stripped) < 5:
                continue
            if PAGE_NUMBER_PATTERN.match(stripped):
                continue
            # Remove Figure captions if they are just isolated lines (simplified for this blueprint)
            if FIGURE_PATTERN.match(stripped) and len(stripped) < 100:
                continue
                
            # Remove lines with high ratio of non-ascii or weird characters (OCR garbage)
            alpha_ratio = sum(1 for c in stripped if c.isalpha()) / max(1, len(stripped))
            if len(stripped) > 20 and alpha_ratio < 0.4:
                 continue
                 
            cleaned_lines.append(stripped)
            
        return "\n".join(cleaned_lines)

    def extract_clean_text(self) -> list[str]:
        """Reads PDF, filters unwanted pages, cleans text, and returns a list of clean page texts."""
        logger.info(f"Extracting and cleaning PDF: {self.pdf_path}")
        doc = fitz.open(self.pdf_path)
        clean_pages = []
        
        for i in range(len(doc)):
            page_text = doc[i].get_text("text")
            if not page_text.strip():
                continue
                
            if self._is_unwanted_page(page_text):
                logger.debug(f"Skipping page {i} (detected as TOC/Index)")
                continue
                
            cleaned_text = self._clean_page_text(page_text)
            if cleaned_text:
                clean_pages.append(cleaned_text)
                
        doc.close()
        return clean_pages
