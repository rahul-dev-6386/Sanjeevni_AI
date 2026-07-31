import logging
import os
import pickle
from time import time
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from app.domain.medical_library.embedder import embed_query
from app.domain.medical_library import indexer
from app.domain.medical_library.reranker import rerank
from app.domain.medical_library.query_expander import expand_query

logger = logging.getLogger("medical_library")
logger.setLevel(logging.INFO)


_bm25_indexes: dict[str, tuple[BM25Okapi, list[str]]] = {}
_bm25_payloads: dict[str, list[dict]] = {}
BM25_CACHE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "bm25_cache"
)


def _bm25_cache_path(collection: str) -> str:
    os.makedirs(BM25_CACHE_DIR, exist_ok=True)
    return os.path.join(BM25_CACHE_DIR, f"bm25_{collection}.pkl")


def _load_bm25_from_disk(collection: str) -> tuple[BM25Okapi, list[str], list[dict]]:
    path = _bm25_cache_path(collection)
    if not os.path.exists(path):
        return (None, [], [])
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        logger.info(f"Loaded cached BM25 index for {collection} ({len(data['texts'])} docs)")
        return (data["bm25"], data["texts"], data["payloads"])
    except Exception as e:
        logger.warning(f"Failed to load BM25 cache for {collection}: {e}")
        return (None, [], [])


def _save_bm25_to_disk(
    collection: str, bm25: BM25Okapi, texts: list[str], payloads: list[dict]
):
    path = _bm25_cache_path(collection)
    try:
        with open(path, "wb") as f:
            pickle.dump({"bm25": bm25, "texts": texts, "payloads": payloads}, f)
        logger.info(f"Saved BM25 index for {collection} ({len(texts)} docs) to {path}")
    except Exception as e:
        logger.warning(f"Failed to cache BM25 index for {collection}: {e}")


def _get_bm25_index(collection: str) -> tuple[BM25Okapi, list[str]]:
    global _bm25_indexes, _bm25_payloads
    if collection in _bm25_indexes:
        return _bm25_indexes[collection]

    # Try disk cache first
    bm25, texts, payloads = _load_bm25_from_disk(collection)
    if bm25 is not None:
        _bm25_indexes[collection] = (bm25, texts)
        _bm25_payloads[collection] = payloads
        return (bm25, texts)

    t0 = time()
    client = indexer.get_client()
    try:
        scroll = client.scroll(
            collection_name=collection,
            limit=10000,
            with_payload=["text", "source_book", "chapter", "section", "page_number"],
        )
        texts = []
        payloads = []
        for point in scroll[0]:
            if point.payload and point.payload.get("text"):
                # Skip non-content pages (e.g. TOC, Index)
                if point.payload.get("content_type", "content") != "content":
                    continue
                texts.append(point.payload["text"])
                payloads.append({
                    "collection": collection,
                    "source_book": point.payload.get("source_book", ""),
                    "chapter": point.payload.get("chapter", ""),
                    "section": point.payload.get("section", ""),
                    "page_number": point.payload.get("page_number", ""),
                    "medical_topic": point.payload.get("medical_topic", ""),
                })
    except Exception as e:
        logger.warning(f"Failed to scroll {collection}: {e}")
        texts = []
        payloads = []

    if not texts:
        _bm25_indexes[collection] = (None, [])
        _bm25_payloads[collection] = []
        return (None, [])

    logger.info(f"Building BM25 index for {collection} ({len(texts)} docs)...")
    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    logger.info(
        f"BM25 index for {collection} built in {time() - t0:.1f}s "
        f"({len(texts)} docs)"
    )
    _bm25_indexes[collection] = (bm25, texts)
    _bm25_payloads[collection] = payloads
    # Persist to disk
    _save_bm25_to_disk(collection, bm25, texts, payloads)
    return (bm25, texts)


def _semantic_search(
    query_vec: list[float],
    collection: str,
    top_k: int = 50,
    client=None,
) -> list[dict]:
    from qdrant_client.http import models as qm
    
    if client is None:
        client = indexer.get_client()
    try:
        response = client.query_points(
            collection_name=collection,
            query=query_vec,
            query_filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="content_type",
                        match=qm.MatchValue(value="content")
                    )
                ]
            ),
            limit=top_k,
            with_payload=True,
        )
        hits = response.points
        return [
            {
                "score": round(hit.score, 4),
                "collection": collection,
                "source_book": hit.payload.get("source_book", ""),
                "chapter": hit.payload.get("chapter", ""),
                "section": hit.payload.get("section", ""),
                "page_number": hit.payload.get("page_number", ""),
                "medical_topic": hit.payload.get("medical_topic", ""),
                "text": hit.payload.get("text", ""),
            }
            for hit in hits
        ]
    except Exception as e:
        logger.warning(f"Semantic search failed on {collection}: {e}")
        return []


def _keyword_search(query: str, collection: str, top_k: int = 50) -> list[dict]:
    bm25, texts = _get_bm25_index(collection)
    if bm25 is None or not texts:
        return []

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:top_k]

    payloads = _bm25_payloads.get(collection, [{}] * len(texts))
    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            p = payloads[idx] if idx < len(payloads) else {}
            results.append({
                "score": float(scores[idx]),
                "collection": p.get("collection", collection),
                "source_book": p.get("source_book", ""),
                "chapter": p.get("chapter", ""),
                "section": p.get("section", ""),
                "page_number": p.get("page_number", ""),
                "medical_topic": p.get("medical_topic", ""),
                "text": texts[idx][:5000],
            })
    return results


def _normalize_keyword_score(keyword_results: list[dict]) -> list[dict]:
    if not keyword_results:
        return []
    max_score = max(r["score"] for r in keyword_results)
    if max_score == 0:
        return keyword_results
    for r in keyword_results:
        r["score"] = r["score"] / max_score
    return keyword_results


def hybrid_search(
    query: str,
    collection: Optional[str] = None,
    semantic_top_k: int = 50,
    keyword_top_k: int = 50,
    final_top_k: int = 50,
    alpha: float = 0.7,
) -> list[dict]:
    client = indexer.get_client()
    query_vec = embed_query(query)

    collections = [collection] if collection else indexer.COLLECTIONS

    # Get per-collection results
    per_collection_results: dict[str, list[dict]] = {}
    for coll in collections:
        semantic_results = _semantic_search(query_vec, coll, semantic_top_k, client)
        keyword_results = _keyword_search(query, coll, keyword_top_k)
        keyword_results = _normalize_keyword_score(keyword_results)

        seen_texts = set()
        combined = []

        for r in semantic_results:
            r["hybrid_score"] = alpha * r["score"]
            combined.append(r)
            seen_texts.add(r.get("text", ""))

        for r in keyword_results:
            if r.get("text", "") not in seen_texts:
                r["hybrid_score"] = (1 - alpha) * r["score"]
                combined.append(r)
                seen_texts.add(r.get("text", ""))
            else:
                for existing in combined:
                    if existing.get("text", "") == r.get("text", ""):
                        existing["hybrid_score"] += (1 - alpha) * r["score"]
                        break

        combined.sort(key=lambda x: x["hybrid_score"], reverse=True)
        per_collection_results[coll] = combined

    if collection:
        # Single collection: return top results
        return per_collection_results[collection][:final_top_k]

    # Cross-collection: round-robin interleave to balance across collections
    # Take top results from each collection in turn
    per_coll_k = min(final_top_k, max(3, final_top_k // len(collections)))
    interleaved = []
    collection_queues = {
        coll: results[:per_coll_k] for coll, results in per_collection_results.items()
    }
    collection_indices = {coll: 0 for coll in collections}

    # Round-robin until we have final_top_k or exhaust all
    while len(interleaved) < final_top_k:
        any_remaining = False
        for coll in collections:
            idx = collection_indices[coll]
            if idx < len(collection_queues[coll]):
                interleaved.append(collection_queues[coll][idx])
                collection_indices[coll] = idx + 1
                any_remaining = True
                if len(interleaved) >= final_top_k:
                    break
        if not any_remaining:
            break

    return interleaved[:final_top_k]


def search(
    query: str,
    collection: Optional[str] = None,
    top_k: int = 5,
    use_hybrid: bool = True,
    use_reranker: bool = False,
) -> list[dict]:
    query = expand_query(query)
    if use_hybrid:
        results = hybrid_search(query, collection, final_top_k=50 if use_reranker else top_k)
    else:
        client = indexer.get_client()
        query_vec = embed_query(query)
        collections = [collection] if collection else indexer.COLLECTIONS
        results = []
        for coll in collections:
            results.extend(_semantic_search(query_vec, coll, top_k, client))
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

    if use_reranker and len(results) > 1:
        results = rerank(query, results, top_k=top_k*2)
    else:
        results = results[:top_k*2]

    # Stage 9: Validation
    from app.domain.medical_library.validator import RAGValidator
    validator = RAGValidator(query)
    results = validator.validate_results(results)
    
    return results[:top_k]


def format_citation(result: dict) -> str:
    parts = []
    if result.get("source_book"):
        parts.append(f"Book: {result['source_book']}")
    if result.get("chapter"):
        parts.append(f"Chapter: {result['chapter']}")
    if result.get("section"):
        parts.append(f"Section: {result['section']}")
    if result.get("page_number"):
        parts.append(f"Page: {result['page_number']}")
    return "\n".join(parts)
