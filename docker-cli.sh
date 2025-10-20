#!/bin/bash
# BioAnalyzer CLI Docker Runner

# Default image name
IMAGE_NAME="bioanalyzer-backend"

# Function to show usage
show_usage() {
    echo "BioAnalyzer CLI Docker Runner"
    echo "=============================="
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  fields                           Show BugSigDB field information"
    echo "  analyze [PMID]                   Analyze a single paper"
    echo "  analyze --batch [PMID1,PMID2]   Analyze multiple papers"
    echo "  analyze --file [FILE]            Analyze papers from file"
    echo "  help                             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 fields"
    echo "  $0 analyze 12345678"
    echo "  $0 analyze --batch 12345678,87654321"
    echo "  $0 analyze --file pmids.txt"
    echo "  $0 analyze 12345678 --format json"
    echo ""
    echo "Options:"
    echo "  --format [table|json|csv]  Output format (default: table)"
    echo "  --output [FILE]              Save results to file"
    echo "  --verbose                    Verbose output"
    echo "  --max-concurrent [N]         Max concurrent analyses (default: 5)"
    echo ""
}

# Check if Docker image exists
if ! docker image inspect $IMAGE_NAME >/dev/null 2>&1; then
    echo "❌ Docker image '$IMAGE_NAME' not found."
    echo "Please run './docker-setup.sh' first to build the image."
    exit 1
fi

# If no arguments provided, show usage
if [ $# -eq 0 ]; then
    show_usage
    exit 0
fi

# Build Docker command
DOCKER_CMD="docker run --rm -it"

# Add volume mounts for file operations
if [[ "$*" == *"--file"* ]]; then
    # Mount current directory for file access
    DOCKER_CMD="$DOCKER_CMD -v $(pwd):/workspace -w /workspace"
fi

# Add volume mounts for output files
if [[ "$*" == *"--output"* ]]; then
    # Mount current directory for output files
    DOCKER_CMD="$DOCKER_CMD -v $(pwd):/workspace -w /workspace"
fi

# Execute the command
echo "🐳 Running BioAnalyzer CLI in Docker..."
echo "Command: python cli.py $*"
echo ""

$DOCKER_CMD $IMAGE_NAME python cli.py "$@"
