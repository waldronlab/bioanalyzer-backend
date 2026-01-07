#!/bin/bash
# Fix linting issues using Docker container
# This script fixes trailing whitespace and other formatting issues

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Fixing trailing whitespace and formatting issues..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    python:3.11-slim \
    bash -c "
        # Install tools
        apt-get update -qq && apt-get install -y -qq gcc sed > /dev/null 2>&1 && \
        pip install --quiet --no-cache-dir black>=23.0.0 && \
        
        # Run Black to fix formatting
        echo 'Running Black to fix formatting...' && \
        black app/ tests/ cli.py main.py && \
        
        # Fix trailing whitespace using sed
        echo 'Fixing trailing whitespace...' && \
        find app tests cli.py main.py -name '*.py' -type f -exec sed -i 's/[[:space:]]*$//' {} \; && \
        
        echo '✓ Formatting fixes complete!'
    "

echo "✓ All formatting issues fixed!"

