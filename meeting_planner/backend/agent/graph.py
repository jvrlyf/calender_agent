from __future__ import annotations

from langgraph.graph import StateGraph, END

from backend.agent.state import AgentState
from backend.agent.nodes import (
    classify_input_node,
    extract_details_node,
    check_completeness_node,
    ask_missing_node,
    present_confirmation_node,
    handle_confirmation_node,
    create_meeting_node,
    general_response_node,
    set_mcp_client,
)
from backend.utils.logger import get_logger

log = get_logger("agent.graph")


# ── routing functions ─────────────────────────────────

def _route_after_classify(state: AgentState) -> str:
    intent = state.get("intent", "general")
    status = state.get("status", "idle")

    if intent == "confirmation" and status == "confirming":
        return "create_meeting"
    if intent == "denial":
        return "general_response"
    if intent in ("new_request", "modification"):
        return "extract_details"
    if intent == "confirmation" and status != "confirming":
        return "general_response"
    return "general_response"


def _route_after_completeness(state: AgentState) -> str:
    return "present_confirmation" if state.get("intent") == "complete" else "ask_missing"


# ── graph builder ─────────────────────────────────────

def build_agent_graph(mcp_client=None):
    """Build and compile the LangGraph agent."""

    if mcp_client is not None:
        set_mcp_client(mcp_client)

    graph = StateGraph(AgentState)

    # add nodes
    graph.add_node("classify_input", classify_input_node)
    graph.add_node("extract_details", extract_details_node)
    graph.add_node("check_completeness", check_completeness_node)
    graph.add_node("ask_missing", ask_missing_node)
    graph.add_node("present_confirmation", present_confirmation_node)
    graph.add_node("create_meeting", create_meeting_node)
    graph.add_node("general_response", general_response_node)

    # entry
    graph.set_entry_point("classify_input")

    # edges
    graph.add_conditional_edges("classify_input", _route_after_classify, {
        "extract_details": "extract_details",
        "create_meeting": "create_meeting",
        "general_response": "general_response",
    })

    graph.add_edge("extract_details", "check_completeness")

    graph.add_conditional_edges("check_completeness", _route_after_completeness, {
        "present_confirmation": "present_confirmation",
        "ask_missing": "ask_missing",
    })

    graph.add_edge("ask_missing", END)
    graph.add_edge("present_confirmation", END)
    graph.add_edge("create_meeting", END)
    graph.add_edge("general_response", END)

    compiled = graph.compile()
    log.info("Agent graph compiled successfully")
    return compiled