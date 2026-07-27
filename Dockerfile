FROM ghcr.io/astral-sh/uv:0.11.26-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY service ./service
COPY ontology ./ontology
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system ke-memory \
    && useradd --system --gid ke-memory --home-dir /app ke-memory
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY config ./config
COPY prompts ./prompts
RUN mkdir -p /app/state && chown -R ke-memory:ke-memory /app

ENV PATH="/app/.venv/bin:$PATH" \
    KE_MEMORY_ROOT=/app \
    KE_MEMORY_HOST=0.0.0.0 \
    KE_MEMORY_PORT=8787 \
    PYTHONUNBUFFERED=1

USER ke-memory
VOLUME ["/app/state"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=3)"

CMD ["ke-memory-serve"]
