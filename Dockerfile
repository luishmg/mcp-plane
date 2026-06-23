# syntax=docker/dockerfile:1.7
# Plane MCP Server — Streamable HTTP transport.
#
# Run: docker build -t plane-mcp .
# The container binds 127.0.0.1:8763 by default. Override HOST to 0.0.0.0 only
# if you place this behind a reverse proxy / authentication layer.

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and buffering stdout/stderr.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application package.
COPY app/ ./app/

# Create a non-root user and switch to it.
RUN groupadd --system appuser && \
    useradd --system --gid appuser --no-create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health: FastAPI /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        urllib.request.urlopen('http://127.0.0.1:${PORT:-8763}/health').read(); sys.exit(0)" \
    || exit 1

EXPOSE 8763

# uvicorn reads HOST/PORT from the environment via app.config.Settings.
CMD ["sh", "-c", "uvicorn app.server:app --host ${HOST:-127.0.0.1} --port ${PORT:-8763}"]
