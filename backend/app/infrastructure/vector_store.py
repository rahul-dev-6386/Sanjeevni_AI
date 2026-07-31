import logging
import time
from typing import Optional

from app.core.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

logger = logging.getLogger("vector_store")

RETRY_MAX = 3
RETRY_DELAY = 1.0


class VectorStore:
    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
        self.collection = settings.QDRANT_COLLECTION
        self.client: Optional[QdrantClient] = None
        self._initialized = False

    def initialize(self):
        if self._initialized and self.client:
            return
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            check_compatibility=False,
            timeout=30,
        )
        self._ensure_collection()
        self._initialized = True
        logger.info(
            f"VectorStore initialized: backend=qdrant, "
            f"collection={self.collection}, dimension={self.dimension}"
        )

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        names = [c.name for c in collections]
        if self.collection not in names:
            logger.info(
                f"Creating Qdrant collection '{self.collection}' "
                f"(dim={self.dimension}, distance=Cosine)"
            )
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(
                    size=self.dimension,
                    distance=qm.Distance.COSINE,
                ),
            )
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name="type",
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name="user_id",
                    field_schema=qm.PayloadSchemaType.INTEGER,
                )
            except Exception as e:
                logger.warning(f"Failed to create payload index: {e}")

    def _point_id(self, embedding_id: str) -> int:
        return hash(embedding_id) % (2**63 - 1)

    def upsert(self, embedding_id: str, embedding: list[float], payload: dict = None):
        if not self._initialized:
            self.initialize()

        point = qm.PointStruct(
            id=self._point_id(embedding_id),
            vector=embedding,
            payload=payload or {},
        )

        for attempt in range(1, RETRY_MAX + 1):
            try:
                self.client.upsert(
                    collection_name=self.collection,
                    points=[point],
                    wait=True,
                )
                return
            except Exception as e:
                logger.warning(
                    f"upsert attempt {attempt}/{RETRY_MAX} failed "
                    f"for {embedding_id}: {e}"
                )
                if attempt < RETRY_MAX:
                    time.sleep(RETRY_DELAY * attempt)
                else:
                    logger.error(f"upsert failed for {embedding_id} after {RETRY_MAX} retries")
                    raise

    def search(self, query_embedding: list[float], top_k: int = 5, payload_filter: Optional[dict] = None) -> list[dict]:
        if not self._initialized:
            self.initialize()

        try:
            qfilter = None
            if payload_filter:
                must = [
                    qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                    for k, v in payload_filter.items()
                ]
                qfilter = qm.Filter(must=must)

            results = self.client.query_points(
                collection_name=self.collection,
                query=query_embedding,
                limit=top_k,
                query_filter=qfilter,
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                }
                for hit in results.points
            ]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def delete_collection(self):
        if not self._initialized:
            return
        try:
            self.client.delete_collection(collection_name=self.collection)
            logger.info(f"Collection '{self.collection}' deleted")
        except Exception as e:
            logger.warning(f"Could not delete collection: {e}")
        self._initialized = False

    def get_status(self) -> dict:
        if not self._initialized:
            self.initialize()
        try:
            info = self.client.get_collection(collection_name=self.collection)
            return {
                "backend": "qdrant",
                "url": settings.QDRANT_URL,
                "collection": self.collection,
                "points_count": info.points_count,
                "dimension": self.dimension,
                "status": str(info.status),
            }
        except Exception as e:
            logger.warning(f"Could not get collection status: {e}")
            return {
                "backend": "qdrant",
                "url": settings.QDRANT_URL,
                "collection": self.collection,
                "points_count": 0,
                "dimension": self.dimension,
                "status": f"error: {e}",
            }


vector_store = VectorStore()
