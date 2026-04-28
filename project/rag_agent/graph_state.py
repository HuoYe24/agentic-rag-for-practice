from typing import List, Annotated, Set
from langgraph.graph import MessagesState
import operator

def accumulate_or_reset(existing: List[dict], new: List[dict]) -> List[dict]:
    if new and any(item.get('__reset__') for item in new):
        return []
    return existing + new

def set_union(a: Set[str], b: Set[str]) -> Set[str]:
    return a | b

class State(MessagesState):
    """State for main agent graph"""
    questionIsClear: bool = False
    conversation_summary: str = ""
    originalQuery: str = "" 
    rewrittenQuestions: List[str] = []
    agent_answers: Annotated[List[dict], accumulate_or_reset] = []
    chat_route: str = "document_qa"
    clarification_message: str = ""
    current_documents: List[str] = []
    document_previews: List[dict] = []
    recent_history: List[dict] = []

class AgentState(MessagesState):
    """State for individual agent subgraph"""
    question: str = ""
    question_index: int = 0
    context_summary: str = ""
    retrieval_grade: str = ""
    retrieval_feedback: str = ""
    retrieval_retry_count: int = 0
    retrieval_keys: Annotated[Set[str], set_union] = set()
    final_answer: str = ""
    agent_answers: List[dict] = []
    tool_call_count: Annotated[int, operator.add] = 0
    iteration_count: Annotated[int, operator.add] = 0
