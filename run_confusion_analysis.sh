#!/bin/bash
# Helper script to run confusion matrix analysis in Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PREDICTIONS_FILE="${1:-analysis_results.csv}"
FEEDBACK_FILE="${2:-feedback.csv}"

echo "=========================================="
echo "BioAnalyzer Confusion Matrix Analysis"
echo "=========================================="
echo ""
echo "Predictions file: $PREDICTIONS_FILE"
echo "Feedback file: $FEEDBACK_FILE"
echo ""

# Check if files exist
if [ ! -f "$PREDICTIONS_FILE" ]; then
    echo "Error: Predictions file not found: $PREDICTIONS_FILE"
    exit 1
fi

if [ ! -f "$FEEDBACK_FILE" ]; then
    echo "Error: Feedback file not found: $FEEDBACK_FILE"
    exit 1
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Build the Docker image if it doesn't exist or is outdated
echo "Building/checking Docker image..."
docker build -t bioanalyzer-backend . > /dev/null 2>&1 || {
    echo "Building Docker image (this may take a few minutes)..."
    docker build -t bioanalyzer-backend .
}

echo ""
echo "Step 1: Checking PMID overlap..."
docker run --rm \
    -v "$SCRIPT_DIR:/app" \
    -w /app \
    bioanalyzer-backend \
    python align_pmids.py "$PREDICTIONS_FILE" "$FEEDBACK_FILE"

echo ""
echo "Step 2: Running confusion matrix analysis..."
docker run --rm \
    -v "$SCRIPT_DIR:/app" \
    -w /app \
    bioanalyzer-backend \
    python confusion_matrix_analysis.py "$PREDICTIONS_FILE" "$FEEDBACK_FILE"

echo ""
echo "=========================================="
echo "Analysis complete! Check confusion_matrix_results/ for output"
echo "=========================================="
