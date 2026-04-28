FROM python:3.12

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV APP_HOST=0.0.0.0
ENV APP_PORT=7860
ENV APP_AUTO_RELOAD=false

# Current project uses Ollama for embeddings.
# Point this to an external Ollama service when running the container.
# Example:
#   docker run -e OLLAMA_HOST=http://host.docker.internal:11434 ...
ENV OLLAMA_HOST=http://host.docker.internal:11434

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /app/requirements.txt

COPY . /app

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/qdrant_db && \
    chown -R appuser:appuser /app

USER appuser

WORKDIR /app/project

EXPOSE 7860

CMD ["python", "app.py"]
