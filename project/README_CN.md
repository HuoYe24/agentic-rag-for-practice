# Agentic RAG System Documentation

[English](README.md)

一个基于 **LangGraph** 的 Agentic RAG 系统，具备 **父子分块**、**稠密 + 稀疏混合检索**、**多模型提供方支持**，当前主入口是 FastAPI Web UI。

## 快速开始

### 安装

推荐使用 `uv` 和 Python 3.12：

```bash
uv python install 3.12
uv venv --python 3.12 .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```bash
uv pip install torch==2.4.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt
```

说明：

- 使用 `uv` 时建议先单独安装 `torch`。本项目中的 `torch==2.4.1+cpu` 来自 PyTorch CPU wheel 源，和其余依赖一起解析时可能触发多索引冲突。
- 如果你的 Python 版本不是 3.12，请先选择与你当前解释器兼容的 Torch 版本，再执行 `uv pip install -r requirements.txt`。
- 如果不确定应该装哪个版本，建议使用 PyTorch 官方安装选择器，根据 Python 版本以及 CPU / CUDA 环境选择命令。

运行前请先准备环境变量文件：

```powershell
Copy-Item project\.env.example project\.env
```

### 启动应用

在运行 `python project/app.py` 之前，请先启动 Ollama。因为本项目用到了 Ollama 的 embedding 模型 `nomic-embed-text:latest`：

```bash
ollama serve
```

你也可以运行下面的命令，检查 Ollama 是否已经正常启动：

```bash
ollama list
```

```bash
python project/app.py
```

默认访问地址为 `http://localhost:7860`。

### 运行前提

- 推荐 Python 3.12，兼容 Python 3.11+
- 推荐用 `uv` 管理环境
- 需要本地 Ollama 或可用的 OpenAI / Anthropic / Google API Key

## 架构概览

系统的核心能力包括：

- 父子分块：小块用于精确召回，大块用于补充完整上下文
- 混合检索：结合 dense embedding 和 sparse BM25
- LangGraph Agent：编排 query rewrite、retrieval、answer generation
- 多提供方支持：可切换 Ollama、OpenAI、Google Gemini、Anthropic Claude
- 向量存储：使用 Qdrant

数据流：

```text
PDF → Markdown Conversion → Parent/Child Chunking → Vector Indexing → Agent Retrieval → LLM Response
```

## 项目结构

### 入口与配置

| 文件 | 作用 |
|------|------|
| `project/app.py` | 应用入口，启动 FastAPI + Uvicorn |
| `project/config.py` | 核心配置中心 |
| `project/utils.py` | PDF 转 Markdown 与上下文 token 估算 |
| `project/document_chunker.py` | 父子分块逻辑 |
| `project/Dockerfile` | Docker 部署文件 |

### Core 层

| 文件 | 作用 |
|------|------|
| `project/core/rag_system.py` | 系统装配与 LangGraph agent 编译 |
| `project/core/document_manager.py` | 文档摄取流程 |
| `project/core/chat_interface.py` | 图调用封装 |
| `project/core/observability.py` | Langfuse tracing 集成 |

### 数据层

| 文件 | 作用 |
|------|------|
| `project/db/vector_db_manager.py` | Qdrant 封装与 embedding 初始化 |
| `project/db/parent_store_manager.py` | parent chunk 文件存储 |

### Agent 层

| 文件 | 作用 |
|------|------|
| `project/rag_agent/graph.py` | 图构建与编译 |
| `project/rag_agent/graph_state.py` | 图状态定义 |
| `project/rag_agent/nodes.py` | 节点实现 |
| `project/rag_agent/edges.py` | 条件边与路由逻辑 |
| `project/rag_agent/tools.py` | 检索工具 |
| `project/rag_agent/prompts.py` | 提示词 |
| `project/rag_agent/schemas.py` | 结构化输出 schema |

### UI 层

| 文件 | 作用 |
|------|------|
| `project/ui/fastapi_ui.py` | FastAPI 路由与 UI 后端逻辑 |
| `project/ui/html_templates.py` | 登录页、文档页、聊天页的 HTML/CSS/JS 模板 |

## 配置说明

主要配置都在 `project/config.py` 中。

### 目录相关

```python
MARKDOWN_DIR = "markdown_docs"
PARENT_STORE_PATH = "parent_store"
QDRANT_DB_PATH = "qdrant_db"
```

### Qdrant 相关

```python
CHILD_COLLECTION = "document_child_chunks"
SPARSE_VECTOR_NAME = "sparse"
```

### 模型相关

```python
DENSE_MODEL = "nomic-embed-text"
DENSE_VECTOR_SIZE = 768
SPARSE_MODEL = "Qdrant/bm25"
OLLAMA_HOST = "http://127.0.0.1:11434"
LLM_MODEL = "qwen-max-0919"
LLM_TEMPERATURE = 0
```

### Agent 参数

```python
MAX_TOOL_CALLS = 8
MAX_ITERATIONS = 10
GRAPH_RECURSION_LIMIT = 50
BASE_TOKEN_THRESHOLD = 2000
TOKEN_GROWTH_FACTOR = 0.9
```

### Langfuse 可观测性

```python
LANGFUSE_ENABLED = False
LANGFUSE_PUBLIC_KEY = ""
LANGFUSE_SECRET_KEY = ""
LANGFUSE_BASE_URL = "http://localhost:3000"
```

## 常见定制

### 切换 LLM 提供方

你可以将默认的 OpenAI-compatible / Ollama 路线替换为 Google、Anthropic 或其他兼容提供方。通常需要：

1. 安装对应 SDK
2. 配置对应 API Key
3. 修改 `project/config.py`
4. 调整 `project/core/rag_system.py` 中的 LLM 初始化逻辑

### 更换 Embedding 模型

直接修改 `project/config.py` 中的 `DENSE_MODEL`，然后重新导入文档。改变 embedding 后需要重建索引。

### 调整 Chunking 策略

可以调节：

- `CHILD_CHUNK_SIZE`
- `CHILD_CHUNK_OVERLAP`
- `MIN_PARENT_SIZE`
- `MAX_PARENT_SIZE`

改完后重新上传文档即可生效。

### Reranker 配置

相关配置：

- `RERANKER_TYPE`
- `CROSS_ENCODER_RERANKER_MODEL`
- `CROSS_ENCODER_LOCAL_FILES_ONLY`
- `INITIAL_SEARCH_TOP_K`
- `RERANKER_TOP_M`
- `FINAL_OUTPUT_TOP_N`

默认 `CROSS_ENCODER_LOCAL_FILES_ONLY=true`，离线环境会优先使用本地缓存的 cross-encoder 模型，不会在启动时阻塞下载。如果需要自动从 Hugging Face 下载模型，可以改成 `false`。

## 可观测性

项目支持可选的 Langfuse tracing，可追踪：

- LLM 调用
- 工具调用
- LangGraph 节点流转
- 部分结构化输出解析过程

启用方式通常是设置：

```bash
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

## 进阶主题

### 自定义 Agent

主要在 `project/rag_agent/` 下扩展：

- 修改 `nodes.py` 增删节点
- 修改 `graph.py` 重组图结构
- 修改 `edges.py` 调整路由逻辑
- 修改 `prompts.py` 调整系统行为
- 修改 `tools.py` 增加新工具

### 替换存储后端

- 向量库：可从本地 Qdrant 替换为 Qdrant Cloud、Pinecone、Weaviate
- Parent store：可替换为 PostgreSQL、MongoDB、S3

### 扩展 UI

主 UI 文件在 `project/ui/fastapi_ui.py`，可以增加运行时设置、管理接口或调试页面。例如：

```python
@app.get("/api/admin/runtime")
async def runtime_settings():
    return {
        "provider": "openai-compatible",
        "parser": current_pdf_parser_name(),
    }
```

### Docker 部署

```bash
docker build -t agentic-rag -f project/Dockerfile .
docker run --name rag-assistant -p 7860:7860 agentic-rag
```

## 故障排查

| 问题 | 原因 | 建议 |
|------|------|------|
| 模型名称报错 | 提供方与模型名不匹配 | 检查 `LLM_MODEL` |
| 检索效果差 | embedding 或 chunk 参数不合适 | 更换 embedding 或调整 chunk |
| 响应慢 | embedding 模型过大或 top_k 过高 | 缩小模型或减少召回数 |
| API 限流 | 外部提供方请求过多 | 增加重试或切换本地模型 |
| 内存不足 | 文档或模型太大 | 降低模型规模，减少批量大小 |
| 检索为空 | 未建立索引或 collection 名称不匹配 | 检查文档上传与 `CHILD_COLLECTION` |
| 切换提供方后 import 失败 | 缺少 SDK | 安装对应依赖 |
| 输出不稳定 | 温度太高 | 将 `LLM_TEMPERATURE` 设为 0 |
