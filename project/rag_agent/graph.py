from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode
from functools import partial

from .graph_state import State
from .nodes import *
from .edges import *

def create_agent_graph(llm, tools_list):
    llm_with_tools = llm.bind_tools(tools_list,parallel_tool_calls=False)
    tool_node = ToolNode(tools_list)

    checkpointer = InMemorySaver()

    print("Compiling agent graph...")
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("orchestrator", partial(orchestrator, llm_with_tools=llm_with_tools))
    agent_builder.add_node("tools", tool_node)
    agent_builder.add_node(
        "grade_retrieval",
        partial(grade_retrieval, llm=llm),
        destinations=("should_compress_context", "orchestrator", "fallback_response"),
    )
    agent_builder.add_node("compress_context", partial(compress_context, llm=llm))
    agent_builder.add_node("fallback_response", partial(fallback_response, llm=llm))
    agent_builder.add_node(
        should_compress_context,
        destinations=("compress_context", "orchestrator"),
    )
    agent_builder.add_node(collect_answer)

    agent_builder.add_edge(START, "orchestrator")
    agent_builder.add_conditional_edges("orchestrator", route_after_orchestrator_call, {"tools": "tools", "fallback_response": "fallback_response", "collect_answer": "collect_answer"})
    agent_builder.add_edge("tools", "grade_retrieval")
    agent_builder.add_edge("compress_context", "orchestrator")
    agent_builder.add_edge("fallback_response", "collect_answer")
    agent_builder.add_edge("collect_answer", END)

    agent_subgraph = agent_builder.compile()

    graph_builder = StateGraph(State)
    graph_builder.add_node("chat_router", partial(chat_router, llm=llm))
    graph_builder.add_node("direct_chat", partial(direct_chat, llm=llm))
    graph_builder.add_node(document_inventory)
    graph_builder.add_node(empty_documents_response)
    graph_builder.add_node(router_clarification)
    graph_builder.add_node("document_library_overview", partial(document_library_overview, llm=llm))
    graph_builder.add_node("summarize_history", partial(summarize_history, llm=llm))
    graph_builder.add_node("rewrite_query", partial(rewrite_query, llm=llm))
    graph_builder.add_node(request_clarification)
    graph_builder.add_node("agent", agent_subgraph)
    graph_builder.add_node("aggregate_answers", partial(aggregate_answers, llm=llm))

    graph_builder.add_edge(START, "chat_router")
    graph_builder.add_conditional_edges("chat_router", route_after_chat_router)
    graph_builder.add_edge("direct_chat", END)
    graph_builder.add_edge("document_inventory", END)
    graph_builder.add_edge("empty_documents_response", END)
    graph_builder.add_edge("router_clarification", END)
    graph_builder.add_edge("document_library_overview", END)
    graph_builder.add_edge("summarize_history", "rewrite_query")
    graph_builder.add_conditional_edges("rewrite_query", route_after_rewrite)
    graph_builder.add_edge("request_clarification", "rewrite_query")
    graph_builder.add_edge(["agent"], "aggregate_answers")
    graph_builder.add_edge("aggregate_answers", END)

    agent_graph = graph_builder.compile(checkpointer=checkpointer, interrupt_before=["request_clarification"])

    print("✓ Agent graph compiled successfully.")
    return agent_graph
