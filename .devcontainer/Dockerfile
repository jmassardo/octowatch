FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install system packages needed by Python dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Python backend dependencies for faster startup
COPY backend/pyproject.toml /tmp/backend/pyproject.toml
RUN pip install --no-cache-dir -e "/tmp/backend[dev]" 2>/dev/null || true

# Pre-install pre-commit
RUN pip install --no-cache-dir pre-commit
