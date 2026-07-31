import hashlib
import json
import logging
import os
from typing import Optional

from app.core.config import settings
from app.infrastructure.embedding_provider import get_embedding_provider

logger = logging.getLogger("embedding_service")


class EmbeddingService:
    def __init__(self):
        self.provider = get_embedding_provider()
        self.dimension = self.provider.dimensions

    def embed(self, text: str) -> list[float]:
        return self.provider.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_batch(texts)

    def embed_document(self, text: str) -> dict:
        embedding = self.embed(text)
        return {
            "embedding": embedding,
            "dimension": self.dimension,
            "model": self.provider.model_name,
        }

logger.info(f"Embedding service ready (provider={get_embedding_provider().model_name})")
embedding_service = EmbeddingService()
