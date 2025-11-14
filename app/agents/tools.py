# app/agents/tools.py
from langchain_core.tools import tool
from app.services.detection_service import detect_signal_impl
from app.rag.retriever import kb_retrieve_impl

@tool("detect_signal")
def detect_signal(scenario: str, bus_id: str, window_sec: int = 300) -> dict:
    """Detect anomalies in SCADA/relay signals for the given scenario and bus."""
    return detect_signal_impl(scenario, bus_id, window_sec)

@tool("kb_retrieve")
def kb_retrieve(query: str, k: int = 3) -> list[dict]:
    """
    Retrieve relevant SOP / protection guidelines for a suspected fault.
    The query should mention the suspected fault type and bus or asset.
    """
    return kb_retrieve_impl(query=query, k=k)
