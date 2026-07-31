import os
import logging
import cv2
import numpy as np
import base64
import httpx
from PIL import Image
import json

logger = logging.getLogger(__name__)

MODELS_IN_ORDER = [
    "google/gemma-4-31b:free",
    "google/gemma-4-26b-a4b:free",
    "qwen/qwen3.5-122b-a10b:free", # Using :free based on "(if free)" note
    "qwen/qwen3.5-27b",
    "google/gemma-3-12b"
]

def run(image: np.ndarray) -> tuple[str, float, list]:
    """
    Runs OCR using OpenRouter vision models with fallback.
    Returns (extracted_text, confidence, lines)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not found in environment.")
        return "", 0.0

    try:
        # Convert image to base64 jpeg
        success, encoded_image = cv2.imencode('.jpg', image)
        if not success:
            logger.error("Failed to encode image for OpenRouter.")
            return "", 0.0
            
        b64_img = base64.b64encode(encoded_image.tobytes()).decode("utf-8")
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://medico.local",
            "X-Title": "Medico OCR"
        }
        
        prompt = (
            "You are a highly accurate medical OCR system. "
            "Extract all the text from this medical document exactly as written, including handwritten notes. "
            "Maintain the structure and formatting as much as possible. "
            "Do not add any conversational filler, markdown formatting (like ```), or summaries. "
            "Just output the raw extracted text."
        )

        for model_name in MODELS_IN_ORDER:
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                        ]
                    }
                ]
            }
            
            logger.info(f"Trying OpenRouter OCR with model: {model_name}")
            try:
                # Using httpx to call OpenRouter
                with httpx.Client(timeout=30) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            text = data["choices"][0]["message"]["content"].strip()
                            confidence = 0.95 if len(text) > 5 else 0.0
                            logger.info(f"OCR successful with model {model_name}")
                            return text, confidence, []
                    else:
                        logger.warning(f"Model {model_name} failed with status {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.warning(f"Exception calling {model_name}: {e}")
                
        logger.error("All OpenRouter vision models failed.")
        return "", 0.0, []
        
    except Exception as e:
        logger.error(f"OpenRouter Vision OCR failed: {e}")
        return "", 0.0, []

