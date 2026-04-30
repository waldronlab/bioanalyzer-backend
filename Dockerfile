FROM python:3.11-slim

# Set working directory

WORKDIR /app

# Ensure Python can find your app

ENV PYTHONPATH="/app:/app/app"

# Install system dependencies

RUN apt-get update && apt-get install -y \
    gcc g++ curl git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip tools

RUN pip install --upgrade pip setuptools wheel

# Copy dependency files first (better Docker caching)
COPY config/requirements.txt ./config/requirements.txt
COPY pyproject.toml README.md ./

# Install dependencies from centralized requirements file
RUN pip install --no-cache-dir -r config/requirements.txt

# Install package metadata/entrypoints without re-installing dependencies
RUN pip install --no-cache-dir --no-deps .

# Copy the rest of the application

COPY . .

# (Optional) Install in editable mode for dev/CLI usage

# You can remove this in production if not needed

RUN pip install --no-cache-dir --no-deps -e .[dev]

# Create required directories

RUN mkdir -p cache logs results

# Ensure scripts are executable

RUN chmod +x scripts/cli.py || true
RUN chmod +x scripts/*.py || true

# Expose API port

EXPOSE 8000

# Healthcheck

HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

# Start application

CMD ["python", "scripts/main.py", "--host", "0.0.0.0", "--port", "8000"]
