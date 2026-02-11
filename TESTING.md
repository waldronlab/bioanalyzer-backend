# Testing Guide for BioAnalyzer Backend

## Running Tests

### Option 1: Run tests in Docker container (Recommended)

Since all dependencies are installed in the Docker container, tests should be run there:

```bash
# Build the container first (if not already built)
BioAnalyzer build

# Run tests in the container
docker exec bioanalyzer-api pytest tests/ -v

# Or use the helper script
./run_tests.sh

# Run with coverage
./run_tests.sh --cov
```

### Option 2: Run specific test files

```bash
# Run a specific test file
docker exec bioanalyzer-api pytest tests/test_utils.py -v

# Run tests matching a pattern
docker exec bioanalyzer-api pytest tests/test_api*.py -v
```

### Option 3: Run tests with coverage report

```bash
docker exec bioanalyzer-api pytest tests/ --cov=app --cov-report=html --cov-report=term
```

This will generate:
- Terminal output with coverage summary
- HTML report in `htmlcov/index.html`

## Test Structure

The test suite is organized as follows:

```
tests/
├── test_utils.py              # Utility function tests
├── test_field_validator.py    # Field validation tests
├── test_text_processing.py   # Text processing tests
├── test_api_utils.py          # API utility tests
├── test_api_endpoints.py      # API endpoint tests
├── test_cache_manager.py      # Cache manager tests
├── test_performance_logger.py # Performance logging tests
└── test_integration.py        # Integration tests
```

## Test Categories

### Unit Tests
- `test_utils.py` - Tests for utility functions
- `test_field_validator.py` - Tests for field validation logic
- `test_text_processing.py` - Tests for text processing
- `test_api_utils.py` - Tests for API utilities
- `test_cache_manager.py` - Tests for cache operations
- `test_performance_logger.py` - Tests for logging

### Integration Tests
- `test_api_endpoints.py` - Tests for API endpoints with mocking
- `test_integration.py` - End-to-end workflow tests

## Running Tests Locally (Not Recommended)

If you want to run tests locally without Docker, you'll need to install all dependencies:

```bash
pip install -r config/requirements.txt
pip install pytest pytest-cov
pytest tests/ -v
```

However, this is **not recommended** as it requires installing PyTorch and other large dependencies locally.

## Test Markers

You can use pytest markers to run specific test categories:

```bash
# Run only unit tests (if markers are added)
docker exec bioanalyzer-api pytest -m unit -v

# Run only integration tests
docker exec bioanalyzer-api pytest -m integration -v
```

## Continuous Integration

For CI/CD pipelines, you can run tests like this:

```bash
docker build -t bioanalyzer-backend .
docker run --rm bioanalyzer-backend pytest tests/ -v --cov=app --cov-report=xml
```

## Troubleshooting

### Import Errors
If you see import errors, make sure:
1. The Docker container is running
2. The container has all dependencies installed
3. You're running tests inside the container, not on the host

### Container Not Found
If the container doesn't exist:
```bash
BioAnalyzer build
BioAnalyzer start
```

### Permission Errors
Make sure the test script is executable:
```bash
chmod +x run_tests.sh
```
