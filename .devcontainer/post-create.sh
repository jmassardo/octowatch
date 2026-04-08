#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing backend dependencies..."
cd /workspaces/octowatch/backend
pip install -e ".[dev]"

echo "==> Installing frontend dependencies..."
cd /workspaces/octowatch/frontend
npm install

echo "==> Installing pre-commit hooks..."
cd /workspaces/octowatch
pre-commit install

echo "==> Running database migrations..."
cd /workspaces/octowatch/backend
alembic upgrade head

echo ""
echo "✅ Dev environment ready!"
echo ""
echo "  Backend:  cd backend && uvicorn app.main:app --reload --host 0.0.0.0"
echo "  Frontend: cd frontend && npm run dev"
echo "  Tests:    make test"
echo "  Lint:     make lint"
echo ""
