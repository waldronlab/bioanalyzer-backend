# BioAnalyzer Docker Deployment Guide

Instructions for deploying BioAnalyzer using Docker and Docker Compose.

## Prerequisites

- Docker 20.0+
- Docker Compose 2.0+ (or the `docker compose` plugin)
- At least 4GB RAM available
- At least 10GB disk space

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd BioAnalyzer-Backend

chmod +x install.sh
./install.sh
```

`install.sh` installs the global `BioAnalyzer` CLI wrapper, which delegates
into this repo's `scripts/cli.py` and drives Docker for you (see below).
Alternatively, `./docker-setup.sh` builds and smoke-tests the
`bioanalyzer-package` image directly without installing the wrapper.

### 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

At minimum set `NCBI_API_KEY`, `EMAIL`, and one LLM provider key (see
`.env.example` for the full list of supported variables - Gemini, OpenAI,
Anthropic, and Ollama are all supported via `LLM_PROVIDER`).

### 3. Start Services

Recommended (via the `BioAnalyzer` CLI wrapper, which builds the image,
brings up `docker-compose.yml`, and waits for the health check):

```bash
BioAnalyzer build
BioAnalyzer start
BioAnalyzer status
```

Or manually with Docker Compose directly:

```bash
# Default (development) compose file
docker compose up -d

# Production compose file (adds resource limits and log rotation)
docker compose -f docker-compose.prod.yml up -d
```

### 4. Verify Deployment

```bash
curl http://localhost:8000/health
BioAnalyzer status
docker compose logs -f
```

## Architecture Overview

The real deployment is two containers - the FastAPI app and Redis. There is
no Nginx, PostgreSQL, or Prometheus in this repo's Docker setup (an earlier
version of this doc described a larger topology that was never built; this
reflects `docker-compose.yml`/`docker-compose.prod.yml` as they actually
are).

```
┌─────────────────────────┐
│   bioanalyzer-package    │
│   FastAPI app (8000)     │
│   /health  /docs  /metrics │
└────────────┬─────────────┘
             │ depends_on (healthy)
             ▼
┌─────────────────────────┐
│         Redis            │
│      (port 6379)         │
└─────────────────────────┘
```

**Important:** Redis is provisioned by both compose files, but it is not
currently wired into the application's caching logic - BioAnalyzer's actual
cache is SQLite-backed (`cache/analysis_cache.db`, see
`app/services/cache_manager.py`). Redis runs but is otherwise idle today;
don't assume cache reads/writes touch it.

## Configuration Files

### Docker Compose Files

- `docker-compose.yml` - default/development configuration. App + Redis,
  bind-mounts `cache/`, `logs/`, `results/`, `models/`, `tests/`, and `app/`
  for live iteration.
- `docker-compose.prod.yml` - production configuration. Same two services,
  plus CPU/memory limits and reservations, and bounded JSON-file log
  rotation. No bind mounts of source code.

There is no `docker-compose.dev.yml` - the default `docker-compose.yml`
*is* the development file.

### Other Relevant Files

- `Dockerfile` - multi-stage build for the `bioanalyzer-package` image.
- `docker-setup.sh` - builds the image directly (`docker build`) and runs a
  smoke test, independent of Compose or the `BioAnalyzer` CLI wrapper.
- `install.sh` - installs the global `BioAnalyzer` CLI wrapper (see
  `BioAnalyzer` at the repo root), which wraps `docker build`/`docker
  compose` for the `build`/`start`/`stop`/`restart`/`status` subcommands.

## Service Configuration

### FastAPI Application (`bioanalyzer-package`)

- **Port:** 8000
- **Health check:** `GET /health` (used by Docker's own `healthcheck:` and
  by `BioAnalyzer status`)
- **Metrics:** `GET /metrics` - returns a JSON payload of app-level metrics
  (request counts, response times, cache hit rate, basic system resource
  usage via `psutil`). This is not a Prometheus-format scrape endpoint;
  there is no Prometheus deployed alongside it.
- **API docs:** `GET /docs` (FastAPI's automatic OpenAPI UI)
- **Runs as:** a non-root user, `${UID:-1000}:${GID:-1000}` (matches your
  host user by default so bind-mounted volumes aren't root-owned)

### Redis

- **Image:** `redis:7-alpine`, AOF persistence enabled
- **Port:** 6379
- Provisioned for future use; not currently read from or written to by the
  application (see the caching note above)

## Health Checks

```bash
# Application
curl http://localhost:8000/health

# Redis
docker exec bioanalyzer-redis redis-cli ping
```

Both services also have Docker-native `healthcheck:` blocks (the app polls
`/health` via `curl`; Redis uses `redis-cli ping`), visible in `docker
compose ps` and `docker inspect`.

## Logging

- **Driver:** JSON file (Docker's default), explicitly configured in
  `docker-compose.prod.yml`: app logs rotate at 10MB x 5 files, Redis logs
  rotate at 10MB x 3 files. The default `docker-compose.yml` doesn't pin
  rotation explicitly and uses Docker's defaults.
- **App logs:** also written to the bind-mounted `logs/` directory
  (separate from container stdout/stderr).

```bash
docker compose logs -f                      # all services
docker compose logs -f bioanalyzer-package  # app only
docker stats                                # live resource usage
```

## Security Notes

- The app container runs as a non-root user (see above).
- Secrets (API keys) are supplied via `.env`, never baked into the image.
- `app/utils/credential_masking.py` scrubs API keys/secrets from logs and
  error responses before they're written or returned - this applies
  regardless of how the app is deployed.
- There's no reverse proxy in front of the app in this repo's Docker setup;
  if you put one in front of it for TLS/rate-limiting in your own
  deployment, that's infrastructure you're adding, not something this repo
  configures for you.

## Resource Limits (production)

`docker-compose.prod.yml` sets CPU/memory limits and reservations per
service rather than configuring horizontal scaling or a load balancer
(neither exists in this repo's Docker setup):

- **App:** limit 2 CPU / 4GB RAM, reservation 1 CPU / 2GB RAM
- **Redis:** limit 0.5 CPU / 1GB RAM, reservation 0.25 CPU / 512MB RAM

## Troubleshooting

### Service won't start

```bash
docker compose logs bioanalyzer-package
docker compose ps
docker compose restart bioanalyzer-package
```

### Health check failing

```bash
curl -v http://localhost:8000/health
docker inspect bioanalyzer-package | grep -A 10 Health
```

If the app container is up but unhealthy, check `docker compose logs` for a
missing required env var (`NCBI_API_KEY`, `EMAIL`, or an LLM provider key) -
the app will start but the health check can still fail if it can't
initialize a required client.

### Port conflicts

```bash
sudo lsof -i :8000
sudo lsof -i :6379
```

Change the host-side port mapping in your compose file's `ports:` section
if either is already in use (e.g. `"8080:8000"`).

### Debug mode

```bash
LOG_LEVEL=debug docker compose up
docker exec -it bioanalyzer-package bash
```

## Maintenance

```bash
# Pull a newer base image / rebuild after a Dockerfile change
docker compose build --no-cache
docker compose up -d

# Stop everything
docker compose down

# Stop and also remove the Redis volume (Redis isn't used for persisted
# app data today, so this is safe; cache/results/logs live in the
# bind-mounted host directories, not in the Redis volume)
docker compose down -v
```

The data that actually matters for BioAnalyzer - the SQLite analysis
cache, logs, and analysis results - lives in the bind-mounted `cache/`,
`logs/`, and `results/` directories on the host, not in a Docker volume.
Back those directories up directly if you need to.

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [BioAnalyzer-Backend Issues](https://github.com/waldronlab/bioanalyzer-backend/issues)
