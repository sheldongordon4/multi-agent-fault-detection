"""
coordinator.py - the MAFD Coordinator agent graph.

A LangGraph ReAct loop: an Azure OpenAI chat model (the gpt-5.4-mini deployment)
bound to the kb_retrieve tool (SOP RAG over the local vector DB). Detection runs
upstream (the event IsolationForest) and arrives as a trigger, so the coordinator's
only tool is SOP retrieval. The model retrieves SOPs, then emits a single
FaultTicket JSON object (parsed + validated downstream in
coordinator_service._coerce_to_ticket).

The graph is built lazily via build_coordinator_graph() so importing this module
never requires Azure credentials; it is only constructed when Azure is configured
(see coordinator_service.USE_LOCAL_FALLBACK).

"""

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.faults import budget
from app.faults.config import settings

from .tools import kb_retrieve

TOOLS = [kb_retrieve]

# Process-wide client-side throttle: a token bucket that caps how often the
# coordinator may call the LLM, so a burst of anomaly events can't blow the Azure
# quota / student credit. requests_per_second is the steady refill rate;
# max_bucket_size is the allowed burst. Tune to your deployment's RPM limit.
_RATE_LIMITER = InMemoryRateLimiter(
    requests_per_second=settings.LLM_REQUESTS_PER_SECOND,
    check_every_n_seconds=0.1,
    max_bucket_size=settings.LLM_MAX_BUCKET_SIZE,
)


def _make_llm() -> ChatOpenAI:
    """
    Chat model for the coordinator (Azure deployment via config), rate-limited and
    with bounded retries + a request timeout so a slow/failing call can't hang the
    consumer or retry forever.
    """
    return ChatOpenAI(
        base_url=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        rate_limiter=_RATE_LIMITER,
        max_retries=settings.LLM_MAX_RETRIES,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
    )


def build_coordinator_graph():
    """
    Build the ReAct agent graph: coordinator <-> tools until the model stops
    requesting tools, then END.

    Invoke with {"messages": [SystemMessage(...), HumanMessage(...)]}; the final
    state's last message holds the FaultTicket JSON the model produced.
    """
    llm_with_tools = _make_llm().bind_tools(TOOLS)

    def coordinator_node(state: MessagesState) -> dict:
        # Spend one unit of the process endpoint-call budget before every real
        # LLM call. Raises LLMBudgetExceeded (caught by the service, which then
        # uses the local fallback) once the budget is exhausted — so a long
        # ReAct loop can't run past the cap.
        budget.spend()
        # MessagesState's reducer appends, so we return only the new message.
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("coordinator", coordinator_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.set_entry_point("coordinator")
    # tools_condition: last message has tool calls -> "tools"; otherwise -> END.
    graph.add_conditional_edges("coordinator", tools_condition)
    graph.add_edge("tools", "coordinator")
    return graph.compile()
