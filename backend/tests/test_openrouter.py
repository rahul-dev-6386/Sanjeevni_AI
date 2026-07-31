import sys
import os
import asyncio
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.infrastructure.ai_provider_service import AIProviderService

def test():
    db = SessionLocal()
    try:
        service = AIProviderService(db)
        print(f"Has usable model: {service.has_usable_model()}")
        response = service.generate_response(
            prompt="Reply exactly with 'OPENROUTER_IS_WORKING'",
            system_instruction="You are a test bot.",
            temperature=0.0
        )
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test()
