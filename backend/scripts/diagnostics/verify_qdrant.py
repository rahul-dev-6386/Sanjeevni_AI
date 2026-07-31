import os
import sys
import logging
from typing import Optional

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("verify_qdrant")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
except ImportError:
    logger.error("qdrant-client is not installed. Install with: pip install qdrant-client")
    sys.exit(1)


def connect_qdrant() -> QdrantClient:
    url = settings.QDRANT_URL
    api_key = settings.QDRANT_API_KEY
    logger.info(f"Connecting to Qdrant at {url}")
    client = QdrantClient(url=url, api_key=api_key, check_compatibility=False)
    logger.info("Connected")
    return client


def print_collection_info(client: QdrantClient, collection: str):
    try:
        info = client.get_collection(collection_name=collection)
        config = info.config
        params = config.params
        vectors_config = params.vectors

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"COLLECTION: {collection}")
        logger.info("=" * 60)
        logger.info(f"  Points count:    {info.points_count}")
        logger.info(f"  Dimension:       {vectors_config.size if hasattr(vectors_config, 'size') else 'N/A'}")
        logger.info(f"  Distance:        {vectors_config.distance if hasattr(vectors_config, 'distance') else 'N/A'}")
        logger.info(f"  Status:          {info.status}")
        logger.info(f"  Vectors config:  {vectors_config}")
        logger.info("")

        if info.points_count > 0:
            result = client.scroll(
                collection_name=collection,
                limit=5,
                with_payload=True,
                with_vectors=True,
            )
            points = result[0]
            logger.info(f"Sample points (first {len(points)}):")
            for i, p in enumerate(points):
                logger.info(f"  [{i}] id={p.id}")
                if p.payload:
                    logger.info(f"      payload keys: {list(p.payload.keys())}")
                    logger.info(f"      payload sample: {dict(list(p.payload.items())[:3])}")
                if p.vector:
                    vec = p.vector
                    if isinstance(vec, dict):
                        vec_key = list(vec.keys())[0]
                        v = vec[vec_key]
                    else:
                        v = vec
                    logger.info(f"      vector[:5]: {v[:5]}")
                    logger.info(f"      vector norm: {sum(x*x for x in v)**0.5:.4f}")
        else:
            logger.info("Collection is empty")

    except Exception as e:
        logger.error(f"Could not get collection info: {e}")


def test_search(client: QdrantClient, collection: str, dimension: int):
    logger.info(f"Testing search with random query vector (dim={dimension})...")
    try:
        import numpy as np
        query = np.random.rand(dimension).tolist()
        hits = client.search(
            collection_name=collection,
            query_vector=query,
            limit=3,
        )
        logger.info(f"Search returned {len(hits)} hits:")
        for hit in hits:
            score_info = f"score={hit.score:.4f}"
            payload_preview = ""
            if hit.payload:
                keys = list(hit.payload.keys())[:3]
                vals = [str(hit.payload[k])[:40] for k in keys]
                payload_preview = f", payload: {dict(zip(keys, vals))}"
            logger.info(f"  id={hit.id} {score_info}{payload_preview}")
    except Exception as e:
        logger.error(f"Search test failed: {e}")


def list_all_collections(client: QdrantClient):
    collections = client.get_collections().collections
    logger.info(f"Available collections ({len(collections)}):")
    for c in collections:
        logger.info(f"  - {c.name}")


def verify():
    client = connect_qdrant()

    list_all_collections(client)

    collection = settings.QDRANT_COLLECTION
    print_collection_info(client, collection)

    dimension = settings.EMBEDDING_DIMENSION
    test_search(client, collection, dimension)

    logger.info("")
    logger.info("Verification complete.")


if __name__ == "__main__":
    verify()
