import uuid
from langchain_ollama import ChatOllama
import config
from db.vector_db_manager import VectorDbManager
from db.parent_store_manager import ParentStoreManager
from document_chunker import DocumentChuncker
from rag_agent.tools import ToolFactory
from rag_agent.graph import create_agent_graph
from core.observability import Observability

from langchain_openai import ChatOpenAI
             


class RAGSystem:

    def __init__(self, collection_name=config.CHILD_COLLECTION, parent_store_path=config.PARENT_STORE_PATH):
        self.collection_name = collection_name
        self.vector_db = VectorDbManager()
        self.parent_store = ParentStoreManager(parent_store_path)
        self.chunker = DocumentChuncker()
        self.observability = Observability()
        self.agent_graph = None
        self.llm = None
        self.thread_id = str(uuid.uuid4())
        self.recursion_limit = config.GRAPH_RECURSION_LIMIT

    def initialize(self):
        self.vector_db.create_collection(self.collection_name)
        collection = self.vector_db.get_collection(self.collection_name)

        self.llm = ChatOpenAI(
                model=config.LLM_MODEL,
                temperature=config.LLM_TEMPERATURE,
                base_url=config.LLM_BASE_URL,
                api_key=config.LLM_API_KEY
                
            )

        # llm = ChatOllama(model=config.LLM_MODEL, temperature=config.LLM_TEMPERATURE)
        tools = ToolFactory(collection, self.parent_store, self.llm).create_tools()
        self.agent_graph = create_agent_graph(self.llm, tools)

    def get_config(self):
        cfg = {"configurable": {"thread_id": self.thread_id}, "recursion_limit": self.recursion_limit}
        handler = self.observability.get_handler()
        if handler:
            cfg["callbacks"] = [handler]
        return cfg

    def reset_thread(self):
        try:
            self.agent_graph.checkpointer.delete_thread(self.thread_id)
        except Exception as e:
            print(f"Warning: Could not delete thread {self.thread_id}: {e}")
        self.thread_id = str(uuid.uuid4())
