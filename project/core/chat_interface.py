import json
import re
import queue
import threading
import time
import uuid
from langchain_core.messages import AIMessage, HumanMessage, AIMessageChunk, SystemMessage, ToolMessage
from rag_agent.prompts import get_chat_router_prompt, get_document_library_overview_prompt

SILENT_NODES = {
    "chat_router",
    "rewrite_query",
    "agent",
    "orchestrator",
    "grade_retrieval",
    "compress_context",
    "fallback_response",
    "collect_answer",
}
SYSTEM_NODES = {"summarize_history", "rewrite_query", "grade_retrieval"}
STATUS_NODE = "work_status"
ANSWER_BASIS_NODE = "answer_basis"

ANSWER_BASIS_BY_NODE = {
    "direct_chat": (
        "回答依据：模型直接生成",
        "本轮回答由大模型直接生成，没有执行文档检索。",
    ),
    "document_inventory": (
        "回答依据：当前文档列表",
        "本轮回答使用当前已上传文档列表，没有执行语义检索。",
    ),
    "document_library_overview": (
        "回答依据：文档库概览",
        "本轮回答使用当前文档名称和文档预览信息。",
    ),
    "empty_documents_response": (
        "回答依据：文档库状态检查",
        "当前文档库为空，因此跳过文档检索。",
    ),
    "router_clarification": (
        "回答依据：问题澄清",
        "本轮没有生成最终答案，因为系统需要更明确的问题。",
    ),
    "request_clarification": (
        "回答依据：问题澄清",
        "本轮没有生成最终答案，因为问题需要更多细节。",
    ),
    "aggregate_answers": (
        "回答依据：当前文档库检索",
        "本轮回答基于当前文档库检索到的片段生成。",
    ),
}

SYSTEM_NODE_CONFIG = {
    "rewrite_query":     {"title": "🔍 Query Analysis & Rewriting"},
    "grade_retrieval":   {"title": "🧪 Retrieval Quality Check"},
    "summarize_history": {"title": "📋 Chat History Summary"},
}

# --- Helpers ---

def make_message(content, *, title=None, node=None):
    msg = {"role": "assistant", "content": content}
    if title or node:
        msg["metadata"] = {k: v for k, v in {"title": title, "node": node}.items() if v}
    return msg


def find_msg_idx(messages, node):
    return next(
        (i for i, m in enumerate(messages) if m.get("metadata", {}).get("node") == node),
        None,
    )


def parse_rewrite_json(buffer):
    match = re.search(r"\{.*\}", buffer, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        return None


def format_rewrite_content(buffer):
    data = parse_rewrite_json(buffer)
    if not data:
        return "⏳ Analyzing query..."
    if data.get("is_clear"):
        lines = ["✅ **Query is clear**"]
        if data.get("questions"):
            lines += ["\n**Rewritten queries:**"] + [f"- {q}" for q in data["questions"]]
    else:
        lines = ["❓ **Query is unclear**"]
        clarification = data.get("clarification_needed", "")
        if clarification and clarification.strip().lower() != "no":
            lines.append(f"\nClarification needed: *{clarification}*")
    return "\n".join(lines)

def format_retrieval_grade_content(buffer):
    data = parse_rewrite_json(buffer)
    if not data:
        return "⏳ Checking retrieval quality..."

    grade = str(data.get("grade", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()

    if grade == "sufficient":
        lines = ["✅ **Retrieval is sufficient**"]
    elif grade == "insufficient":
        lines = ["❌ **Retrieval needs another round**"]
    else:
        lines = ["❓ **Retrieval quality is unclear**"]

    if reason:
        lines.append(f"\nReason: *{reason}*")
    return "\n".join(lines)

# --- End of Helpers ---

class ChatInterface:

    def __init__(self, rag_system):
        self.rag_system = rag_system
        self._stop_requested = False

    def _merge_system_buffer(self, node, existing_buffer, chunk):
        content = chunk.content or ""
        if not content:
            return existing_buffer

        if isinstance(chunk, AIMessage):
            if existing_buffer.strip() == content.strip() or existing_buffer.endswith(content):
                return existing_buffer
            if content.startswith(existing_buffer):
                return content

        if node in {"rewrite_query", "grade_retrieval"}:
            if existing_buffer.strip().endswith("}") and content.lstrip().startswith("{"):
                return content

        return existing_buffer + content

    def _handle_system_node(self, chunk, node, response_messages, system_node_buffer):
        """Update (or create) the collapsible system-node message and surface any clarification."""
        system_node_buffer[node] = self._merge_system_buffer(
            node,
            system_node_buffer.get(node, ""),
            chunk,
        )
        buffer = system_node_buffer[node]
        title  = SYSTEM_NODE_CONFIG[node]["title"]
        if node == "rewrite_query":
            content = format_rewrite_content(buffer)
        elif node == "grade_retrieval":
            content = format_retrieval_grade_content(buffer)
        else:
            content = buffer

        idx = find_msg_idx(response_messages, node)
        if idx is None:
            response_messages.append(make_message(content, title=title, node=node))
        else:
            response_messages[idx]["content"] = content

        if node == "rewrite_query":
            self._surface_clarification(buffer, response_messages)

    def _surface_clarification(self, buffer, response_messages):
        """If the query is unclear, add/update a plain clarification message."""
        data          = parse_rewrite_json(buffer) or {}
        clarification = data.get("clarification_needed", "")
        if not data.get("is_clear") and clarification.strip().lower() not in ("", "no"):
            cidx = find_msg_idx(response_messages, "clarification")
            if cidx is None:
                response_messages.append(make_message(clarification, node="clarification"))
            else:
                response_messages[cidx]["content"] = clarification

    def _handle_tool_call(self, chunk, response_messages, active_tool_calls):
        """Register new tool calls as collapsible messages."""
        for tc in chunk.tool_calls:
            if tc.get("id") and tc["id"] not in active_tool_calls:
                response_messages.append(
                    make_message(f"Running `{tc['name']}`...", title=f"🛠️ {tc['name']}")
                )
                active_tool_calls[tc["id"]] = len(response_messages) - 1

    def _handle_tool_result(self, chunk, response_messages, active_tool_calls):
        """Fill in the tool result inside the matching collapsible message."""
        idx = active_tool_calls.get(chunk.tool_call_id)
        if idx is not None:
            preview = str(chunk.content)[:300]
            suffix  = "\n..." if len(str(chunk.content)) > 300 else ""
            response_messages[idx]["content"] = f"```\n{preview}{suffix}\n```"

    def _upsert_answer_basis(self, response_messages, node):
        basis = ANSWER_BASIS_BY_NODE.get(node)
        if not basis:
            return

        title, content = basis
        idx = find_msg_idx(response_messages, ANSWER_BASIS_NODE)
        if idx is None:
            response_messages.append(make_message(content, title=title, node=ANSWER_BASIS_NODE))
        else:
            response_messages[idx]["metadata"]["title"] = title
            response_messages[idx]["content"] = content

    def _last_plain_assistant_message(self, response_messages):
        for msg in reversed(response_messages):
            if msg.get("role") == "assistant" and "metadata" not in msg:
                return msg
        return None

    def _handle_llm_token(self, chunk, node, response_messages):
        """Append streaming LLM tokens to the last plain assistant message."""
        content = chunk.content
        if not content:
            return

        last = response_messages[-1] if response_messages else None
        last_plain = self._last_plain_assistant_message(response_messages)

        if isinstance(chunk, AIMessage) and last_plain:
            existing = last_plain.get("content", "")
            if existing.strip() == content.strip() or existing.endswith(content):
                return
            if content.startswith(existing):
                last_plain["content"] = content
                return
            if len(content.strip()) > 80 and content.strip() in existing:
                return

        if not (last and last.get("role") == "assistant" and "metadata" not in last):
            response_messages.append(make_message(""))
        response_messages[-1]["content"] += content

    def _dedupe_repeated_blocks(self, text):
        """Remove exact adjacent repeated paragraphs from streamed assistant output."""
        if not text or "\n\n" not in text:
            return text

        parts = re.split(r"\n{2,}", text)
        deduped = []
        previous = None
        for part in parts:
            normalized = re.sub(r"\s+", " ", part).strip()
            if normalized and normalized == previous:
                continue
            deduped.append(part)
            if normalized:
                previous = normalized
        return "\n\n".join(deduped)

    def _dedupe_plain_assistant_messages(self, response_messages):
        for msg in response_messages:
            if msg.get("role") == "assistant" and "metadata" not in msg:
                msg["content"] = self._dedupe_repeated_blocks(msg.get("content", ""))

    def _iter_full_message_prefixes(self, content, step=24):
        text = str(content or "")
        if not text:
            return
        for end in range(step, len(text), step):
            yield text[:end]
        yield text

    def _upsert_status(self, response_messages, stage_text, elapsed_seconds):
        """Update a persistent status message so users can see ongoing work."""
        status_content = f"{stage_text}\n\n⏱️ Elapsed: {elapsed_seconds}s"
        idx = find_msg_idx(response_messages, STATUS_NODE)
        if idx is None:
            response_messages.append(
                make_message(status_content, title="⏳ Working", node=STATUS_NODE)
            )
        else:
            response_messages[idx]["content"] = status_content

    def _remove_status(self, response_messages):
        idx = find_msg_idx(response_messages, STATUS_NODE)
        if idx is not None:
            response_messages.pop(idx)

    def _parse_json_response(self, text):
        match = re.search(r"\{.*\}", str(text or ""), re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except Exception:
            return None

    def _plain_history_items(self, history):
        plain_history = []
        for item in history:
            if not isinstance(item, dict):
                continue
            if item.get("metadata"):
                continue
            role = item.get("role")
            content = str(item.get("content") or "").strip()
            if not content or role not in {"user", "assistant"}:
                continue
            plain_history.append((role, content))
        return plain_history

    def _history_for_prompt(self, history, limit=8):
        recent_items = self._plain_history_items(history)[-limit:]
        if not recent_items:
            return "(empty)"
        return "\n".join(f"{role}: {content}" for role, content in recent_items)

    def _fallback_route(self, message):
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

    def _is_follow_up_document_query(self, message):
        normalized = " ".join((message or "").strip().lower().split())
        follow_up_markers = [
            "从当前文档库中寻找",
            "从文档中找",
            "在文档中找",
            "从当前文档库里找",
            "继续",
            "接着说",
            "进一步",
            "那",
            "那么",
            "这个",
            "这个问题",
            "它",
            "它们",
            "这些",
            "those",
            "that",
            "this",
            "continue",
            "what about",
            "from the current document library",
        ]
        if len((message or "").strip()) <= 24:
            return True
        return any(marker in normalized for marker in follow_up_markers)

    def _build_contextual_document_query(self, message, history):
        plain_history = self._plain_history_items(history)
        if not plain_history or not self._is_follow_up_document_query(message):
            return message.strip()

        context_window = plain_history[-4:]
        context_lines = [f"{role}: {content}" for role, content in context_window]
        return (
            "Recent conversation context from this chat:\n"
            + "\n".join(context_lines)
            + "\n\nCurrent user query about the current document library:\n"
            + message.strip()
        )

    def route_message(self, message, history, current_documents):
        fallback = self._fallback_route(message)

        if not self.rag_system.llm:
            return fallback

        router_messages = [
            SystemMessage(content=get_chat_router_prompt()),
            HumanMessage(
                content=(
                    f"current_documents: {json.dumps(current_documents, ensure_ascii=False)}\n"
                    f"recent_history:\n{self._history_for_prompt(history)}\n\n"
                    f"current_query: {message.strip()}"
                )
            ),
        ]

        try:
            result = self.rag_system.llm.invoke(router_messages)
            data = self._parse_json_response(getattr(result, "content", result))
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
                return fallback
            if route == "general_chat" and fallback.get("route") != "general_chat":
                return fallback
            return {
                "route": route,
                "clarification_message": clarification_message,
            }
        except Exception:
            return fallback

    def _build_direct_chat_messages(self, message, history):
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

        plain_history = []
        for item in history:
            if not isinstance(item, dict):
                continue
            if item.get("metadata"):
                continue
            role = item.get("role")
            content = str(item.get("content") or "").strip()
            if not content or role not in {"user", "assistant"}:
                continue
            plain_history.append((role, content))

        for role, content in plain_history[-8:]:
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=message.strip()))
        return messages

    def _build_document_library_overview_messages(self, message, history, document_previews):
        payload = {
            "current_documents": [item["name"] for item in document_previews],
            "document_previews": document_previews,
            "recent_history": self._history_for_prompt(history),
            "user_request": message.strip(),
        }
        return [
            SystemMessage(content=get_document_library_overview_prompt()),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
        ]

    def _stream_llm_messages(self, prompt_messages, stage_text, basis_node=None):
        if not self.rag_system.llm:
            yield "⚠️ System not initialized!"
            return

        self._stop_requested = False
        response_messages = []
        start_time = time.time()

        try:
            self._upsert_status(response_messages, stage_text, elapsed_seconds=0)
            self._upsert_answer_basis(response_messages, basis_node)
            yield response_messages

            for chunk in self.rag_system.llm.stream(prompt_messages):
                if self._stop_requested:
                    self._remove_status(response_messages)
                    return

                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    self._handle_llm_token(chunk, "", response_messages)
                    elapsed = int(time.time() - start_time)
                    self._upsert_status(response_messages, stage_text, elapsed_seconds=elapsed)
                    yield response_messages
                elif isinstance(chunk, AIMessage) and chunk.content:
                    for partial in self._iter_full_message_prefixes(chunk.content):
                        self._handle_llm_token(AIMessage(content=partial), "", response_messages)
                        elapsed = int(time.time() - start_time)
                        self._upsert_status(response_messages, stage_text, elapsed_seconds=elapsed)
                        yield response_messages

            self._remove_status(response_messages)
            self._dedupe_plain_assistant_messages(response_messages)
            yield response_messages

        except Exception as e:
            self._remove_status(response_messages)
            response_messages.append(make_message(f"❌ Error: {str(e)}"))
            yield response_messages

    def chat(self, message, history, current_documents=None, document_previews=None):
        """Generator that streams Gradio chat message dicts."""
        if not self.rag_system.agent_graph:
            yield "⚠️ System not initialized!"
            return

        self._stop_requested = False

        config        = self.rag_system.get_config()
        current_state = self.rag_system.agent_graph.get_state(config)

        try:
            current_documents = current_documents or []
            document_previews = document_previews or []
            if current_state.next:
                self.rag_system.agent_graph.update_state(
                    config,
                    {
                        "messages": [HumanMessage(content=message.strip())],
                        "current_documents": current_documents,
                        "document_previews": document_previews,
                        "recent_history": history,
                    },
                )
                stream_input = None
            else:
                stream_input = {
                    "messages": [HumanMessage(content=message.strip())],
                    "current_documents": current_documents,
                    "document_previews": document_previews,
                    "recent_history": history,
                }

            response_messages  = []
            active_tool_calls  = {}
            system_node_buffer = {}
            event_queue = queue.Queue()
            start_time = time.time()
            heartbeat = 0.5
            stage_text = "🧠 Understanding your question..."

            def stream_worker():
                try:
                    for chunk, metadata in self.rag_system.agent_graph.stream(
                        stream_input, config=config, stream_mode="messages"
                    ):
                        if self._stop_requested:
                            break
                        event_queue.put(("chunk", chunk, metadata))
                except Exception as worker_error:
                    event_queue.put(("error", str(worker_error), None))
                finally:
                    event_queue.put(("done", None, None))

            threading.Thread(target=stream_worker, daemon=True).start()

            self._upsert_status(response_messages, stage_text, elapsed_seconds=0)
            yield response_messages

            while True:
                if self._stop_requested:
                    self._remove_status(response_messages)
                    return

                try:
                    event_type, chunk, metadata = event_queue.get(timeout=heartbeat)
                except queue.Empty:
                    elapsed = int(time.time() - start_time)
                    self._upsert_status(response_messages, stage_text, elapsed_seconds=elapsed)
                    yield response_messages
                    continue

                if event_type == "done":
                    break

                if event_type == "error":
                    self._remove_status(response_messages)
                    response_messages.append(make_message(f"❌ Error: {chunk}"))
                    yield response_messages
                    return

                node = metadata.get("langgraph_node", "")

                if node in SYSTEM_NODES and isinstance(chunk, (AIMessage, AIMessageChunk)) and chunk.content:
                    self._handle_system_node(chunk, node, response_messages, system_node_buffer)
                    if node == "summarize_history":
                        stage_text = "📋 Summarizing conversation history..."
                    elif node == "rewrite_query":
                        stage_text = "🔍 Rewriting query and planning retrieval..."
                    elif node == "grade_retrieval":
                        stage_text = "🧪 Checking retrieval quality..."

                elif hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    self._handle_tool_call(chunk, response_messages, active_tool_calls)
                    tool_names = ", ".join(
                        [tc.get("name", "tool") for tc in chunk.tool_calls if tc.get("name")]
                    )
                    if tool_names:
                        stage_text = f"🛠️ Running tools: {tool_names}"

                elif isinstance(chunk, ToolMessage):
                    self._handle_tool_result(chunk, response_messages, active_tool_calls)
                    stage_text = "📚 Processing retrieved documents..."

                elif isinstance(chunk, (AIMessage, AIMessageChunk)) and chunk.content and node not in SILENT_NODES:
                    self._upsert_answer_basis(response_messages, node)
                    if isinstance(chunk, AIMessageChunk):
                        self._handle_llm_token(chunk, node, response_messages)
                        stage_text = "✍️ Generating final answer..."
                    else:
                        stage_text = "✍️ Generating final answer..."
                        for partial in self._iter_full_message_prefixes(chunk.content):
                            self._handle_llm_token(AIMessage(content=partial), node, response_messages)
                            elapsed = int(time.time() - start_time)
                            self._upsert_status(response_messages, stage_text, elapsed_seconds=elapsed)
                            yield response_messages
                        continue

                elapsed = int(time.time() - start_time)
                self._upsert_status(response_messages, stage_text, elapsed_seconds=elapsed)
                yield response_messages

            self._remove_status(response_messages)
            self._dedupe_plain_assistant_messages(response_messages)
            yield response_messages

        except Exception as e:
            yield f"❌ Error: {str(e)}"

    def direct_chat(self, message, history):
        prompt_messages = self._build_direct_chat_messages(message, history)
        yield from self._stream_llm_messages(
            prompt_messages,
            "💬 Answering directly...",
            basis_node="direct_chat",
        )

    def document_library_overview(self, message, history, document_previews):
        prompt_messages = self._build_document_library_overview_messages(
            message, history, document_previews
        )
        yield from self._stream_llm_messages(
            prompt_messages,
            "📚 Reviewing the current document library...",
            basis_node="document_library_overview",
        )

    def clear_session(self):
        self.rag_system.reset_thread()
        self.rag_system.observability.flush()

    def set_thread(self, thread_id):
        self.rag_system.thread_id = thread_id

    def new_thread(self):
        new_thread_id = str(uuid.uuid4())
        self.rag_system.thread_id = new_thread_id
        return new_thread_id

    def request_stop(self):
        self._stop_requested = True
