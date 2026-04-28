import os

# --- Directory Configuration ---
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))

MARKDOWN_DIR = os.path.join(_BASE_DIR, "data", "_legacy_default", "markdown_docs")
PARENT_STORE_PATH = os.path.join(_BASE_DIR, "data", "_legacy_default", "parent_store")
QDRANT_DB_PATH = os.path.join(_BASE_DIR, "qdrant_db")

# --- Qdrant Configuration ---
CHILD_COLLECTION = "document_child_chunks"
SPARSE_VECTOR_NAME = "sparse"

# --- Model Configuration ---
DENSE_MODEL = os.environ.get("DENSE_MODEL", "nomic-embed-text")
SPARSE_MODEL = os.environ.get("SPARSE_MODEL", "Qdrant/bm25")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen-max-0919")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# --- Agent Configuration ---
MAX_TOOL_CALLS = 8
MAX_ITERATIONS = 10
CRAG_MAX_RETRIES = 2
GRAPH_RECURSION_LIMIT = 50
BASE_TOKEN_THRESHOLD = 2000
TOKEN_GROWTH_FACTOR = 0.9

# --- Text Splitter Configuration ---
CHILD_CHUNK_SIZE = 500
CHILD_CHUNK_OVERLAP = 100
MIN_PARENT_SIZE = 2000
MAX_PARENT_SIZE = 4000
HEADERS_TO_SPLIT_ON = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3")
]

# --- Reranker Configuration ---
RERANKER_TYPE = os.environ.get("RERANKER_TYPE", "cross_encoder").strip().lower()  # Options: "llm", "cross_encoder", "none"
RERANKER_ENABLED = RERANKER_TYPE in {"llm", "cross_encoder"}
CROSS_ENCODER_RERANKER_MODEL = os.environ.get("CROSS_ENCODER_RERANKER_MODEL", "BAAI/bge-reranker-base")
INITIAL_SEARCH_TOP_K = 10  # Initial retrieval top-K
RERANKER_TOP_M = 5         # Rerank result top-M (M <= K)
FINAL_OUTPUT_TOP_N = 5     # Final output top-N unique parent chunks

# --- Langfuse Observability ---
LANGFUSE_ENABLED = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000")
