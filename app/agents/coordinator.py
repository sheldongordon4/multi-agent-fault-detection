# app/agents/coordinator.py
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from .tools import detect_signal, kb_retrieve
from app.models.fault_ticket import FaultTicket

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

tools = [detect_signal, kb_retrieve]
llm_with_tools = llm.bind_tools(tools)

def coordinator_node(state):
    # state contains: scenario, bus_id, window_sec, prior_tool_outputs, etc.
    messages = state["messages"]
    result = llm_with_tools.invoke(messages)
    return {"messages": messages + [result]}

def build_coordinator_graph():
    g = StateGraph(dict)
    g.add_node("coordinator", coordinator_node)
    g.set_entry_point("coordinator")
    g.add_edge("coordinator", END)
    return g.compile()

