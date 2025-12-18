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

# Copy requirements first for better caching
COPY config/requirements.txt .

# Upgrade pip and setuptools first
RUN pip install --upgrade pip setuptools wheel

# ------------------------------------------------------------
# Step 1: Install PyTorch CPU versions (fixed +cpu issue)
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=600 --retries=10 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.0+cpu \
    torchvision==0.16.0+cpu \
    torchaudio==2.1.0+cpu

# ------------------------------------------------------------
# Step 2: Install ML and NLP packages
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 \
    transformers>=4.34.0 \
    scikit-learn>=1.3.0 \
    pandas>=2.1.1 \
    numpy>=1.26.0 \
    sentencepiece>=0.1.99 \
    accelerate>=0.24.0 \
    datasets>=2.14.0 \
    tiktoken>=0.5.0 \
    tokenizers>=0.14.1

# ------------------------------------------------------------
# Step 3: Install web framework and async packages
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 \
    fastapi>=0.104.0 \
    "uvicorn[standard]>=0.23.2" \
    aiohttp>=3.8.6 \
    websockets>=11.0.3 \
    python-multipart>=0.0.5 \
    aiofiles>=0.7.0 \
    pydantic>=2.4.2 \
    starlette>=0.31.1 \
    httptools>=0.3.0 \
    h11>=0.12.0 \
    wsproto>=1.0.0

# ------------------------------------------------------------
# Step 4: Install utility packages
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 \
    requests>=2.31.0 \
    beautifulsoup4>=4.12.2 \
    lxml>=4.9.0 \
    openpyxl>=3.1.0 \
    xlrd>=2.0.1 \
    tqdm>=4.65.0 \
    python-dotenv>=1.0.0 \
    click>=8.0.1 \
    PyYAML>=5.4.1 \
    watchfiles>=1.0.0 \
    typing-extensions>=3.10.0.2 \
    pytz>=2023.3 \
    biopython>=1.81 \
    google-generativeai>=0.7.2

# ------------------------------------------------------------
# Step 5: Install paper-qa from PyPI
# ------------------------------------------------------------
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 paper-qa>=5.0.0

# ------------------------------------------------------------
# Step 6: Install testing dependencies
# ------------------------------------------------------------
RUN pip install --no-cache-dir pytest>=7.4.0 pytest-cov>=4.1.0

# ------------------------------------------------------------
# Copy application code
# ------------------------------------------------------------
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

# Set PYTHONPATH for app module imports (fixed nested /app/app issue)
# ENV PYTHONPATH=/app:/app/app

# Default command (can be overridden)
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
