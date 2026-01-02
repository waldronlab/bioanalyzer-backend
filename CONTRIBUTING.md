# Contributing to BioAnalyzer Backend

Thank you for your interest in contributing to BioAnalyzer Backend! This document provides guidelines and instructions for contributing to the project.

## Development Setup

### Prerequisites

- Python 3.11+ (recommended)
- Docker (for containerized development)
- Git

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/waldronlab/bioanalyzer-backend.git
   cd bioanalyzer-backend
   ```

2. **Install the package in development mode:**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Set up pre-commit hooks** (see below)

## Pre-commit Hooks

Pre-commit hooks automatically run code quality checks before each commit, ensuring consistent code style and catching issues early.

### Installation

1. **Install pre-commit:**
   ```bash
   pip install pre-commit
   ```

   Or if using Docker:
   ```bash
   docker run --rm -v "$(pwd):/workspace" -w /workspace python:3.11-slim \
     pip install pre-commit
   ```

2. **Install the git hooks:**
   ```bash
   pre-commit install
   ```

   This will install hooks that run automatically on `git commit`.

### Available Hooks

The following hooks are configured in `.pre-commit-config.yaml`:

- **black**: Code formatting (line length: 120)
- **isort**: Import sorting (compatible with black)
- **flake8**: Linting (max line length: 120, ignores E203, W503, E501)
- **mypy**: Type checking (applies to `app/` directory only)
- **bandit**: Security scanning (applies to `app/` directory only)
- **trailing-whitespace**: Removes trailing whitespace
- **end-of-file-fixer**: Ensures files end with a newline
- **check-yaml**: Validates YAML files
- **check-json**: Validates JSON files
- **check-merge-conflict**: Detects merge conflict markers
- **check-case-conflict**: Detects case conflicts in file names
- **check-toml**: Validates TOML files
- **mixed-line-ending**: Normalizes line endings to LF

### Running Hooks Manually

You can run all hooks on all files:

```bash
pre-commit run --all-files
```

Or run a specific hook:

```bash
pre-commit run black --all-files
pre-commit run flake8 --all-files
```

### Updating Hooks

To update hook versions:

```bash
pre-commit autoupdate
```

### Skipping Hooks (Not Recommended)

If you need to skip hooks for a specific commit (not recommended):

```bash
git commit --no-verify -m "Your message"
```

**Note:** This bypasses all quality checks and should only be used in exceptional circumstances.

## Code Style Guidelines

### Python Code

- **Formatting**: Use `black` with 120 character line length
- **Imports**: Use `isort` with black-compatible profile
- **Linting**: Follow `flake8` rules (with configured exceptions)
- **Type Hints**: Use type hints where appropriate; `mypy` will check them

### Example

```python
from typing import Dict, List, Optional

def analyze_paper(pmid: str, options: Optional[Dict] = None) -> Dict[str, Any]:
    """Analyze a paper and return results."""
    # Your code here
    pass
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_specific.py
```

### Writing Tests

- Place tests in the `tests/` directory
- Use descriptive test names
- Follow the existing test patterns
- Ensure tests are independent and can run in any order

## Pull Request Process

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and ensure:
   - Code follows style guidelines
   - All tests pass
   - Pre-commit hooks pass
   - Documentation is updated if needed

3. **Commit your changes:**
   ```bash
   git add .
   git commit -m "Description of your changes"
   ```
   Pre-commit hooks will run automatically.

4. **Push to your fork:**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request** on GitHub

## Code Review Guidelines

- All PRs require at least one approval
- Address review comments promptly
- Keep PRs focused and reasonably sized
- Ensure CI/CD checks pass

## Docker Development

### Building the Docker Image

```bash
docker build -t bioanalyzer-backend .
```

### Running in Docker

```bash
docker run --rm -p 8000:8000 bioanalyzer-backend
```

### Running Pre-commit in Docker

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
  -v ~/.cache/pre-commit:/root/.cache/pre-commit \
  python:3.11-slim bash -c "
    pip install pre-commit && \
    pre-commit run --all-files
  "
```

## Troubleshooting

### Pre-commit Hooks Not Running

1. Verify installation:
   ```bash
   pre-commit --version
   ```

2. Reinstall hooks:
   ```bash
   pre-commit uninstall
   pre-commit install
   ```

### Hook Failures

If a hook fails:

1. **Auto-fixable issues** (black, isort, trailing-whitespace):
   - The hook will attempt to fix them automatically
   - Review the changes and commit again

2. **Manual fixes required** (flake8, mypy, bandit):
   - Fix the issues reported
   - Run the hook again: `pre-commit run <hook-name> --all-files`

### Common Issues

- **"command not found"**: Ensure the tool is installed in your environment
- **"hook failed"**: Check the error message and fix the reported issues
- **Slow hooks**: First run may be slow as hooks download dependencies

## Additional Resources

- [Pre-commit Documentation](https://pre-commit.com/)
- [Black Documentation](https://black.readthedocs.io/)
- [Flake8 Documentation](https://flake8.pycqa.org/)
- [MyPy Documentation](https://mypy.readthedocs.io/)
- [Bandit Documentation](https://bandit.readthedocs.io/)

## Questions?

If you have questions or need help, please:
- Open an issue on GitHub
- Check existing documentation in the `docs/` directory
- Review the codebase for examples

Thank you for contributing! 🎉

