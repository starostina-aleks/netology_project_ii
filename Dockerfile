# syntax=docker/dockerfile:1.7

# ========== STAGE 1: BUILDER ==========
FROM python:3.13-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_EXTRA=tracing

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY app/ ./app/
COPY bot/ ./bot/
COPY pyproject.toml uv.lock ./
COPY wheels/ ./wheels/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN uv pip install ./wheels/ru_core_news_md-3.8.0-py3-none-any.whl
RUN /app/.venv/bin/python -m nltk.downloader -d /app/nltk_data punkt_tab

# ========== STAGE 2: RUNTIME ==========
FROM python:3.13-slim-bookworm
ARG RAG_DATA_DIR

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

#RUN mkdir -p /$RAG_DATA_DIR && chown -R appuser:appuser /$RAG_DATA_DIR

#RUN mkdir -p /$RAG_DATA_DIR && chmod 777 /$RAG_DATA_DIR

RUN mkdir -p /$RAG_DATA_DIR

COPY --from=builder --chown=appuser:appuser /app /app
RUN chown -R appuser:appuser /$RAG_DATA_DIR


USER root
RUN chmod 777 /$RAG_DATA_DIR

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NLTK_DATA="/app/nltk_data"

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else sys.exit(1)" \
    || exit 1

CMD ["python", "-m","uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]