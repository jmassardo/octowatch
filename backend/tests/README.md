# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run with coverage
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
