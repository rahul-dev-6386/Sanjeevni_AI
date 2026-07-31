import os
import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import settings

logger = logging.getLogger("medical_library")

QDRANT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "library_qdrant")

COLLECTIONS = ["diseases", "laboratory", "pharmacology", "clinical_practice"]
EMBEDDING_DIM = settings.EMBEDDING_DIMENSION

_client_instance: Optional[QdrantClient] = None


def get_client() -> QdrantClient:
    global _client_instance
    if _client_instance is None:
        if settings.QDRANT_URL and settings.QDRANT_API_KEY:
            _client_instance = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY
            )
        else:
            os.makedirs(QDRANT_PATH, exist_ok=True)
            _client_instance = QdrantClient(path=QDRANT_PATH)
    return _client_instance


def reset_client():
    global _client_instance
    if _client_instance is not None:
        try:
            _client_instance.close()
        except Exception:
            pass
        _client_instance = None


def _ensure_content_type_index(client: QdrantClient, collection: str):
    """Create a keyword payload index for 'content_type' if it doesn't already exist.
    Qdrant requires an index to use keyword filters on payload fields."""
    try:
        client.create_payload_index(
            collection_name=collection,
            field_name="content_type",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )
        logger.info(f"Created 'content_type' payload index on collection: {collection}")
    except Exception as e:
        # Index may already exist; Qdrant raises an error in that case – safe to ignore
        logger.debug(f"Payload index for 'content_type' on '{collection}' skipped: {e}")


def ensure_payload_indexes(client: Optional[QdrantClient] = None):
    """Retrofit keyword payload indexes onto all existing collections.
    Call once at startup to fix collections created without indexes."""
    if client is None:
        client = get_client()
    for name in COLLECTIONS:
        _ensure_content_type_index(client, name)


def init_collections(client: Optional[QdrantClient] = None):
    if client is None:
        client = get_client()
    for name in COLLECTIONS:
        existing = client.get_collections().collections
        if name not in [c.name for c in existing]:
            client.create_collection(
                collection_name=name,
                vectors_config=qm.VectorParams(
                    size=EMBEDDING_DIM,
                    distance=qm.Distance.COSINE,
                ),
                optimizers_config=qm.OptimizersConfigDiff(
                    default_segment_number=2,
                ),
                hnsw_config=qm.HnswConfigDiff(
                    m=32,
                    ef_construct=200,
                ),
            )
            logger.info(f"Created collection: {name} (dim={EMBEDDING_DIM})")
        else:
            info = client.get_collection(collection_name=name)
            logger.info(f"Collection exists: {name} ({info.points_count} points)")
        # Always ensure the payload index exists (no-op if already present)
        _ensure_content_type_index(client, name)


def upload_batch(client: QdrantClient, collection: str, chunks: list[dict], vectors: list[list[float]], global_start_index: int = 0):
    if len(chunks) != len(vectors):
        raise ValueError(f"Chunks/vectors mismatch: {len(chunks)} chunks vs {len(vectors)} vectors")

    points = []
    for offset, (chunk, vector) in enumerate(zip(chunks, vectors)):
        global_i = global_start_index + offset
        book_name = chunk.get("book", "")
        metadata = chunk.get("metadata", {})
        payload = {
            "source_book": book_name,
            "chapter": chunk.get("chapter", ""),
            "section": chunk.get("section", ""),
            "collection": collection,
            "page_number": str(chunk.get("page_number", "")),
            "medical_topic": metadata.get("topic", ""),
            "content_type": metadata.get("content_type", "content"),
            "char_count": metadata.get("char_count", 0),
            "text": chunk.get("text", "")[:5000],
        }
        point_id = hash(f"lib:{collection}:{book_name}:{global_i}") % (2**63 - 1)
        points.append(qm.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        ))
    response = client.upsert(collection_name=collection, points=points, wait=True)
    if response and hasattr(response, 'status') and response.status != 'ok':
        logger.error(f"Upload failed for batch starting at {global_start_index}: {response}")
    logger.info(f"Uploaded {len(points)} points to {collection} (batch start={global_start_index})")
    return response


def collection_count(client: Optional[QdrantClient] = None, name: str = "") -> int:
    if client is None:
        client = get_client()
    try:
        info = client.get_collection(collection_name=name)
        return info.points_count
    except Exception:
        return 0


def get_stats(client: Optional[QdrantClient] = None) -> dict:
    if client is None:
        client = get_client()
    stats = {}
    for name in COLLECTIONS:
        stats[name] = collection_count(client, name)
    return stats
