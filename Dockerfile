FROM python:3.11-slim AS builder

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade packaging tools
RUN pip install --upgrade pip setuptools wheel

# Copy dependency files first (better caching)
COPY requirements.txt ./requirements.txt
COPY pyproject.toml setup.py README.md ./

# Install Python dependencies. --timeout/--retries: this layer resolves and
# downloads ~40 packages including multi-hundred-MB torch wheels; on a slow
# or lossy network pip's default 15s read-timeout can time out mid-download
# and get misreported as an unrelated "no matching distribution" resolver
# error rather than a plain network failure - these flags make it retry
# instead of giving up.
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

# Copy application code
COPY app ./app
COPY scripts ./scripts
COPY setup.py pyproject.toml README.md ./

# Install project itself
RUN pip install --no-cache-dir --no-deps .

# Prepare runtime directories
RUN mkdir -p cache logs results models data
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

# This base image ships its own (older) setuptools/wheel. COPY below is
# additive - it won't remove files that aren't in the source - so without
# this step those stock versions survive alongside the builder's upgraded
# ones as duplicate, conflicting dist-info metadata. That left `import
# setuptools` resolving to this image's old, vulnerable 65.5.1
# (CVE-2024-6345, PYSEC-2025-49) at runtime even though the builder stage
# correctly resolved 81.0.0 - confirmed via `python -c "import setuptools;
# print(setuptools.__version__)"` returning 65.5.1 before this fix.
RUN pip uninstall -y setuptools wheel || true

# Copy installed packages + app from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create all runtime directories and make them writable by any user (fixes UID/GID mismatch)
RUN mkdir -p /app/cache /app/logs /app/results /app/models /app/data \
    && chmod -R 777 /app/cache /app/logs /app/results /app/models /app/data

EXPOSE 8000

HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "scripts/main.py", "--host", "0.0.0.0", "--port", "8000"]


# -----------------------------
# TEST IMAGE
# -----------------------------
FROM runtime AS test

ENV PYTHONPATH=/app

WORKDIR /app

# Directories already created + chmod'd in runtime stage above; nothing extra needed

# Install test + dev dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    pytest-asyncio \
    black \
    flake8 \
    mypy \
    defusedxml

# Default command for running the API server (allowing tests via exec)
CMD ["python", "scripts/main.py", "--host", "0.0.0.0", "--port", "8000"]