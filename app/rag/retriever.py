import logging

from .vector_store import get_vectordb

logger = logging.getLogger(__name__)


def kb_retrieve_impl(query: str, k: int = 3) -> list[dict]:
    """
    Retrieve relevant SOP / protection guidelines for a suspected fault.
    Returns list of dicts with keys aligned to KBCitation.

    Degrades gracefully: if the vector DB is unavailable (not built, embedding
    model missing, etc.) it logs and returns [] so a KB hiccup never crashes a
    diagnosis — the coordinator still produces a ticket, just without citations.
    """
    try:
        vectordb = get_vectordb()
        docs = vectordb.similarity_search(query, k=k)
    except Exception:
        logger.exception("kb_retrieve failed; returning no citations")
        return []

    results = []
    for d in docs:
        meta = d.metadata or {}
        results.append(
            {
                "source_id": meta.get("source_id", meta.get("path", "unknown")),
                "title": meta.get("title", "Unknown SOP"),
                "section": meta.get("section"),
                "url": meta.get("url"),
                "snippet": d.page_content[:600],
            }
        )
    return results
