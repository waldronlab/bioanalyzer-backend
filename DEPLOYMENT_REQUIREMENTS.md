# BioAnalyzer Deployment Requirements

System requirements and deployment info for issue #25.

## System Requirements

### Hardware

Minimum setup:
- 2 CPU cores
- 2GB RAM
- 5GB disk space (for Docker image and dependencies)
- Internet access for API calls

Recommended for better performance:
- 4+ CPU cores
- 4GB+ RAM
- 10GB+ disk space (for cache, logs, results)
- Stable internet connection

### Software

You'll need:
- Docker 20.0+ with Docker Compose 2.0+, or Python 3.8+ if not using Docker
- Internet access for NCBI E-utilities API and LLM provider APIs

Optional but useful:
- Redis for caching (SQLite is used by default though)
- Reverse proxy like Nginx or Traefik for production
- SSL/TLS certificates if you need HTTPS

### Dependencies

All dependencies are in the Docker image or `requirements.txt`. Main ones are FastAPI, Uvicorn, LiteLLM, Paper-QA, and PyTorch (CPU version). See `config/requirements.txt` for the full list.

## Deployment Options

### API-Only Deployment

Users don't need CLI access if you're just using the API. The CLI is optional and only useful for command-line analysis, local development, or admin tasks.

For API-only deployment, just run the FastAPI server. No CLI installation needed. Everything works through REST API endpoints, so it can run on Shiny server alongside other services like metaharmonizer.

### CLI Access

You only need CLI access if users want to run analysis from the command line, need it for admin tasks, or for local testing. If you do need it, you'll need a Python environment on the server and run the `install.sh` script, which adds some complexity to the deployment.

## Server Selection: Shiny Server vs Superstudio

### Shiny Server

Good choice for API-only deployment. You can run it alongside other services like metaharmonizer. Deployment is simpler since it's just the API service, and you don't need local LLM installations - it uses external APIs like Gemini or OpenAI. Easier to manage too.

Requirements:
- Docker support or Python 3.8+ environment
- API keys for LLM providers (Gemini works well)
- Port 8000 available (or change it in config)
- Internet access for API calls

Deployment is straightforward:
```bash
docker compose up -d
# or
python main.py --host 0.0.0.0 --port 8000
```

### Superstudio

Use Superstudio if you have local LLM models installed and want to use them, need Ollama or Llamafile for local inference, want to avoid external API costs, or have specific requirements for on-premise LLM access.

Requirements are the same as Shiny Server, plus you'll need local LLM setup (Ollama, Llamafile, etc.) and more resources if you're running local models.

## API Key Requirements

### Required API Keys

You'll need an NCBI API key for PubMed/PMC data access. Get it from https://www.ncbi.nlm.nih.gov/account/settings/. It's free and gives you 3 requests/second rate limit.

For LLM, you need at least one API key. Gemini is recommended and has a free tier. Get it from https://makersuite.google.com/app/apikey. After the free tier it's pay-as-you-go.

OpenAI and Anthropic are optional alternatives. OpenAI keys are at https://platform.openai.com/api-keys, Anthropic at https://console.anthropic.com/. Both are pay-per-use.

### Creating a New API Key

Yes, it's fine to create a new key for BioAnalyzer. Actually, it's better to have a dedicated key. Store it in environment variables or a `.env` file, never commit it to version control, and keep an eye on usage and costs.

### Environment Variables

Create a `.env` file with:
```bash
# Required
NCBI_API_KEY=your_ncbi_key_here
EMAIL=your_email@example.com

# At least one LLM provider
GEMINI_API_KEY=your_gemini_key_here
# OR
OPENAI_API_KEY=your_openai_key_here
# OR
ANTHROPIC_API_KEY=your_anthropic_key_here

# Optional: Local LLM (if using Ollama)
OLLAMA_BASE_URL=http://localhost:11434
LLM_PROVIDER=ollama
```

## Deployment Steps

### Docker Deployment

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

cp .env.example .env
# Edit .env with your API keys

docker compose build
docker compose up -d

curl http://localhost:8000/health
```

### Python Deployment

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r config/requirements.txt
pip install -e .

# Create .env file with your API keys

python main.py --host 0.0.0.0 --port 8000
```

## API Endpoints

Once deployed, you can access:
- Health check: `GET /health`
- API docs: `GET /docs` (Swagger UI)
- Analysis v1: `GET /api/v1/analyze/{pmid}`
- Analysis v2 with RAG: `GET /api/v2/analyze/{pmid}`
- Retrieval: `GET /api/v1/retrieve/{pmid}`
- System status: `GET /api/v1/status`

## Current Status

As @lwaldron mentioned, the app isn't production-ready yet. It needs testing by a couple of people first.

I'd suggest deploying to a staging environment first, have 2-3 users test the API endpoints, monitor for issues, fix any problems, then consider production. Shiny Server might be easier for testing since it's already set up there.

## Testing

Before calling it done, make sure:
- Health endpoint works
- API docs are accessible at `/docs`
- You can analyze a test PMID
- You can retrieve paper data
- Error handling works
- API keys are configured correctly
- Logs are being generated
- Cache works (if enabled)
- Rate limiting works (if enabled)

## Troubleshooting

If something goes wrong:
- Check logs with `docker compose logs` or look in the `logs/` directory
- Verify API keys are set correctly
- Test the health endpoint: `curl http://localhost:8000/health`
- Check network connectivity for API calls
- See [PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md) for more details

