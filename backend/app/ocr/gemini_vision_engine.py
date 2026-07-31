import os
import logging
import cv2
import numpy as np
import google.generativeai as genai
from PIL import Image

logger = logging.getLogger(__name__)

_initialized = False

def _init_gemini():
    global _initialized
    if _initialized:
        return True
    
    # Try to load from env (settings handles this usually, but we fallback to os.environ)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not found in environment.")
        return False
        
    try:
        genai.configure(api_key=api_key)
        _initialized = True
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini: {e}")
        return False

def run(image: np.ndarray) -> tuple[str, float]:
    """
    Runs Gemini 1.5 Flash Vision on the full image to extract text perfectly.
    Returns (extracted_text, confidence)
    """
    if not _init_gemini():
        return "", 0.0
        
    try:
        if len(image.shape) == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
            
        pil_image = Image.fromarray(image_rgb)
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = (
            "You are a highly accurate medical OCR system. "
            "Extract all the text from this medical document exactly as written, including handwritten notes. "
            "Maintain the structure and formatting as much as possible. "
            "Do not add any conversational filler, markdown formatting (like ```), or summaries. "
            "Just output the raw extracted text."
        )
        
        response = model.generate_content([prompt, pil_image])
        text = response.text.strip()
        
        confidence = 0.98 if len(text) > 5 else 0.0
        
        return text, confidence
    except Exception as e:
        logger.error(f"Gemini Vision OCR failed: {e}")
        return "", 0.0
