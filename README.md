# Agentic RAG for Practice

[中文说明 / Chinese](README_CN.md)

<p align="center">
  <img src="assets/logo.png" alt="Agentic RAG for Practice Logo" width="220" />
</p>

A practice-oriented multi-user Agentic RAG document QA system. The current main entry point is a FastAPI web UI with document upload, hybrid retrieval, reranking, LangGraph workflows, multi-turn memory, and conversation isolation after document-library changes.

## Demo

![Agentic RAG for Practice Demo](assets/demo.gif)

## Overview

This project is more than a simple "vector search + LLM answer" demo. It already has a product-like shape and focuses on:

- Private document QA
- Context understanding across multi-turn conversations
- Preventing stale context after document-library changes
- Multi-user document and chat isolation
- More explainable retrieval behavior

Current capabilities:

- User registration and login
- PDF / Markdown upload
- PDF parsing with LlamaParse / PyMuPDF4LLM
- Parent-child chunking
- Dense + sparse hybrid retrieval
- Cross-encoder reranker
- LangGraph-based Agentic RAG workflow
- CRAG-style retrieval-quality grading
- Persistent chat history and summary memory
- Document-version-aware thread refresh strategy

## Origin

This project is based on and extended from:

- Original repository: [GiovanniPasq/agentic-rag-for-dummies](https://github.com/GiovanniPasq/agentic-rag-for-dummies)

Major changes in this version include:

- FastAPI UI and multi-user login system
- Document-version-aware chat thread refresh
- Answer-basis display and intermediate status cards
- CRAG-style retrieval grading
- Better upload workflow and document management
- Improved Docker and environment-variable loading

## Architecture

The system can be viewed in 5 layers:

1. Web: FastAPI pages and APIs
2. Core: chat, document management, user state, and RAG assembly
3. Agent: LangGraph graph, nodes, edges, tools, and prompts
4. Storage: Qdrant, parent store, and local chat state
5. Model: external OpenAI-compatible LLM plus Ollama embeddings

Typical flow:

```text
Upload Document
  -> PDF/Markdown preprocessing
  -> parent/child chunking
  -> child chunks into Qdrant
  -> parent chunks into parent_store
  -> documents_version bump
  -> user asks a question
  -> LLM Router
  -> LangGraph document QA flow
  -> retrieval / rerank / grading / answer
```

## Repository Structure

```text
.
├─ project/
│  ├─ app.py
│  ├─ config.py
│  ├─ document_chunker.py
│  ├─ core/
│  ├─ db/
│  ├─ rag_agent/
│  ├─ ui/
│  ├─ Dockerfile
│  ├─ README.md
│  └─ README_CN.md
├─ data/                  # local runtime user data
├─ qdrant_db/             # local Qdrant storage
├─ requirements.txt
├─ README.md
└─ README_CN.md
```

`project/README.md` focuses more on implementation and development details, while this README focuses on setup and usage.

## Requirements

- Recommended Python 3.12
- Compatible with Python 3.11+
- `uv` is recommended for environment management
- An accessible OpenAI-compatible LLM API
- A local or remote Ollama service
- The embedding model `nomic-embed-text`

Recommended preparation:

```bash
ollama serve
ollama pull nomic-embed-text
```

## Configuration

Configuration priority:

1. Process environment variables
2. `project/.env`
3. Default values in `project/config.py`

Key settings:

- `LLM_MODEL`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `DENSE_MODEL`
- `SPARSE_MODEL`
- `OLLAMA_HOST`
- `APP_HOST`
- `APP_PORT`
- `APP_AUTO_RELOAD`

Copy and rename `project/.env.example` to `project/.env` first:

```powershell
Copy-Item project\.env.example project\.env
```

Then fill in your own `LLM_API_KEY` and other local settings.

## Local Run

### Recommended: `uv` + Python 3.12

```bash
uv python install 3.12
uv venv --python 3.12 .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
uv pip install torch==2.4.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt
```

Notes:

- Install `torch` first because `torch==2.4.1+cpu` comes from the PyTorch CPU wheel index and can conflict with multi-index dependency resolution.
- If you are not using Python 3.12, choose a Torch version compatible with your interpreter first.
- When in doubt, use the official PyTorch install selector for your Python version and CPU / CUDA environment.

Prepare environment variables:

```powershell
Copy-Item project\.env.example project\.env
```

Start the app:

```bash
cd project
python app.py
```

### Alternative: `pip`

```bash
pip install -r requirements.txt
cd project
python app.py
```

Default URL:

```text
http://127.0.0.1:7860
```

## Usage

1. Register and log in
2. Upload PDF or Markdown files on the Documents page
3. Choose one of the upload modes:
   - `Supplement Current Topic`
   - `Start New Topic`
4. Return to the chat page and ask questions

The UI can show answer-basis hints such as:

- `回答依据：模型直接生成`
- `回答依据：当前文档列表`
- `回答依据：文档库概览`
- `回答依据：当前文档库检索`

## Document Refresh Strategy

The project uses a "document version + chat thread version" mechanism:

- Effective document changes bump `documents_version`
- Each chat stores its own `document_context_version`
- If a chat version is stale, a new `thread_id` is used on the next real message
- Old chat history remains visible but no longer participates in reasoning

## Docker

Recommended deployment model:

- Run only the FastAPI app inside the container
- Use Ollama as an external embedding service
- Use an external OpenAI-compatible API for the main LLM

Build:

```bash
docker build -f project/Dockerfile -t agentic-rag-fastapi .
```

Run:

```bash
docker run --rm -p 7860:7860 --env-file project/.env agentic-rag-fastapi
```

## Public URL

The current main UI is FastAPI.

- Use `cloudflared` for temporary public exposure
- Use a cloud server for longer-term deployment

Example:

```bash
cloudflared tunnel --url http://127.0.0.1:7860
```

## Current Limits

- LangGraph checkpointing is still memory-based
- Document overwrite/update strategy is not implemented separately
- Page-level citation is not implemented yet
- Clearing the document library uses lazy chat refresh, not automatic global reset

## License

This repository is licensed under the [MIT License](LICENSE).

This project is based on and modified from the original work by [Giovanni Pasqualino](https://github.com/GiovanniPasq/agentic-rag-for-dummies).
The original copyright notice is preserved in the LICENSE file.
