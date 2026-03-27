# Contributing to OctoWatch

Welcome! We're glad you're interested in contributing to OctoWatch. Whether you're fixing a bug, adding a feature, improving documentation, or suggesting ideas — every contribution matters.

This guide covers everything you need to get started.

## Prerequisites

Make sure you have the following installed:

- **Python 3.12+** — Backend runtime
- **Node.js 20+** — Frontend toolchain
- **Docker and Docker Compose** — Full-stack local development
- **Git** — Version control

## Development Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Frontend

```bash
cd frontend
npm install
```

### Full Stack (Docker Compose)

For running the complete application with all services (TimescaleDB, Valkey, MinIO, nginx):

```bash
# Generate environment configuration
python scripts/gen_env.py

# Generate TLS certificates (see nginx/ssl/README.md)
# Start all services
docker compose up -d
```

### Pre-Commit Hooks

We use pre-commit hooks to catch issues before they reach CI:

```bash
pip install pre-commit
pre-commit install
```

## Code Style

### Python (Backend)

- **Linter/formatter:** [ruff](https://docs.astral.sh/ruff/) — handles both linting and formatting
- **Type checking:** [mypy](https://mypy-lang.org/) with strict mode
- **Security scanning:** [bandit](https://bandit.readthedocs.io/) and [pip-audit](https://pypi.org/project/pip-audit/)

Run checks locally:

```bash
cd backend
ruff check .            # Linting
ruff format --check .   # Format check
mypy .                  # Type checking
```

### TypeScript (Frontend)

- **Linter:** [ESLint](https://eslint.org/) with TypeScript support
- **Formatter:** [Prettier](https://prettier.io/)

Run checks locally:

```bash
cd frontend
npm run lint            # ESLint
npx tsc --noEmit        # TypeScript type checking
```

## Running Tests

### Backend

```bash
cd backend
pytest                                    # Run all tests
pytest --cov=app --cov-fail-under=80      # Run with coverage (80% threshold)
pytest tests/test_specific.py             # Run a specific test file
```

### Frontend

```bash
cd frontend
npm test                # Run all tests
```

## Branch Naming

Use descriptive branch names with a category prefix:

- `feature/add-webhook-ingestion` — New functionality
- `fix/detection-false-positive` — Bug fixes
- `docs/update-api-reference` — Documentation changes

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) style:

```
<type>(<scope>): <short summary>

<optional body>

<optional footer>
```

**Types:**

| Type | Description |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation changes |
| `style` | Code style changes (formatting, no logic change) |
| `refactor` | Code refactoring (no feature or fix) |
| `test` | Adding or updating tests |
| `chore` | Build process, CI, or tooling changes |
| `perf` | Performance improvements |

**Examples:**

```
feat(detection): add impossible travel rule for SSH key events
fix(ingestion): handle empty S3 prefix without error
docs(readme): add architecture diagram
test(api): add coverage for RBAC scope injection
```

## Pull Request Process

1. **Fork the repository** and create your branch from `main`.
2. **Make your changes** following the code style and testing guidelines above.
3. **Add or update tests** for any new or modified functionality.
4. **Update documentation** if your change affects user-facing behavior.
5. **Add a changelog entry** to `CHANGELOG.md` under `[Unreleased]` if applicable.
6. **Ensure all checks pass** before opening a PR:

   ```bash
   # Backend
   cd backend && ruff check . && ruff format --check . && mypy . && pytest

   # Frontend
   cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
   ```

7. **Open a pull request** against `main` with a clear description of your changes.
8. **Fill out the PR template** — link related issues, describe the change, and complete the checklist.

### CI Requirements

All pull requests must pass the CI pipeline before merging:

- Linting and type checking (backend and frontend)
- All tests pass with required coverage thresholds
- Security scanning (bandit, pip-audit)
- Docker image builds successfully

## Code Review

All submissions require review before merging. Reviewers will look for:

- **Correctness** — Does the code do what it's supposed to?
- **Test coverage** — Are new code paths tested?
- **Code quality** — Is it readable, maintainable, and following project patterns?
- **Security** — Are inputs validated? Are there injection risks?
- **Documentation** — Are public APIs documented? Are complex decisions explained?

Please be responsive to review feedback. We aim to keep PRs focused and small to make review efficient.

## Reporting Bugs

Use the [bug report template](https://github.com/octowatch/octowatch/issues/new?template=bug_report.yml) to file a bug. Include steps to reproduce, expected behavior, and any relevant logs.

## Requesting Features

Use the [feature request template](https://github.com/octowatch/octowatch/issues/new?template=feature_request.yml) to suggest new functionality. Describe the problem you're solving and your proposed approach.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@octowatch.dev.

## Questions?

If you have questions about contributing, feel free to open a [discussion](https://github.com/octowatch/octowatch/discussions) or reach out in an issue. We're happy to help!
