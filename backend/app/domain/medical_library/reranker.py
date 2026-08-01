import logging
import os
import time
import threading

import httpx

from app.core.config import settings

logger = logging.getLogger("medical_library.reranker")

JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"
JINA_MODEL = "jina-reranker-v2-base-multilingual"

# ── Concurrency guard ─────────────────────────────────────────────────────────
# Jina free tier: max 2 concurrent requests.
# This semaphore queues all callers so we never exceed that limit.
_JINA_SEMAPHORE = threading.BoundedSemaphore(2)

# ── Retry settings ────────────────────────────────────────────────────────────
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 2.0   # seconds; doubles each attempt: 2 → 4 → 8 → 16


def _rerank_via_jina(query: str, results: list[dict], top_k: int) -> list[dict] | None:
    """
    Calls the Jina AI Reranker API (free tier).

    Concurrency-safe: a BoundedSemaphore(2) ensures at most 2 simultaneous
    HTTP calls are in-flight. Extra callers wait their turn rather than
    hammering the API and getting 429 RATE_CONCURRENCY errors.

    On 429 we also do exponential-backoff retries.
    """
    api_key = settings.JINA_API_KEY
    if not api_key:
        return None

    documents = [r.get("text", "") for r in results]
    if not documents:
        return None

    payload = {
        "model": JINA_MODEL,
        "query": query,
        "documents": documents,
        "top_n": top_k,
        "return_documents": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        # Block until a slot opens — guarantees ≤2 concurrent Jina calls
        logger.debug(f"Jina reranker: waiting for semaphore (attempt {attempt})")
        _JINA_SEMAPHORE.acquire()
        semaphore_held = True
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(JINA_RERANK_URL, headers=headers, json=payload)

            if resp.status_code == 429:
                # Respect Retry-After if present, else exponential backoff
                retry_after = float(
                    resp.headers.get("Retry-After", _RETRY_BASE_DELAY * attempt)
                )
                logger.warning(
                    f"Jina reranker 429 (attempt {attempt}/{_MAX_RETRIES}). "
                    f"Sleeping {retry_after:.1f}s before retry…"
                )
                _JINA_SEMAPHORE.release()          # free the slot while we sleep
                semaphore_held = False
                time.sleep(retry_after)
                continue                            # re-acquire and retry

            resp.raise_for_status()
            data = resp.json()

            reranked_results = []
            for item in data.get("results", []):
                idx = item["index"]
                score = item["relevance_score"]
                result = dict(results[idx])
                result["rerank_score"] = float(score)
                reranked_results.append(result)

            logger.info(
                f"Jina reranker ✓ {len(reranked_results)} results "
                f"(model={JINA_MODEL}, attempt={attempt})"
            )
            return reranked_results

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Jina reranker HTTP {e.response.status_code} "
                f"(attempt {attempt}/{_MAX_RETRIES}): {e.response.text[:200]}"
            )
        except Exception as e:
            logger.warning(
                f"Jina reranker error (attempt {attempt}/{_MAX_RETRIES}): {e}"
            )
        finally:
            if semaphore_held:
                _JINA_SEMAPHORE.release()

        if attempt < _MAX_RETRIES:
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.info(f"Jina reranker: retrying in {delay:.1f}s…")
            time.sleep(delay)

    logger.warning("Jina reranker: all retries exhausted — falling back to score sort.")
    return None


def rerank(query: str, results: list[dict], top_k: int = 10) -> list[dict]:
    """
    Re-ranks retrieved chunks by relevance using the Jina AI API.

    Strategy:
      1. Jina API  (free, concurrency-safe, retry on 429)   → best quality
      2. Fallback: sort by hybrid/vector score               → still good
    """
    if not results:
        return []

    if os.getenv("DISABLE_RERANKER") == "1":
        logger.debug("Reranker disabled via DISABLE_RERANKER env var.")
        return results[:top_k]

    reranked = _rerank_via_jina(query, results, top_k)
    if reranked is not None:
        return reranked

    # Fallback: sort by existing score
    logger.info("Reranker fallback: sorting by hybrid/vector score.")
    return sorted(
        results,
        key=lambda r: r.get("hybrid_score", r.get("score", 0)),
        reverse=True,
    )[:top_k]


# Alias used by main.py startup pre-warm.
def _get_direct_reranker():
    if settings.JINA_API_KEY:
        logger.info(f"Reranker: Jina AI API configured (model={JINA_MODEL})")
    else:
        logger.warning(
            "Reranker: JINA_API_KEY not set. "
            "Results will be sorted by vector score only. "
            "Get a free key at https://jina.ai"
        )
    return None
