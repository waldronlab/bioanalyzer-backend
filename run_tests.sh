#!/bin/bash
# Run pytest inside Docker (same environment as production / CI).

set -euo pipefail

IMAGE="${BIOANALYZER_IMAGE:-bioanalyzer-package}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🧪 Running BioAnalyzer tests in Docker (${IMAGE})..."

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    echo "📦 Building image..."
    docker build -t "${IMAGE}" "${ROOT}"
fi

echo "🚀 Running pytest..."
docker run --rm \
    -e PYTHONPATH=/app \
    -e GEMINI_API_KEY="${GEMINI_API_KEY:-test_key_1234567890abcdef}" \
    -e NCBI_API_KEY="${NCBI_API_KEY:-test-key}" \
    -e EMAIL="${EMAIL:-test@example.com}" \
    -v "${ROOT}:/app" \
    -w /app \
    "${IMAGE}" \
    pytest tests/ -v "$@"

