import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("embedding_provider")


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...


class OpenRouterEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: Optional[str] = None, dimension: Optional[int] = None):
        self.api_key = settings.OPENROUTER_API_KEY
        self._model = model_name or settings.EMBEDDING_MODEL
        self._dim = dimension or settings.EMBEDDING_DIMENSION
        self._url = "https://openrouter.ai/api/v1/embeddings"

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data or not data["data"]:
                raise RuntimeError(f"OpenRouter returned unexpected response: {data}")
            items = sorted(data["data"], key=lambda x: x.get("index", 0))
            return [item["embedding"] for item in items]

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return f"openrouter/{self._model}"


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self._model = "models/gemini-embedding-001"
        self._dim = 768

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
        except Exception as e:
            raise RuntimeError(f"Gemini init failed: {e}")

        results = []
        for text in texts:
            result = genai.embed_content(model=self._model, content=text)
            results.append(result["embedding"])
        return results

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model


_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is not None:
        return _provider

    provider_name = settings.EMBEDDING_PROVIDER
    if provider_name == "openrouter":
        _provider = OpenRouterEmbeddingProvider()
    elif provider_name == "gemini":
        _provider = GeminiEmbeddingProvider()
    else:
        raise ValueError(f"Unknown embedding provider: {provider_name}")

    logger.info(f"Embedding provider: {_provider.model_name} ({_provider.dimensions}d)")
    return _provider
