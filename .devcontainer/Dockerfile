FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# Install Node.js 20
# Remove stale Yarn repo first to avoid GPG errors during apt-get update
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install system packages needed by Python dependencies
# Remove stale Yarn repo that has an expired GPG key
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Python backend dependencies for faster startup
COPY backend/pyproject.toml /tmp/backend/pyproject.toml
RUN pip install --no-cache-dir -e "/tmp/backend[dev]" 2>/dev/null || true

# Pre-install pre-commit
RUN pip install --no-cache-dir pre-commit
