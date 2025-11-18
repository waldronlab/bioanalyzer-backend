# BioAnalyzer Backend Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY config/requirements.txt .

# Upgrade pip first
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies with increased timeout and retries
# Split into two steps: core dependencies first, then paper-qa
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 \
    torch>=2.1.0+cpu \
    torchvision>=0.16.0+cpu \
    torchaudio>=2.1.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    transformers>=4.34.0 \
    scikit-learn>=1.3.0 \
    pandas>=2.1.1 \
    numpy>=1.26.0 \
    biopython>=1.81 \
    sentencepiece>=0.1.99 \
    accelerate>=0.24.0 \
    datasets>=2.14.0 \
    google-generativeai>=0.7.2 \
    tiktoken>=0.5.0 \
    requests>=2.31.0 \
    beautifulsoup4>=4.12.2 \
    lxml>=4.9.0 \
    openpyxl>=3.1.0 \
    xlrd>=2.0.1 \
    tqdm>=4.65.0 \
    python-dotenv>=1.0.0 \
    fastapi>=0.104.0 \
    "uvicorn[standard]>=0.23.2" \
    aiohttp>=3.8.6 \
    websockets>=11.0.3 \
    python-multipart>=0.0.5 \
    aiofiles>=0.7.0 \
    pydantic>=2.4.2 \
    typing-extensions>=3.10.0.2 \
    starlette>=0.31.1 \
    click>=8.0.1 \
    h11>=0.12.0 \
    httptools>=0.3.0 \
    PyYAML>=5.4.1 \
    "watchfiles[watchdog]>=1.0.0" \
    wsproto>=1.0.0 \
    tokenizers>=0.14.1 \
    pytz>=2023.3

# Install paper-qa from PyPI (no local directory needed)
# The code imports from 'paperqa' package, which works with standard pip install
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 paper-qa>=5.0.0

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p cache logs results

# Make CLI executable
RUN chmod +x cli.py

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden)
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
