FROM python:3.11-slim AS builder

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade packaging tools
RUN pip install --upgrade pip setuptools wheel

# Copy dependency files first (better caching)
COPY config/requirements.txt ./config/requirements.txt
COPY pyproject.toml setup.py README.md ./

# Install Python dependencies
RUN pip install --no-cache-dir -r config/requirements.txt

# Copy application code
COPY app ./app
COPY scripts ./scripts
COPY setup.py pyproject.toml README.md ./

# Install project itself
RUN pip install --no-cache-dir --no-deps .

# Prepare runtime directories
RUN mkdir -p cache logs results
RUN chmod +x scripts/cli.py || true
RUN chmod +x scripts/*.py || true


# -----------------------------
# RUNTIME IMAGE
# -----------------------------
FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages + app from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

RUN mkdir -p cache logs results

EXPOSE 8000

HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "scripts/main.py", "--host", "0.0.0.0", "--port", "8000"]


# -----------------------------
# TEST IMAGE
# -----------------------------
FROM runtime AS test

ENV PYTHONPATH=/app

WORKDIR /app

# Install test + dev dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    pytest-asyncio \
    black \
    flake8 \
    mypy \
    defusedxml

# Default command for running tests
CMD ["pytest", "-v"]