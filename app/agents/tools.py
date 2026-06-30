from langchain_core.tools import tool

from ml.baseline_detector import detect_signal_payload, train_baseline_detector
from app.rag.retriever import kb_retrieve_impl


@tool("detect_signal")
def detect_signal(scenario: str, bus_id: str, window_sec: int = 300) -> dict:
    """Detect anomalies in SCADA/relay signals for the given scenario and bus."""
    # Uses the real IsolationForest detector (ml/baseline_detector) against the
    # SQLite signal store. window_sec is kept for the tool interface; the current
    # detector windows by row count rather than an explicit time window.
    try:
        return detect_signal_payload(scenario, bus_id)
    except FileNotFoundError:
        # Model not trained yet — train the baseline on 'normal' data, then retry.
        train_baseline_detector()
        return detect_signal_payload(scenario, bus_id)

@tool("kb_retrieve")
def kb_retrieve(query: str, k: int = 3) -> list[dict]:
    """
    Retrieve relevant SOP / protection guidelines for a suspected fault.
    The query should mention the suspected fault type and bus or asset.
    """
    return kb_retrieve_impl(query=query, k=k)
