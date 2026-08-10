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
# --user matches docker-compose.yml's own "${UID:-1000}:${GID:-1000}" pattern.
# Without it, this container runs as root (the image's build-time default) and
# writes into the bind-mounted repo (cache/, logs/, results/, models/, data/)
# as root - which then leaves those directories permission-denied for the
# non-root user docker-compose.yml explicitly runs the production container
# as, the next time someone does `docker-compose up`. Confirmed reproduced:
# ./data on a real checkout was left root-owned by a prior run of this exact
# script.
docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e PYTHONPATH=/app \
    -e GEMINI_API_KEY="${GEMINI_API_KEY:-test_key_1234567890abcdef}" \
    -e NCBI_API_KEY="${NCBI_API_KEY:-test-key}" \
    -e EMAIL="${EMAIL:-test@example.com}" \
    -e HOME=/tmp \
    -v "${ROOT}:/app" \
    -w /app \
    "${IMAGE}" \
    pytest tests/ -v "$@"

