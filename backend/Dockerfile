# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies in one layer, then clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    xmlsec1 \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Install dependencies into /install so we can copy them into the final stage
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="audit-log-analyzer-api"
LABEL org.opencontainers.image.description="Audit Log Analyzer API + Worker"

# Runtime OS libs needed by xmlsec1 / asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libxml2 \
    libxslt1.1 \
    xmlsec1 \
    libxmlsec1-openssl \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -r -u 1001 -g root -m -d /app appuser

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:root app/ ./app/
COPY --chown=appuser:root alembic/ ./alembic/
COPY --chown=appuser:root alembic.ini .

# GeoIP DB mount point (read-only volume in production)
RUN mkdir -p /app/data && chown appuser:root /app/data

USER appuser

# Expose API port
EXPOSE 8000

# Default: run the API server
# Override CMD for workers: celery -A app.celery_app worker ...
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
