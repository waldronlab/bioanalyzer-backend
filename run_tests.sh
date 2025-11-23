#!/bin/bash
# Script to run tests in Docker container

echo "🧪 Running BioAnalyzer tests in Docker container..."

# Check if container is running
if ! docker ps | grep -q bioanalyzer-api; then
    echo "📦 Container not running. Building and starting..."
    docker build -t bioanalyzer-backend . || exit 1
    docker run -d --name bioanalyzer-api-test \
        -v "$(pwd)/tests:/app/tests" \
        -v "$(pwd)/app:/app/app" \
        bioanalyzer-backend \
        tail -f /dev/null
    sleep 2
fi

# Run tests with PYTHONPATH set
echo "🚀 Running pytest..."
docker exec -e PYTHONPATH=/app bioanalyzer-api-test pytest tests/ -v "$@"

# Optional: Run with coverage
if [[ "$1" == "--cov" ]]; then
    echo "📊 Running with coverage..."
    docker exec bioanalyzer-api-test pytest tests/ --cov=app --cov-report=html --cov-report=term "$@"
fi

