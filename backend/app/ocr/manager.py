import io
import logging
import cv2
import numpy as np
from PIL import Image
from typing import Optional

from app.ocr import preprocessing
from app.ocr import confidence as conf_module
from app.ocr import medical_postprocess

logger = logging.getLogger(__name__)

class OcrManager:
    def __init__(self):
        self._openrouter = None

    def _get_openrouter(self):
        if self._openrouter is None:
            from app.ocr import openrouter_vision_engine
            self._openrouter = openrouter_vision_engine
        return self._openrouter

    def _bytes_to_cv2(self, file_bytes: bytes) -> np.ndarray:
        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def extract_text(self, file_bytes: bytes, file_type: str) -> str:
        result = self.extract_structured(file_bytes, file_type)
        return result.get("raw_text", "")

    def extract_structured(self, file_bytes: bytes, file_type: str) -> dict:
        if file_type == "application/pdf":
            return self._process_pdf(file_bytes)

        if file_type in ("image/jpeg", "image/jpg", "image/png"):
            return self._process_image(file_bytes)

        return {
            "raw_text": "",
            "confidence": 0.0,
            "engine": "none",
            "structured_data": {},
        }

    def _process_image(self, file_bytes: bytes) -> dict:
        image = self._bytes_to_cv2(file_bytes)
        if image is None:
            return {"raw_text": "", "confidence": 0.0, "engine": "none", "structured_data": {}}

        processed = preprocessing.preprocess(image)
        processed = preprocessing.resize_for_ocr(processed)

        openrouter = self._get_openrouter()
        text, conf, _ = openrouter.run(processed)
        
        engine_used = "OpenRouterVision"
        logger.info(f"OpenRouterVision confidence: {conf}")

        overall_conf = conf_module.assess(text, engine_used, conf, conf)
        result = medical_postprocess.postprocess(text, engine_used, overall_conf)
        return result

    def _process_pdf(self, file_bytes: bytes) -> dict:
        # 1. Try local extraction first for digitally generated PDFs
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            embedded_text = ""
            for page in reader.pages:
                embedded_text += page.extract_text() or ""
                
            if len(embedded_text.strip()) > 150:
                logger.info("PDF has embedded text. Bypassing OCR entirely.")
                overall_conf = conf_module.assess(embedded_text, "PyPDF2", 1.0)
                return {
                    "raw_text": embedded_text,
                    "confidence": 1.0,
                    "engine": "PyPDF2",
                    "structured_data": medical_postprocess.postprocess(
                        embedded_text, "PyPDF2", overall_conf
                    ).get("structured_data", {}),
                }
        except Exception as e:
            logger.info(f"Local PyPDF2 extraction not applicable: {e}")

        # 2. Proceed with OCR for scanned PDFs
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_bytes, dpi=300)
        except Exception as e:
            logger.warning(f"PDF to image conversion failed: {e}")
            return self._pdf_fallback(file_bytes)

        all_text = []
        all_conf = 0.0
        engine_used = "OpenRouterVision"
        count = 0

        for page_image in images:
            arr = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)
            processed = preprocessing.preprocess(arr)
            processed = preprocessing.resize_for_ocr(processed)

            openrouter = self._get_openrouter()
            page_text, page_conf, _ = openrouter.run(processed)
            
            if page_text.strip():
                all_text.append(page_text)
                all_conf += page_conf
                count += 1

        if not all_text:
            return self._pdf_fallback(file_bytes)

        avg_conf = round(all_conf / count, 4) if count else 0.0
        combined = "\n\n".join(all_text)
        overall_conf = conf_module.assess(combined, engine_used, avg_conf)
        result = medical_postprocess.postprocess(combined, engine_used, overall_conf)
        return result

    def _pdf_fallback(self, file_bytes: bytes) -> dict:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            if text.strip():
                return {
                    "raw_text": text,
                    "confidence": 0.9,
                    "engine": "PyPDF2",
                    "structured_data": medical_postprocess.postprocess(
                        text, "PyPDF2", 0.9
                    ).get("structured_data", {}),
                }
        except Exception:
            pass
        return {"raw_text": "", "confidence": 0.0, "engine": "none", "structured_data": {}}
