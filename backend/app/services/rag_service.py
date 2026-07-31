"""
RAGService — Qdrant-backed knowledge base (no LangChain / FAISS / HuggingFace).

Uses the project's existing infrastructure:
  - Embeddings  → infrastructure.embedding_service (OpenRouter / Gemini)
  - Vector store → Qdrant (already running for the medical library)
  - LLM answers  → infrastructure.ai_provider_service (OpenRouter / Gemini / Groq)
"""
import logging
import uuid
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_COLLECTION = "knowledge_base"
_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 150


# ── helpers ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> List[str]:
    """Split text into overlapping chunks."""
    chunks, start = [], 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def _get_qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
    )


def _ensure_collection(client, dimension: int):
    from qdrant_client.http import models as qm
    existing = [c.name for c in client.get_collections().collections]
    if _COLLECTION not in existing:
        client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=qm.VectorParams(
                size=dimension,
                distance=qm.Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection '{_COLLECTION}' (dim={dimension})")


def _embed(texts: List[str]) -> List[List[float]]:
    from app.infrastructure.embedding_service import embed_texts
    return embed_texts(texts)


def _embed_one(text: str) -> List[float]:
    vecs = _embed([text])
    return vecs[0] if vecs else []


# ── RAGService ────────────────────────────────────────────────────────────────

class RAGService:
    """Lightweight RAG service backed by Qdrant and project-level AI providers."""

    def add_documents(self, texts: List[str]):
        """Chunk, embed, and upsert texts into Qdrant."""
        all_chunks = []
        for text in texts:
            all_chunks.extend(_chunk_text(text))

        if not all_chunks:
            return

        vectors = _embed(all_chunks)
        if not vectors:
            logger.warning("Embedding failed — documents not ingested.")
            return

        dimension = len(vectors[0])
        client = _get_qdrant()
        _ensure_collection(client, dimension)

        from qdrant_client.http import models as qm
        points = [
            qm.PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={"text": chunk},
            )
            for chunk, vec in zip(all_chunks, vectors)
        ]
        client.upsert(collection_name=_COLLECTION, points=points)
        logger.info(f"Upserted {len(points)} chunks into '{_COLLECTION}'")

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """Semantic search over the knowledge base."""
        try:
            query_vec = _embed_one(query)
            if not query_vec:
                return []

            client = _get_qdrant()
            hits = client.search(
                collection_name=_COLLECTION,
                query_vector=query_vec,
                limit=top_k,
                with_payload=True,
            )
            return [
                {"content": h.payload.get("text", ""), "score": round(h.score, 4)}
                for h in hits
            ]
        except Exception as e:
            logger.warning(f"RAGService.search failed: {e}")
            return []

    def query_with_context(self, query: str, user_context: str = "") -> str:
        """Search + generate an answer with the project AI provider."""
        results = self.search(query, top_k=5)
        if not results:
            return "Knowledge base is empty. Ingest documents first."

        context_text = "\n\n---\n\n".join(r["content"] for r in results)
        prompt = (
            "You are a medical knowledge assistant. "
            "Use the retrieved context to answer the question. "
            "Always cite your sources. "
            "If the context is insufficient, say so clearly.\n\n"
            f"User Health Context:\n{user_context}\n\n"
            f"Retrieved Knowledge:\n{context_text}\n\n"
            f"Question: {query}\n\nAnswer:"
        )

        try:
            from app.infrastructure.ai_provider_service import AIProviderService
            provider = AIProviderService()
            return provider.complete(prompt)
        except Exception as e:
            logger.warning(f"RAGService LLM call failed: {e}")
            # Graceful degradation: return raw chunks
            return context_text

    def rebuild_index(self, texts: List[str]):
        """Delete and rebuild the collection from scratch."""
        try:
            client = _get_qdrant()
            existing = [c.name for c in client.get_collections().collections]
            if _COLLECTION in existing:
                client.delete_collection(_COLLECTION)
                logger.info(f"Dropped collection '{_COLLECTION}'")
        except Exception as e:
            logger.warning(f"Could not drop collection: {e}")
        self.add_documents(texts)

    def get_status(self) -> dict:
        try:
            client = _get_qdrant()
            existing = [c.name for c in client.get_collections().collections]
            if _COLLECTION not in existing:
                return {"index_loaded": False, "total_documents": 0, "dimension": 0}
            info = client.get_collection(_COLLECTION)
            return {
                "index_loaded": True,
                "total_documents": info.points_count,
                "dimension": info.config.params.vectors.size,
            }
        except Exception as e:
            logger.warning(f"RAGService.get_status failed: {e}")
            return {"index_loaded": False, "total_documents": 0, "dimension": 0}


rag_service = RAGService()
