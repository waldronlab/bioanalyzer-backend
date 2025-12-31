# Quick Start Guide

Get BioAnalyzer Backend up and running in 5 minutes.

## Prerequisites

You'll need:
- Docker 20.0+ with Docker Compose support (recommended)
- Python 3.8+ (for local installation, optional)
- Internet connection
- Git

## Docker Setup (Recommended)

Works on modern Linux systems.

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

chmod +x install.sh
./install.sh

docker compose build
docker compose up -d

docker compose ps
curl http://localhost:8000/health

export PATH="$PATH:/home/ronald/.local/bin"
BioAnalyzer fields
```

Open http://localhost:8000/docs for API documentation.

## Local Python Setup

Note: This may encounter issues with externally managed Python environments.

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

sudo apt install python3.12-venv python3-full
python3 -m venv .venv
source .venv/bin/activate

# Install package from pyproject.toml (modern Python packaging)
pip install -e .
# Or with development dependencies: pip install -e .[dev]

cat > .env << EOF
NCBI_API_KEY=your_ncbi_key_here
GEMINI_API_KEY=your_gemini_key_here
EMAIL=your_email@example.com
EOF

python main.py
```

## Testing

Docker:
- Visit http://localhost:8000/docs
- Test health: http://localhost:8000/health
- CLI: `BioAnalyzer fields`

Local:
- Visit http://localhost:8000/docs
- Test health: http://localhost:8000/health
- CLI: `python cli.py fields`

## Common Issues

**externally-managed-environment error:**
```bash
# Use Docker (recommended)
docker compose build
docker compose up -d

# OR install python3-venv
sudo apt install python3.12-venv python3-full
```

**docker-compose command not found:**
```bash
# Use newer Docker Compose syntax
docker compose build
docker compose up -d
```

**BioAnalyzer command not found:**
```bash
export PATH="$PATH:/home/ronald/.local/bin"
# Or restart terminal after running ./install.sh
```

**Port already in use:**
```bash
sudo lsof -i :8000
# Use different port in docker-compose.yml or stop other services
```

**API not responding:**
```bash
docker compose ps
docker compose logs
docker compose restart
```

## Verification

- Docker container running
- API responding at http://localhost:8000/health
- CLI commands working (`BioAnalyzer fields`)
- API documentation accessible at http://localhost:8000/docs
- System status shows all green (`BioAnalyzer status`)

## Next Steps

- Read the [Complete Setup Guide](../SETUP_GUIDE.md)
- Explore the [API documentation](http://localhost:8000/docs)
- Test with real PMIDs
- Configure API keys for full functionality

Need help? Check the [troubleshooting section](../README.md#troubleshooting) in the main README. 