import logging
from app.infrastructure.embedding_provider import OpenRouterEmbeddingProvider

logger = logging.getLogger("medical_library")

medical_embedder = OpenRouterEmbeddingProvider(
    model_name="nvidia/llama-nemotron-embed-vl-1b-v2:free",
    dimension=2048
)

def embed_texts(texts: list[str], batch_size: int = 256) -> list[list[float]]:
    return medical_embedder.embed_batch(texts)


def embed_query(query: str) -> list[float]:
    return medical_embedder.embed(query)
