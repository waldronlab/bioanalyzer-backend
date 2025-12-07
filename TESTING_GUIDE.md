# Testing Guide - Running Tests

## Quick Start: Run a Single Test File

### Option 1: Using Docker (Recommended)

If your container is already running:

```bash
# Run the specific test file
docker exec bioanalyzer-api pytest tests/test_pubmed_retriever_errors.py -v

# Run with more detailed output
docker exec bioanalyzer-api pytest tests/test_pubmed_retriever_errors.py -v -s

# Run a specific test function
docker exec bioanalyzer-api pytest tests/test_pubmed_retriever_errors.py::test_fetch_paper_metadata_handles_no_response -v
```

### Option 2: Using the Test Script

```bash
# Make sure the script is executable
chmod +x run_tests.sh

# Run the specific test file
./run_tests.sh tests/test_pubmed_retriever_errors.py
```

### Option 3: If Container is Not Running

```bash
# Start the container first
BioAnalyzer start

# Then run the test
docker exec bioanalyzer-api pytest tests/test_pubmed_retriever_errors.py -v
```

## Understanding Test Output

### Passing Test
```
tests/test_pubmed_retriever_errors.py::test_fetch_paper_metadata_handles_no_response PASSED
```

### Failing Test
```
tests/test_pubmed_retriever_errors.py::test_fetch_paper_metadata_handles_no_response FAILED
[Error details will be shown]
```

## Useful pytest Flags

- `-v` or `--verbose`: Show detailed output
- `-s`: Show print statements (useful for debugging)
- `-x`: Stop on first failure
- `--tb=short`: Shorter traceback format
- `-k "pattern"`: Run tests matching a pattern

## Example Commands

```bash
# Run with verbose output and show print statements
docker exec bioanalyzer-api pytest tests/test_pubmed_retriever_errors.py -v -s

# Run and stop on first failure
docker exec bioanalyzer-api pytest tests/test_pubmed_retriever_errors.py -v -x

# Run all tests in the tests directory
docker exec bioanalyzer-api pytest tests/ -v

# Run tests matching a pattern
docker exec bioanalyzer-api pytest tests/ -v -k "pubmed"
```

