"""Migrate vectors from local sources to Qdrant Cloud.

Supports two sources:
  1. FAISS index (System A - VectorStore fallback) — reads index.faiss + id_map.pkl
  2. Local on-disk Qdrant (System B - Medical Library) — reads 4 collections

Usage:
    python scripts/ingestion/migrate_faiss_to_qdrant.py              # all sources
    python scripts/ingestion/migrate_faiss_to_qdrant.py --source faiss
    python scripts/ingestion/migrate_faiss_to_qdrant.py --source local_qdrant
"""

import os
import sys
import time
import pickle
import logging
import argparse

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
    from qdrant_client.http.exceptions import UnexpectedResponse
except ImportError:
    logger.error("Install qdrant-client: pip install qdrant-client")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    logger.error("Install tqdm: pip install tqdm")
    sys.exit(1)


# ── config ──────────────────────────────────────────────────────────────
FAISS_INDEX_DIR = "./data/faiss_index"
LOCAL_QDRANT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "library_qdrant",
)
LIBRARY_COLLECTIONS = ["diseases", "laboratory", "pharmacology", "clinical_practice"]
BATCH_SIZE = 250
MAX_RETRIES = 3
RETRY_DELAY = 2.0


# ── helpers ─────────────────────────────────────────────────────────────
def connect_cloud() -> QdrantClient:
    url = settings.QDRANT_URL
    api_key = settings.QDRANT_API_KEY
    logger.info(f"Connecting to Qdrant Cloud at {url}")
    client = QdrantClient(url=url, api_key=api_key, check_compatibility=False, timeout=60)
    logger.info("Connected")
    return client


def ensure_collection(client: QdrantClient, name: str, dimension: int):
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        info = client.get_collection(name)
        logger.info(f"Collection '{name}' exists: {info.points_count} points, dim={info.config.params.vectors.size}")
        return
    logger.info(f"Creating collection '{name}' (dim={dimension}, distance=Cosine)")
    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
    )


def get_existing_ids(client: QdrantClient, collection: str) -> set:
    ids = set()
    try:
        offset = None
        while True:
            result = client.scroll(collection, limit=1000, offset=offset, with_payload=False, with_vectors=False)
            points, offset = result
            for p in points:
                ids.add(p.id)
            if offset is None or offset == 0:
                break
    except Exception as e:
        logger.warning(f"Could not scroll existing points in '{collection}': {e}")
    return ids


def upload_batch(client: QdrantClient, collection: str, batch: list[qm.PointStruct]) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client.upsert(collection_name=collection, points=batch, wait=True)
            return True
        except Exception as e:
            logger.warning(f"Upload attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return False


def verify_count(client: QdrantClient, collection: str, expected: int) -> bool:
    try:
        info = client.get_collection(collection)
        actual = info.points_count
        ok = actual == expected
        status = "PASS" if ok else "MISMATCH"
        logger.info(f"  Verify '{collection}': {status} (cloud={actual}, expected={expected})")
        return ok
    except Exception as e:
        logger.error(f"  Verify '{collection}' failed: {e}")
        return False


# ── source: FAISS ───────────────────────────────────────────────────────
def migrate_from_faiss(cloud: QdrantClient):
    index_file = os.path.join(FAISS_INDEX_DIR, "index.faiss")
    map_file = os.path.join(FAISS_INDEX_DIR, "id_map.pkl")

    if not os.path.exists(index_file) or not os.path.exists(map_file):
        logger.info("FAISS index not found — nothing to migrate from FAISS")
        return 0, 0

    import faiss

    logger.info(f"Reading FAISS index from {index_file}")
    index = faiss.read_index(index_file)
    n_total = index.ntotal
    with open(map_file, "rb") as f:
        id_map = pickle.load(f)
    logger.info(f"FAISS: {n_total} vectors, dim={index.d}, {len(id_map)} id_map entries")

    vectors = []
    for fid in range(n_total):
        vec = index.reconstruct(fid)
        entry = id_map.get(fid)
        if entry is None:
            continue
        vectors.append({
            "embedding_id": entry["id"],
            "vector": vec.tolist(),
            "payload": entry.get("payload", {}),
        })

    collection = settings.QDRANT_COLLECTION
    ensure_collection(cloud, collection, index.d)
    existing_ids = get_existing_ids(cloud, collection)

    to_upload = []
    skipped = 0
    for v in vectors:
        pid = hash(v["embedding_id"]) % (2**63 - 1)
        if pid in existing_ids:
            skipped += 1
        else:
            to_upload.append(v)

    logger.info(f"FAISS → Cloud '{collection}': total={len(vectors)}, skip={skipped}, upload={len(to_upload)}")
    return _do_upload(cloud, collection, to_upload, skipped), len(vectors)


# ── source: local Qdrant ────────────────────────────────────────────────
def migrate_from_local_qdrant(cloud: QdrantClient):
    if not os.path.isdir(LOCAL_QDRANT_DIR):
        logger.info(f"Local Qdrant not found at {LOCAL_QDRANT_DIR} — skipping")
        return 0, 0

    logger.info(f"Opening local Qdrant at {LOCAL_QDRANT_DIR}")
    local = QdrantClient(path=LOCAL_QDRANT_DIR)

    total_found = 0
    total_uploaded = 0

    for coll in LIBRARY_COLLECTIONS:
        try:
            info = local.get_collection(coll)
            n_local = info.points_count
            dim = info.config.params.vectors.size if hasattr(info.config.params, 'vectors') else 1024
        except Exception:
            logger.warning(f"Local collection '{coll}' not found, skipping")
            continue

        if n_local == 0:
            logger.info(f"Local '{coll}' is empty, skipping")
            continue

        logger.info(f"Reading {n_local} vectors from local '{coll}' (dim={dim})")
        offset = None
        points_data = []
        with tqdm(total=n_local, desc=f"  Scroll {coll}", unit="vec") as pbar:
            while True:
                result = local.scroll(coll, limit=500, offset=offset, with_payload=True, with_vectors=True)
                pts, offset = result
                for p in pts:
                    vec = p.vector
                    if isinstance(vec, dict):
                        vec = list(vec.values())[0]
                    points_data.append({
                        "id": p.id,
                        "vector": vec,
                        "payload": p.payload or {},
                    })
                pbar.update(len(pts))
                if offset is None or offset == 0:
                    break

        total_found += len(points_data)
        ensure_collection(cloud, coll, dim)
        existing_ids = get_existing_ids(cloud, coll)

        to_upload = []
        skipped = 0
        for p in points_data:
            if p["id"] in existing_ids:
                skipped += 1
            else:
                to_upload.append(p)

        logger.info(f"  Local '{coll}' → Cloud '{coll}': total={len(points_data)}, skip={skipped}, upload={len(to_upload)}")

        batch_points = []
        for p in to_upload:
            batch_points.append(qm.PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p["payload"],
            ))

        uploaded = 0
        for i in range(0, len(batch_points), BATCH_SIZE):
            batch = batch_points[i : i + BATCH_SIZE]
            if upload_batch(cloud, coll, batch):
                uploaded += len(batch)
            tqdm.write(f"  Upload '{coll}': {uploaded}/{len(batch_points)}")

        total_uploaded += uploaded
        verify_count(cloud, coll, len(points_data))

    local.close()
    return total_uploaded, total_found


def _do_upload(cloud: QdrantClient, collection: str, to_upload: list, skipped: int) -> int:
    if not to_upload:
        return 0

    batch_points = []
    for v in to_upload:
        pid = hash(v["embedding_id"]) % (2**63 - 1)
        batch_points.append(qm.PointStruct(id=pid, vector=v["vector"], payload=v["payload"]))

    uploaded = 0
    for i in range(0, len(batch_points), BATCH_SIZE):
        batch = batch_points[i : i + BATCH_SIZE]
        if upload_batch(cloud, collection, batch):
            uploaded += len(batch)
        tqdm.write(f"  Upload '{collection}': {uploaded}/{len(batch_points)}")
    return uploaded


# ── main ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Migrate vectors to Qdrant Cloud")
    parser.add_argument("--source", choices=["faiss", "local_qdrant", "all"], default="all")
    args = parser.parse_args()

    start = time.time()
    cloud = connect_cloud()

    total_uploaded = 0
    total_found = 0

    if args.source in ("faiss", "all"):
        logger.info("\n═══════════════════════════════════════")
        logger.info("Source: FAISS index")
        logger.info("═══════════════════════════════════════")
        u, f = migrate_from_faiss(cloud)
        total_uploaded += u
        total_found += f

    if args.source in ("local_qdrant", "all"):
        logger.info("\n═══════════════════════════════════════")
        logger.info("Source: Local on-disk Qdrant (Medical Library)")
        logger.info("═══════════════════════════════════════")
        u, f = migrate_from_local_qdrant(cloud)
        total_uploaded += u
        total_found += f

    elapsed = time.time() - start

    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Vectors found:     {total_found}")
    logger.info(f"  Vectors uploaded:  {total_uploaded}")
    logger.info(f"  Vectors skipped:   {total_found - total_uploaded}")
    logger.info(f"  Upload time:       {elapsed:.1f}s")

    if total_found == 0:
        logger.info("  Result: NOTHING TO MIGRATE")
    elif total_uploaded == total_found:
        logger.info("  Result: PASS")
    else:
        logger.info("  Result: PARTIAL — re-run to upload remaining")
        sys.exit(1)


if __name__ == "__main__":
    main()
