# syntax=docker/dockerfile:1
# ─── Stage 1: Build dependencies ─────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution/install
RUN pip install --no-cache-dir uv

# Copy project metadata only (cache-friendly layer)
COPY pyproject.toml ./

# Install production dependencies into /build/venv
RUN uv venv /build/venv && \
    uv pip install --python /build/venv/bin/python --no-cache \
    boto3 numpy fastapi pydantic "uvicorn[standard]"

# ─── Stage 2: Runtime image ───────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /build/venv /app/venv

# Copy application source
COPY --chown=appuser:appgroup . .

ENV PATH="/app/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    LOG_LEVEL=info \
    EMBEDDING_BACKEND=bedrock \
    ENABLE_UI=false

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"

CMD ["python", "main.py"]
