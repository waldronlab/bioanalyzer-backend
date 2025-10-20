#!/bin/bash
# BioAnalyzer Backend Docker Setup Script

set -e

echo "🐳 BioAnalyzer Backend Docker Setup"
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
docker rmi bioanalyzer-backend 2>/dev/null || true

print_status "Building BioAnalyzer Backend Docker image..."

# Build the Docker image
docker build -t bioanalyzer-backend .

if [ $? -eq 0 ]; then
    print_success "Docker image built successfully!"
else
    print_error "Failed to build Docker image"
    exit 1
fi

print_status "Testing Docker image..."

# Test the image with a simple command
docker run --rm bioanalyzer-backend python test_cli.py

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
echo "   docker run -d --name bioanalyzer-api -p 8000:8000 bioanalyzer-backend"
echo ""
echo "2. Use CLI (interactive):"
echo "   docker run -it --rm bioanalyzer-backend python cli.py fields"
echo "   docker run -it --rm bioanalyzer-backend python cli.py analyze 12345678"
echo ""
echo "3. Use CLI with custom command:"
echo "   docker run --rm bioanalyzer-backend python cli.py analyze --help"
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
    print_status "Starting BioAnalyzer Backend API server..."
    docker run -d --name bioanalyzer-api -p 8000:8000 bioanalyzer-backend
    
    if [ $? -eq 0 ]; then
        print_success "API server started successfully!"
        echo ""
        echo "🌐 API available at: http://localhost:8000"
        echo "📚 Documentation: http://localhost:8000/docs"
        echo "🔍 Health check: http://localhost:8000/health"
        echo ""
        echo "To view logs: docker logs bioanalyzer-api"
        echo "To stop: docker stop bioanalyzer-api"
    else
        print_error "Failed to start API server"
        exit 1
    fi
fi

print_success "Setup complete! 🎉"
