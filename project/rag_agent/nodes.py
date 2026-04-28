from typing import Literal, Set
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, AIMessage, ToolMessage
from langgraph.types import Command
from .graph_state import State, AgentState
from .schemas import QueryAnalysis
from .prompts import *
from utils import estimate_context_tokens
from config import BASE_TOKEN_THRESHOLD, TOKEN_GROWTH_FACTOR, CRAG_MAX_RETRIES

def _parse_json_response(text):
    import json
    import re

    match = re.search(r"\{.*\}", str(text or ""), re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        return None

def _history_for_prompt(history, limit=8):
    recent_items = []
    for item in history[-limit:]:
        if not isinstance(item, dict):
            continue
        if item.get("metadata"):
            continue
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if content and role in {"user", "assistant"}:
            recent_items.append((role, content))
    if not recent_items:
        return "(empty)"
    return "\n".join(f"{role}: {content}" for role, content in recent_items)

def _latest_tool_outputs(messages, limit=3, max_chars=1600):
    latest_outputs = []
    collecting = False

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            collecting = True
            content = str(msg.content or "").strip()
            latest_outputs.append(
                f"Tool: {getattr(msg, 'name', 'tool')}\nOutput:\n{content[:max_chars]}"
            )
            if len(latest_outputs) >= limit:
                break
            continue

        if collecting and isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            break

    return list(reversed(latest_outputs))

def _make_retrieval_grade_message(grade, reason):
    import json
    return AIMessage(content=json.dumps({"grade": grade, "reason": reason}, ensure_ascii=False))

def _is_retrieval_grade_message(message):
    if not isinstance(message, AIMessage) or getattr(message, "tool_calls", None):
        return False
    data = _parse_json_response(getattr(message, "content", ""))
    return isinstance(data, dict) and "grade" in data and "reason" in data

def _reasoning_messages(messages):
    return [message for message in messages if not _is_retrieval_grade_message(message)]

def _fallback_route(message):
    normalized = " ".join((message or "").strip().lower().split())
    overview_markers = [
        "每篇文档讲了什么",
        "每个文档讲了什么",
        "每篇讲了什么",
        "每个文档是什么",
        "每篇论文讲了什么",
        "概述每篇文档",
        "总结每篇文档",
        "summarize each",
        "what each document is about",
        "overview of each",
    ]
    inventory_markers = [
        "当前文档库有哪些文档",
        "当前文档库中有哪些文档",
        "文档库有哪些文档",
        "文档库里有哪些文档",
        "当前文档库中有文档吗",
        "当前文档库里有文档吗",
        "文档库中有文档吗",
        "文档库里有文档吗",
        "列出当前文档库",
        "列出文档库",
        "列出所有文档",
        "列出全部文档",
        "文档清单",
        "文档列表",
        "当前有哪些文档",
        "当前有哪些文件",
        "what documents",
        "which documents",
        "list documents",
        "document list",
    ]
    document_question_markers = [
        "文档库",
        "当前文档库",
        "查阅文档库",
        "查一下文档库",
        "查阅当前文档库",
        "检索文档库",
        "搜索文档库",
        "请你查阅文档库",
        "请查阅文档库",
        "请只根据当前文档库回答",
        "请根据当前文档库回答",
        "请查阅文档",
        "查阅文档",
        "根据文档",
        "根据论文",
        "文档中",
        "论文中",
        "这份文档",
        "这篇论文",
        "这些文档",
        "上传的文档",
        "知识库",
        ".pdf",
        ".md",
        "pdf",
        "markdown",
    ]

    if any(marker in normalized for marker in overview_markers):
        return {"route": "document_library_overview", "clarification_message": ""}
    if any(marker in normalized for marker in inventory_markers):
        return {"route": "document_inventory", "clarification_message": ""}
    if any(marker in normalized for marker in document_question_markers):
        return {"route": "document_qa", "clarification_message": ""}
    return {"route": "general_chat", "clarification_message": ""}

def chat_router(state: State, llm):
    last_message = state["messages"][-1]
    message = str(getattr(last_message, "content", "") or "")
    current_documents = state.get("current_documents", [])
    fallback = _fallback_route(message)

    router_messages = [
        SystemMessage(content=get_chat_router_prompt()),
        HumanMessage(
            content=(
                f"current_documents: {current_documents}\n"
                f"recent_history:\n{_history_for_prompt(state.get('recent_history', []))}\n\n"
                f"current_query: {message.strip()}"
            )
        ),
    ]

    try:
        result = llm.invoke(router_messages)
        data = _parse_json_response(getattr(result, "content", result))
        route = str((data or {}).get("route") or "").strip()
        clarification_message = str((data or {}).get("clarification_message") or "").strip()
        allowed_routes = {
            "general_chat",
            "document_inventory",
            "document_library_overview",
            "document_qa",
            "needs_clarification",
        }
        if route not in allowed_routes:
            route = fallback["route"]
            clarification_message = fallback["clarification_message"]
        if route == "general_chat" and fallback.get("route") != "general_chat":
            route = fallback["route"]
            clarification_message = fallback["clarification_message"]
        return {"chat_route": route, "clarification_message": clarification_message}
    except Exception:
        return {
            "chat_route": fallback["route"],
            "clarification_message": fallback["clarification_message"],
        }

def direct_chat(state: State, llm):
    last_message = state["messages"][-1]
    messages = [
        SystemMessage(
            content=(
                "You are a helpful assistant. "
                "Answer the user's message directly and naturally. "
                "Do not claim to have searched documents unless the user explicitly asks about documents. "
                "If you were not given retrieved document context in this route, never invent document-based facts, "
                "never fabricate file names or Sources sections, and never pretend you verified the current document library."
            )
        )
    ]
    for role, content in [
        (item.get("role"), str(item.get("content") or "").strip())
        for item in state.get("recent_history", [])
        if isinstance(item, dict) and not item.get("metadata")
    ][-8:]:
        if not content or role not in {"user", "assistant"}:
            continue
        messages.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
    messages.append(HumanMessage(content=str(last_message.content).strip()))
    response = llm.invoke(messages)
    return {"messages": [response]}

def document_inventory(state: State):
    documents = state.get("current_documents", [])
    if not documents:
        content = (
            "当前文档库为空，没有可列出的文档。\n\n"
            "请先进入 Documents 页面上传至少一个 PDF 或 Markdown 文档。"
        )
    else:
        lines = [f"当前文档库中共有 {len(documents)} 个文档：", ""]
        lines.extend(f"- {name}" for name in documents)
        content = "\n".join(lines)
    return {"messages": [AIMessage(content=content)]}

def empty_documents_response(state: State):
    return {
        "messages": [
            AIMessage(
                content=(
                    "当前文档库为空，无法执行文档检索。\n\n"
                    "请先进入 Documents 页面上传至少一个 PDF 或 Markdown 文档，然后再继续提问。"
                )
            )
        ]
    }

def router_clarification(state: State):
    clarification = state.get("clarification_message", "").strip()
    if not clarification:
        clarification = "请再具体说明一下你想让我做什么。"
    return {"messages": [AIMessage(content=clarification)]}

def document_library_overview(state: State, llm):
    last_message = state["messages"][-1]
    document_previews = state.get("document_previews", [])
    payload = {
        "current_documents": [item["name"] for item in document_previews],
        "document_previews": document_previews,
        "recent_history": _history_for_prompt(state.get("recent_history", [])),
        "user_request": str(last_message.content).strip(),
    }
    import json
    response = llm.invoke([
        SystemMessage(content=get_document_library_overview_prompt()),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
    ])
    return {"messages": [response]}

def summarize_history(state: State, llm):
    if len(state["messages"]) < 4:
        return {"conversation_summary": ""}
    
    relevant_msgs = [
        msg for msg in state["messages"][:-1]
        if isinstance(msg, (HumanMessage, AIMessage)) and not getattr(msg, "tool_calls", None)
    ]

    if not relevant_msgs:
        return {"conversation_summary": ""}
    
    conversation = "Conversation history:\n"
    for msg in relevant_msgs[-6:]:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        conversation += f"{role}: {msg.content}\n"

    summary_response = llm.with_config(temperature=0.2).invoke([SystemMessage(content=get_conversation_summary_prompt()), HumanMessage(content=conversation)])
    return {"conversation_summary": summary_response.content, "agent_answers": [{"__reset__": True}]}

# def rewrite_query(state: State, llm):
#     last_message = state["messages"][-1]
#     conversation_summary = state.get("conversation_summary", "")

#     context_section = (f"Conversation Context:\n{conversation_summary}\n" if conversation_summary.strip() else "") + f"User Query:\n{last_message.content}\n"

#     llm_with_structure = llm.with_config(temperature=0.1).with_structured_output(QueryAnalysis)
#     response = llm_with_structure.invoke([SystemMessage(content=get_rewrite_query_prompt()), HumanMessage(content=context_section)])

#     if response.questions and response.is_clear:
#         delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
#         return {"questionIsClear": True, "messages": delete_all, "originalQuery": last_message.content, "rewrittenQuestions": response.questions}

#     clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 10 else "I need more information to understand your question."
#     return {"questionIsClear": False, "messages": [AIMessage(content=clarification)]}

def rewrite_query(state: State, llm):
    last_message = state["messages"][-1]
    conversation_summary = state.get("conversation_summary", "")
    recent_history = _history_for_prompt(state.get("recent_history", []))

    context_section = (
        f"Conversation Context:\n{conversation_summary}\n" 
        if conversation_summary.strip() 
        else ""
    )
    if recent_history != "(empty)":
        context_section += f"Recent Chat History:\n{recent_history}\n"
    context_section += f"User Query:\n{last_message.content}\n"

    # 修改 Prompt，要求直接返回 JSON
    system_prompt = get_rewrite_query_prompt() + """

Output format (return ONLY valid JSON, no extra text):
{
    "questions": ["rewritten query 1", "rewritten query 2"],
    "is_clear": true,
    "clarification_needed": ""
}

If unclear, set is_clear to false and provide clarification_needed.
"""

    # 用普通调用替代 with_structured_output
    response = llm.with_config(temperature=0.1).invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context_section)
    ])

    # 手动解析 JSON
    import json
    try:
        # 提取 JSON（可能包含 markdown 代码块）
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        parsed = json.loads(content)
        
        if parsed.get("questions") and parsed.get("is_clear"):
            delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
            return {
                "questionIsClear": True,
                "messages": delete_all,
                "originalQuery": last_message.content,
                "rewrittenQuestions": parsed["questions"]
            }
    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        print(f"Warning: Failed to parse query rewrite response: {e}")
        # 降级：直接用原查询
        delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": last_message.content,
            "rewrittenQuestions": [last_message.content]
        }

    clarification = parsed.get("clarification_needed", "").strip()
    if not clarification or len(clarification) < 10:
        clarification = "I need more information to understand your question."
    
    return {"questionIsClear": False, "messages": [AIMessage(content=clarification)]}

def request_clarification(state: State):
    return {}

# --- Agent Nodes ---
def orchestrator(state: AgentState, llm_with_tools):
    context_summary = state.get("context_summary", "").strip()
    retrieval_feedback = state.get("retrieval_feedback", "").strip()
    messages = _reasoning_messages(state.get("messages", []))
    sys_msg = SystemMessage(content=get_orchestrator_prompt())
    summary_injection = (
        [HumanMessage(content=f"[COMPRESSED CONTEXT FROM PRIOR RESEARCH]\n\n{context_summary}")]
        if context_summary else []
    )
    feedback_injection = (
        [HumanMessage(content=f"[RETRIEVAL QUALITY FEEDBACK]\n\n{retrieval_feedback}")]
        if retrieval_feedback else []
    )
    if not messages:
        human_msg = HumanMessage(content=state["question"])
        force_search = HumanMessage(content="YOU MUST CALL 'search_child_chunks' AS THE FIRST STEP TO ANSWER THIS QUESTION.")
        response = llm_with_tools.invoke([sys_msg] + feedback_injection + summary_injection + [human_msg, force_search])
        return {"messages": [human_msg, response], "tool_call_count": len(response.tool_calls or []), "iteration_count": 1}

    response = llm_with_tools.invoke([sys_msg] + feedback_injection + summary_injection + messages)
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    return {"messages": [response], "tool_call_count": len(tool_calls) if tool_calls else 0, "iteration_count": 1}

def fallback_response(state: AgentState, llm):
    seen = set()
    unique_contents = []
    for m in state["messages"]:
        if isinstance(m, ToolMessage) and m.content not in seen:
            unique_contents.append(m.content)
            seen.add(m.content)

    context_summary = state.get("context_summary", "").strip()

    context_parts = []
    if context_summary:
        context_parts.append(f"## Compressed Research Context (from prior iterations)\n\n{context_summary}")
    if unique_contents:
        context_parts.append(
            "## Retrieved Data (current iteration)\n\n" +
            "\n\n".join(f"--- DATA SOURCE {i} ---\n{content}" for i, content in enumerate(unique_contents, 1))
        )

    context_text = "\n\n".join(context_parts) if context_parts else "No data was retrieved from the documents."

    prompt_content = (
        f"USER QUERY: {state.get('question')}\n\n"
        f"{context_text}\n\n"
        f"INSTRUCTION:\nProvide the best possible answer using only the data above."
    )
    response = llm.invoke([SystemMessage(content=get_fallback_response_prompt()), HumanMessage(content=prompt_content)])
    return {"messages": [response]}

def grade_retrieval(state: AgentState, llm) -> Command[Literal["should_compress_context", "orchestrator", "fallback_response"]]:
    latest_outputs = _latest_tool_outputs(state.get("messages", []))
    retry_count = int(state.get("retrieval_retry_count", 0) or 0)

    if not latest_outputs:
        return Command(
            update={
                "messages": [_make_retrieval_grade_message("unknown", "No retrieval outputs were available to grade.")],
                "retrieval_grade": "unknown",
                "retrieval_feedback": "",
                "retrieval_retry_count": retry_count,
            },
            goto="orchestrator",
        )

    combined_outputs = "\n\n".join(latest_outputs)
    upper_outputs = combined_outputs.upper()
    if "NO_RELEVANT_CHUNKS" in upper_outputs or "RETRIEVAL_ERROR" in upper_outputs:
        next_retry_count = retry_count + 1
        if next_retry_count > CRAG_MAX_RETRIES:
            return Command(
                update={
                    "messages": [_make_retrieval_grade_message("insufficient", "Retrieval quality remained insufficient after the maximum CRAG retry limit.")],
                    "retrieval_grade": "insufficient",
                    "retrieval_feedback": "Retrieval quality remained insufficient after the maximum CRAG retry limit.",
                    "retrieval_retry_count": next_retry_count,
                },
                goto="fallback_response",
            )
        return Command(
            update={
                "messages": [_make_retrieval_grade_message("insufficient", "Latest retrieval did not produce sufficiently relevant evidence. Broaden or reformulate the search before answering.")],
                "retrieval_grade": "insufficient",
                "retrieval_feedback": "Latest retrieval did not produce sufficiently relevant evidence. Broaden or reformulate the search before answering.",
                "retrieval_retry_count": next_retry_count,
            },
            goto="orchestrator",
        )

    grading_prompt = (
        f"User question:\n{state.get('question', '').strip()}\n\n"
        f"Latest retrieval outputs:\n{combined_outputs}"
    )

    try:
        response = llm.with_config(temperature=0).invoke([
            SystemMessage(content=get_retrieval_grading_prompt()),
            HumanMessage(content=grading_prompt),
        ])
        parsed = _parse_json_response(getattr(response, "content", response)) or {}
        grade = str(parsed.get("grade", "")).strip().lower()
        reason = str(parsed.get("reason", "")).strip()
    except Exception:
        grade = "unknown"
        reason = ""

    if grade == "sufficient":
        return Command(
            update={
                "messages": [_make_retrieval_grade_message("sufficient", reason or "The latest retrieval results are relevant enough to continue.")],
                "retrieval_grade": "sufficient",
                "retrieval_feedback": "",
                "retrieval_retry_count": 0,
            },
            goto="should_compress_context",
        )

    next_retry_count = retry_count + 1
    if next_retry_count > CRAG_MAX_RETRIES:
        return Command(
            update={
                "messages": [_make_retrieval_grade_message("insufficient", reason or "Retrieval quality remained insufficient after the maximum CRAG retry limit.")],
                "retrieval_grade": "insufficient",
                "retrieval_feedback": reason or "Retrieval quality remained insufficient after the maximum CRAG retry limit.",
                "retrieval_retry_count": next_retry_count,
            },
            goto="fallback_response",
        )

    feedback = reason or "Latest retrieval is not strong enough to answer confidently. Search again with a better-focused query."
    return Command(
        update={
            "messages": [_make_retrieval_grade_message("insufficient", feedback)],
            "retrieval_grade": "insufficient",
            "retrieval_feedback": feedback,
            "retrieval_retry_count": next_retry_count,
        },
        goto="orchestrator",
    )

def should_compress_context(state: AgentState) -> Command[Literal["compress_context", "orchestrator"]]:
    messages = state["messages"]
    reasoning_messages = _reasoning_messages(messages)

    new_ids: Set[str] = set()
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if tc["name"] == "retrieve_parent_chunks":
                    raw = tc["args"].get("parent_id") or tc["args"].get("id") or tc["args"].get("ids") or []
                    if isinstance(raw, str):
                        new_ids.add(f"parent::{raw}")
                    else:
                        new_ids.update(f"parent::{r}" for r in raw)

                elif tc["name"] == "search_child_chunks":
                    query = tc["args"].get("query", "")
                    if query:
                        new_ids.add(f"search::{query}")
            break

    updated_ids = state.get("retrieval_keys", set()) | new_ids

    current_token_messages = estimate_context_tokens(reasoning_messages)
    current_token_summary = estimate_context_tokens([HumanMessage(content=state.get("context_summary", ""))])
    current_tokens = current_token_messages + current_token_summary

    max_allowed = BASE_TOKEN_THRESHOLD + int(current_token_summary * TOKEN_GROWTH_FACTOR)

    goto = "compress_context" if current_tokens > max_allowed else "orchestrator"
    return Command(update={"retrieval_keys": updated_ids}, goto=goto)

def compress_context(state: AgentState, llm):
    messages = _reasoning_messages(state["messages"])
    existing_summary = state.get("context_summary", "").strip()

    if not messages:
        return {}

    conversation_text = f"USER QUESTION:\n{state.get('question')}\n\nConversation to compress:\n\n"
    if existing_summary:
        conversation_text += f"[PRIOR COMPRESSED CONTEXT]\n{existing_summary}\n\n"

    for msg in messages[1:]:
        if isinstance(msg, AIMessage):
            tool_calls_info = ""
            if getattr(msg, "tool_calls", None):
                calls = ", ".join(f"{tc['name']}({tc['args']})" for tc in msg.tool_calls)
                tool_calls_info = f" | Tool calls: {calls}"
            conversation_text += f"[ASSISTANT{tool_calls_info}]\n{msg.content or '(tool call only)'}\n\n"
        elif isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "tool")
            conversation_text += f"[TOOL RESULT — {tool_name}]\n{msg.content}\n\n"

    summary_response = llm.invoke([SystemMessage(content=get_context_compression_prompt()), HumanMessage(content=conversation_text)])
    new_summary = summary_response.content

    retrieved_ids: Set[str] = state.get("retrieval_keys", set())
    if retrieved_ids:
        parent_ids = sorted(r for r in retrieved_ids if r.startswith("parent::"))
        search_queries = sorted(r.replace("search::", "") for r in retrieved_ids if r.startswith("search::"))

        block = "\n\n---\n**Already executed (do NOT repeat):**\n"
        if parent_ids:
            block += "Parent chunks retrieved:\n" + "\n".join(f"- {p.replace('parent::', '')}" for p in parent_ids) + "\n"
        if search_queries:
            block += "Search queries already run:\n" + "\n".join(f"- {q}" for q in search_queries) + "\n"
        new_summary += block

    return {"context_summary": new_summary, "messages": [RemoveMessage(id=m.id) for m in messages[1:]]}

def collect_answer(state: AgentState):
    last_message = state["messages"][-1]
    is_valid = isinstance(last_message, AIMessage) and last_message.content and not last_message.tool_calls
    answer = last_message.content if is_valid else "Unable to generate an answer."
    return {
        "final_answer": answer,
        "agent_answers": [{"index": state["question_index"], "question": state["question"], "answer": answer}]
    }
# --- End of Agent Nodes---

def aggregate_answers(state: State, llm):
    if not state.get("agent_answers"):
        return {"messages": [AIMessage(content="No answers were generated.")]}

    sorted_answers = sorted(state["agent_answers"], key=lambda x: x["index"])
    
    unique_answers = []
    seen_answers = set()
    for ans in sorted_answers:
        answer_text = str(ans["answer"] or "").strip()
        if answer_text and answer_text not in seen_answers:
            unique_answers.append(answer_text)
            seen_answers.add(answer_text)

    remove_messages = [
        RemoveMessage(id=m.id)
        for m in state.get("messages", [])
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)
    ]

    if len(unique_answers) == 1:
        return {"messages": remove_messages + [AIMessage(content=unique_answers[0])]}

    formatted_answers = ""
    for i, answer_text in enumerate(unique_answers, start=1):
        formatted_answers += f"\nAnswer {i}:\n{answer_text}\n"

    user_message = HumanMessage(content=f"""Original user question: {state["originalQuery"]}\nRetrieved answers:{formatted_answers}""")
    synthesis_response = llm.invoke([SystemMessage(content=get_aggregation_prompt()), user_message])
    return {"messages": remove_messages + [AIMessage(content=synthesis_response.content)]}
