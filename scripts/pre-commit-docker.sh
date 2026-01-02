#!/bin/bash
# Helper script to run pre-commit hooks using Docker
# Usage: ./scripts/pre-commit-docker.sh [hook-name]

set -e

# Get the hook name from argument (optional)
HOOK_NAME="${1:-}"

# Build the pre-commit command
if [ -z "$HOOK_NAME" ]; then
    CMD="pre-commit run --all-files"
else
    CMD="pre-commit run $HOOK_NAME --all-files"
fi

# Run pre-commit in Docker
docker run --rm \
    -v "$(pwd):/workspace" \
    -w /workspace \
    -v ~/.cache/pre-commit:/root/.cache/pre-commit \
    python:3.11-slim \
    bash -c "pip install --quiet pre-commit && $CMD"

