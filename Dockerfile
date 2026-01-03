# BioAnalyzer Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# FIX: Make Python recognize the application as a package
ENV PYTHONPATH="/app:/app/app"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and README.md first for better caching
COPY pyproject.toml README.md ./

# Upgrade pip and setuptools first
RUN pip install --upgrade pip setuptools wheel build

# ------------------------------------------------------------
# Step 1: Install PyTorch CPU versions (fixed +cpu issue)
# Note: PyTorch CPU versions require special index URL, so we install them separately
# before installing the package from pyproject.toml
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=600 --retries=10 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.0+cpu \
    torchvision==0.16.0+cpu \
    torchaudio==2.1.0+cpu

# ------------------------------------------------------------
# Step 2: Copy application code
# ------------------------------------------------------------
COPY . .

# ------------------------------------------------------------
# Step 3: Install the package from pyproject.toml
# This installs the package and all its dependencies from pyproject.toml
# PyTorch is already installed above, so pip will skip it
# Installing in editable mode (-e) ensures entry points are properly installed
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 -e .

# ------------------------------------------------------------
# Step 4: Install testing dependencies (optional, for development)
# ------------------------------------------------------------
RUN pip install --no-cache-dir pytest>=7.4.0 pytest-cov>=4.1.0

# Create necessary directories
RUN mkdir -p cache logs results

# Make CLI executable
RUN chmod +x cli.py

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set PYTHONPATH for app module imports (fixed nested /app/app issue)
# ENV PYTHONPATH=/app:/app/app

# Default command (can be overridden)
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
