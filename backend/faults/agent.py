"""
agent.py - the MAFD Coordinator agent graph.

A LangGraph ReAct loop: a chat model (Google AI Studio's Gemini by default — see
backend/faults/config.py) bound to the kb_retrieve tool (SOP RAG over the local
vector DB). Detection runs upstream (the event IsolationForest) and arrives as a
trigger, so the coordinator's only tool is SOP retrieval. The model retrieves
SOPs, then emits a single FaultTicket JSON object (parsed + validated downstream
in faults_service._coerce_to_ticket).

The client comes from build_chat_model(): the native ChatGoogleGenerativeAI for
Google, ChatOpenAI on a configurable base_url for everything else. Google needs
its own class because Gemini 3.x requires a thought_signature echoed back with
each tool result and the OpenAI chat-completions format has no field to carry it
— see the note on build_chat_model below. For every OTHER provider, changing
provider really is a change of endpoint/key/model and nothing else.

The graph is built lazily via build_coordinator_graph() so importing this module
never requires credentials; it is only constructed when an endpoint is configured
(see faults_service.USE_LOCAL_FALLBACK).

"""

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from backend.faults import budget
from backend.faults.config import settings

from .tools import kb_retrieve

TOOLS = [kb_retrieve]

# Process-wide client-side throttle: a token bucket that caps how often the
# coordinator may call the LLM, so a burst of anomaly events can't blow the
# provider's quota — which on a free tier is a per-minute request limit, not a
# bill. requests_per_second is the steady refill rate; max_bucket_size is the
# allowed burst. Tune to your endpoint's RPM limit.
_RATE_LIMITER = InMemoryRateLimiter(
    requests_per_second=settings.LLM_REQUESTS_PER_SECOND,
    check_every_n_seconds=0.1,
    max_bucket_size=settings.LLM_MAX_BUCKET_SIZE,
)


def build_chat_model(
    *,
    max_retries: int,
    max_tokens: int,
    rate_limiter=_RATE_LIMITER,
) -> BaseChatModel:
    """
    Chat model for the coordinator (endpoint/key/model from config), rate-limited
    and with bounded retries + a request timeout so a slow/failing call can't hang
    the consumer or retry forever.

    TWO CLIENTS, ONE CONFIG
    -----------------------
    Google needs its own client; everyone else gets `ChatOpenAI` on a base_url.
    That is not a preference, it is a protocol limit:

    Gemini 3.x attaches an opaque `thought_signature` to every function call and
    requires it echoed back when the tool result is returned, so the model can
    resume its reasoning. The OpenAI chat-completions format has no field to
    carry it - its tool calls are stateless (id, name, arguments). So a single
    call over the compatibility layer SUCCEEDS and a tool LOOP fails on the
    second request:

        400 INVALID_ARGUMENT - Function call is missing a thought_signature in
        functionCall parts ... position 2

    This coordinator is a ReAct loop, so it is always multi-turn. Gemini 2.x
    predates the requirement but is closed to new API projects, so there is no
    older model to fall back to - the native client is the only route.

    Everything else (Azure, OpenRouter, Groq, a self-hosted vLLM or Ollama)
    keeps the OpenAI-compatible path, so `LLM_ENDPOINT` stays the whole story
    for them.
    """
    if settings.resolved_provider == "google":
        # Imported lazily: the OpenAI path must not require this package.
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            google_api_key=settings.LLM_API_KEY,
            rate_limiter=rate_limiter,
            max_retries=max_retries,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_output_tokens=max_tokens,
        )

    return ChatOpenAI(
        base_url=settings.LLM_ENDPOINT,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        rate_limiter=rate_limiter,
        max_retries=max_retries,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_tokens=max_tokens,
    )


def _make_llm() -> BaseChatModel:
    """The coordinator's own client, built from config."""
    return build_chat_model(
        max_retries=settings.LLM_MAX_RETRIES,
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
