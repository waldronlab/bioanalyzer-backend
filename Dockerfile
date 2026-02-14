FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH="/app:/app/app"

RUN apt-get update && apt-get install -y \
    gcc g++ curl git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

RUN pip install --upgrade pip setuptools wheel build

# Install PyTorch CPU wheels
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.0+cpu torchvision==0.16.0+cpu torchaudio==2.1.0+cpu

COPY . .

# Install package + dependencies (including dev extras for pytest in test container)
RUN pip install --no-cache-dir -e .[dev]

# Explicit analysis deps (defensive)
RUN pip install --no-cache-dir pandas scikit-learn matplotlib seaborn

RUN mkdir -p cache logs results

RUN chmod +x cli.py || true
RUN chmod +x scripts/*.py || true

EXPOSE 8000

HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
