"""Nine logical nodes with explicit per-node transitions, one corrective round, and one regeneration."""

from langgraph.graph import END, START, StateGraph

from src.agents.copilot import nodes
from src.agents.copilot.state import CopilotState

NODE_NAMES = (
    "analyze_and_route",
    "plan_queries",
    "retrieve_documents",
    "select_evidence",
    "build_context",
    "generate_answer",
    "check_grounding",
    "finalize_response",
    "fallback_response",
)

NODE_TRANSITIONS: dict[str, dict[str, str]] = {
    "analyze_and_route": {
        "retrieve_documents": "retrieve_documents",
        "plan_queries": "plan_queries",
        "generate_answer": "generate_answer",
        "finalize_response": "finalize_response",
        "fallback_response": "fallback_response",
        "end": END,
    },
    "plan_queries": {
        "retrieve_documents": "retrieve_documents",
        "finalize_response": "finalize_response",
        "fallback_response": "fallback_response",
    },
    "retrieve_documents": {
        "select_evidence": "select_evidence",
        "finalize_response": "finalize_response",
        "fallback_response": "fallback_response",
    },
    "select_evidence": {
        "build_context": "build_context",
        "plan_queries": "plan_queries",
        "finalize_response": "finalize_response",
        "fallback_response": "fallback_response",
    },
    "build_context": {
        "generate_answer": "generate_answer",
        "select_evidence": "select_evidence",
        "plan_queries": "plan_queries",
        "finalize_response": "finalize_response",
        "fallback_response": "fallback_response",
    },
    "generate_answer": {
        "check_grounding": "check_grounding",
        "finalize_response": "finalize_response",
        "fallback_response": "fallback_response",
    },
    "check_grounding": {
        "check_grounding": "check_grounding",
        "finalize_response": "finalize_response",
        "generate_answer": "generate_answer",
        "plan_queries": "plan_queries",
        "select_evidence": "select_evidence",
        "fallback_response": "fallback_response",
    },
    "finalize_response": {
        "end": END,
        "fallback_response": "fallback_response",
    },
    "fallback_response": {
        "end": END,
    },
}


def build_copilot_graph():
    graph = StateGraph(CopilotState)
    for name in NODE_NAMES:
        graph.add_node(name, getattr(nodes, name))
    graph.add_edge(START, "analyze_and_route")
    for name, transitions in NODE_TRANSITIONS.items():
        graph.add_conditional_edges(name, lambda state: state["route"], transitions)
    return graph.compile()


copilot_agent = build_copilot_graph()
