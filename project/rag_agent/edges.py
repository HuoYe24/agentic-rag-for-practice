from typing import Literal
from langgraph.types import Send
from .graph_state import State, AgentState
from config import MAX_ITERATIONS, MAX_TOOL_CALLS

def route_after_chat_router(
    state: State,
) -> Literal[
    "direct_chat",
    "document_inventory",
    "document_library_overview",
    "empty_documents_response",
    "router_clarification",
    "summarize_history",
]:
    route = state.get("chat_route", "document_qa")
    current_documents = state.get("current_documents", [])

    if route == "general_chat":
        return "direct_chat"
    if route == "document_inventory":
        return "document_inventory"
    if route == "needs_clarification":
        return "router_clarification"
    if route in {"document_library_overview", "document_qa"} and not current_documents:
        return "empty_documents_response"
    if route == "document_library_overview":
        return "document_library_overview"
    return "summarize_history"

def route_after_rewrite(state: State) -> Literal["request_clarification", "agent"]:
    if not state.get("questionIsClear", False):
        return "request_clarification"
    else:
        return [
                Send("agent", {"question": query, "question_index": idx, "messages": []})
                for idx, query in enumerate(state["rewrittenQuestions"])
            ]
    
def route_after_orchestrator_call(state: AgentState) -> Literal["tools", "fallback_response", "collect_answer"]:
    iteration = state.get("iteration_count", 0)
    tool_count = state.get("tool_call_count", 0)

    if iteration >= MAX_ITERATIONS or tool_count > MAX_TOOL_CALLS:
        return "fallback_response"

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []

    if not tool_calls:
        return "collect_answer"
    
    return "tools"
