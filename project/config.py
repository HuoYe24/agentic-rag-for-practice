import os


def _env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_float(name: str, default: float) -> float:
    value = _env_str(name, "")
    if not value:
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = _env_str(name, "")
    if not value:
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name, "")
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


# --- Directory Configuration ---
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))

MARKDOWN_DIR = os.path.join(_BASE_DIR, "data", "_legacy_default", "markdown_docs")
PARENT_STORE_PATH = os.path.join(_BASE_DIR, "data", "_legacy_default", "parent_store")
QDRANT_DB_PATH = os.path.join(_BASE_DIR, "qdrant_db")

# --- Qdrant Configuration ---
CHILD_COLLECTION = "document_child_chunks"
SPARSE_VECTOR_NAME = "sparse"

# --- Model Configuration ---
DENSE_MODEL = _env_str("DENSE_MODEL", "nomic-embed-text")
DENSE_VECTOR_SIZE = _env_int("DENSE_VECTOR_SIZE", 768)
SPARSE_MODEL = _env_str("SPARSE_MODEL", "Qdrant/bm25")
OLLAMA_HOST = _env_str("OLLAMA_HOST", "http://127.0.0.1:11434")
LLM_MODEL = _env_str("LLM_MODEL", "qwen-max-0919")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0)

LLM_API_KEY = _env_str("LLM_API_KEY", "")
LLM_BASE_URL = _env_str("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

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


# --- Memory Safety Configuration ---
MAX_UPLOAD_SIZE_MB = _env_int("MAX_UPLOAD_SIZE_MB", 200)  # Upload file size limit (MB)
MAX_MD_SIZE_MB = _env_int("MAX_MD_SIZE_MB", 50)           # Markdown file size limit (MB)
# --- Reranker Configuration ---
RERANKER_TYPE = _env_str("RERANKER_TYPE", "cross_encoder").strip().lower()  # Options: "llm", "cross_encoder", "none"
RERANKER_ENABLED = RERANKER_TYPE in {"llm", "cross_encoder"}
CROSS_ENCODER_RERANKER_MODEL = _env_str("CROSS_ENCODER_RERANKER_MODEL", "BAAI/bge-reranker-base")
CROSS_ENCODER_LOCAL_FILES_ONLY = _env_bool("CROSS_ENCODER_LOCAL_FILES_ONLY", True)
INITIAL_SEARCH_TOP_K = 10  # Initial retrieval top-K
RERANKER_TOP_M = 5         # Rerank result top-M (M <= K)
FINAL_OUTPUT_TOP_N = 5     # Final output top-N unique parent chunks

# --- Langfuse Observability ---
LANGFUSE_ENABLED = _env_bool("LANGFUSE_ENABLED", False)
LANGFUSE_PUBLIC_KEY = _env_str("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = _env_str("LANGFUSE_SECRET_KEY", "")
LANGFUSE_BASE_URL = _env_str("LANGFUSE_BASE_URL", "http://localhost:3000")
