"""
coordinator.py - the MAFD Coordinator agent graph.

A LangGraph ReAct loop: an Azure OpenAI chat model (the gpt-4o-mini deployment)
bound to the real tools - detect_signal (IsolationForest detector over the signal
store) and kb_retrieve (SOP RAG over the local vector DB). The model calls tools
until it has gathered enough evidence, then emits a single FaultTicket JSON object
(parsed + validated downstream in coordinator_service._coerce_to_ticket).

The graph is built lazily via build_coordinator_graph() so importing this module
never requires Azure credentials; it is only constructed when Azure is configured
(see coordinator_service.USE_LOCAL_FALLBACK).

Provider note: AzureChatOpenAI talks to an OpenAI-compatible endpoint, so moving to
a self-hosted open model later (the target architecture) is a configuration change
here, not a rewrite.
"""

import os

from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from .tools import detect_signal, kb_retrieve

TOOLS = [detect_signal, kb_retrieve]


def _make_llm() -> AzureChatOpenAI:
    """Azure OpenAI chat model (gpt-4o-mini deployment), configured from env."""
    return AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        temperature=0,
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
