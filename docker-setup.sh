#!/bin/bash
# BioAnalyzer Package Docker Setup Script

set -e

echo "🐳 BioAnalyzer Package Docker Setup"
echo "===================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_warning "Docker Compose not found. Using docker compose instead."
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

print_status "Cleaning up existing containers and images..."

# Stop and remove existing containers
docker stop $(docker ps -aq --filter "name=bioanalyzer") 2>/dev/null || true
docker rm $(docker ps -aq --filter "name=bioanalyzer") 2>/dev/null || true

# Remove existing images
docker rmi bioanalyzer-package 2>/dev/null || true

print_status "Building BioAnalyzer Package Docker image..."

# Build the Docker image
docker build -t bioanalyzer-package .

if [ $? -eq 0 ]; then
    print_success "Docker image built successfully!"
else
    print_error "Failed to build Docker image"
    exit 1
fi

print_status "Testing Docker image..."

# Test the image with a simple command
docker run --rm bioanalyzer-package python scripts/dev/cli_smoke_check.py

if [ $? -eq 0 ]; then
    print_success "Docker image test passed!"
else
    print_warning "Docker image test had issues, but continuing..."
fi

echo ""
echo "🚀 Docker Setup Complete!"
echo "========================"
echo ""
echo "Available commands:"
echo ""
echo "1. Start API Server:"
echo "   docker run -d --name bioanalyzer-api -p 8000:8000 bioanalyzer-package"
echo ""
echo "2. Use CLI (interactive):"
echo "   docker run -it --rm bioanalyzer-package python scripts/cli.py fields"
echo "   docker run -it --rm bioanalyzer-package python scripts/cli.py analyze 12345678"
echo ""
echo "3. Use CLI with custom command:"
echo "   docker run --rm bioanalyzer-package python scripts/cli.py analyze --help"
echo ""
echo "4. Start with Docker Compose:"
echo "   $COMPOSE_CMD up -d"
echo ""
echo "5. View logs:"
echo "   docker logs bioanalyzer-api"
echo ""
echo "6. Stop and remove:"
echo "   docker stop bioanalyzer-api && docker rm bioanalyzer-api"
echo ""

# Ask if user wants to start the container
read -p "Would you like to start the API server now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Starting BioAnalyzer Package API server..."
    docker run -d --name bioanalyzer-api -p 8000:8000 bioanalyzer-package
    
    if [ $? -eq 0 ]; then
        print_success "API server started successfully!"
        echo ""
        API_URL="${BIOANALYZER_API_URL:-http://localhost:8000}"
        # If user set BIOANALYZER_API_URL to include /api/v1, strip it for root endpoints.
        API_ROOT="${API_URL%/}"
        API_ROOT="${API_ROOT%/api/v1}"
        echo "🌐 API available at: ${API_ROOT}"
        echo "📚 Documentation: ${API_ROOT}/docs"
        echo "🔍 Health check: ${API_ROOT}/health"
        echo ""
        echo "To view logs: docker logs bioanalyzer-api"
        echo "To stop: docker stop bioanalyzer-api"
    else
        print_error "Failed to start API server"
        exit 1
    fi
fi

print_success "Setup complete! 🎉"
