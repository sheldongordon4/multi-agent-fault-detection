from langchain_core.tools import tool

from app.rag.retriever import kb_retrieve_impl


@tool("kb_retrieve")
def kb_retrieve(query: str, k: int = 3) -> list[dict]:
    """
    Retrieve relevant SOP / protection guidelines for a suspected fault.
    The query should mention the suspected fault type and the affected
    feeder/bus or asset.
    """
    return kb_retrieve_impl(query=query, k=k)
