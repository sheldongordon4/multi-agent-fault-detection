# app/rag/retriever.py
from typing import List, Dict
from .vector_store import get_vectordb

def kb_retrieve_impl(query: str, k: int = 3) -> List[Dict]:
    """
    Retrieve relevant SOP / protection guidelines for a suspected fault.
    Returns list of dicts with keys aligned to KBCitation.
    """
    vectordb = get_vectordb()
    docs = vectordb.similarity_search(query, k=k)

    results = []
    for d in docs:
        meta = d.metadata or {}
        results.append({
            "source_id": meta.get("source_id", meta.get("path", "unknown")),
            "title": meta.get("title", "Unknown SOP"),
            "section": meta.get("section"),
            "url": meta.get("url"),
            "snippet": d.page_content[:600],
        })
    return results
