#!/bin/bash
# Format code using Black in Docker container
# Usage: ./scripts/format_code.sh [--check]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [ "$1" == "--check" ]; then
    echo "Checking code formatting with Black..."
    docker run --rm \
        -v "$PROJECT_ROOT:/workspace" \
        -w /workspace \
        python:3.11-slim \
        bash -c "
            apt-get update -qq && apt-get install -y -qq gcc > /dev/null 2>&1 && \
            pip install --quiet --no-cache-dir black>=23.0.0 && \
            black --check app/ tests/ scripts/cli.py scripts/main.py
        "
    echo "✓ All files are properly formatted!"
else
    echo "Formatting code with Black..."
    docker run --rm \
        -v "$PROJECT_ROOT:/workspace" \
        -w /workspace \
        python:3.11-slim \
        bash -c "
            apt-get update -qq && apt-get install -y -qq gcc > /dev/null 2>&1 && \
            pip install --quiet --no-cache-dir black>=23.0.0 && \
            black app/ tests/ scripts/cli.py scripts/main.py
        "
    echo "✓ Code formatted successfully!"
fi

