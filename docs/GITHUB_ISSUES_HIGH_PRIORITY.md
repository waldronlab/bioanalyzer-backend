# High-priority GitHub issues for BioAnalyzer-Backend

Use this list to create GitHub issues so the project is production-ready. **Start with high priority** below; a separate document can list medium/low and nice-to-have issues.

---

## 1. [High] Fail startup when required env vars are missing in production

**Title:** Fail application startup when required env vars are missing in production

**Labels:** `high priority`, `configuration`, `production`

**Description:**

Currently `validate_env_vars()` and `check_required_vars()` in `app/utils/config.py` only print warnings when `NCBI_API_KEY`, `EMAIL`, or LLM keys are missing. The app still starts, which leads to runtime errors and confusing health/analysis failures.

**Acceptance criteria:**

- When `ENVIRONMENT=production` (or a dedicated `STRICT_ENV=true`), the application **exits with a non-zero code** at startup if any of the required vars are missing: `NCBI_API_KEY`, `EMAIL`, and at least one LLM key (e.g. `GEMINI_API_KEY`).
- Log a clear message listing the missing variables and how to set them (e.g. `.env` or export).
- In development (default or `ENVIRONMENT=development`), keep current behavior (warn but do not exit).

**Files to consider:** `app/utils/config.py`, `main.py`, Docker `CMD`/entrypoint.

---

## 2. [High] Document and fix backend container crash on start (health never ready)

**Title:** Backend container enters Restarting state; /health never reports healthy

**Labels:** `high priority`, `docker`, `bug`

**Description:**

Users report that after `BioAnalyzer start`, the package container is in "Restarting" state and `/health` never succeeds within the 60s timeout, so the start flow fails or the system appears broken.

**Tasks:**

- Add a troubleshooting section to the README or SETUP_GUIDE: run `docker logs bioanalyzer-package` and interpret common errors (missing `.env` in container, permission errors on `cache/` or `logs/`, import errors).
- Ensure `docker-compose.yml` (and CLI start flow) passes `.env` into the backend container so `NCBI_API_KEY`, `GEMINI_API_KEY`, `EMAIL` are available.
- Optionally: improve health check or startup so the container exits quickly with a clear error if required config is missing, instead of crash-looping.

**Acceptance criteria:**

- README or docs explain how to diagnose "container Restarting" and "health not ready".
- New users following the Quick Start can get a healthy `/health` after `BioAnalyzer start` when `.env` is correctly set.

---

## 3. [High] Pin paper-qa and other critical dependencies for stable CI and installs

**Title:** Pin paper-qa and other critical dependency versions for stable builds

**Labels:** `high priority`, `dependencies`, `ci`

**Description:**

CI and local installs can break when upstream packages change (e.g. `QdrantVectorStore` removed from `paperqa.llms`). We already made the import optional in code, but unpinned versions still cause unpredictable failures.

**Tasks:**

- Pin `paper-qa` to a known-good version in `pyproject.toml` and `config/requirements.txt` (e.g. the version that provides the API currently used).
- Optionally pin other critical dependencies (e.g. `litellm`, `google-generativeai`, `fastapi`, `uvicorn`) to minor versions to avoid surprise breakage.
- Document in CONTRIBUTING or README how to update pins after testing.

**Acceptance criteria:**

- `pip install -e .` and CI install the same major/minor (or exact) versions for paper-qa and any other pinned deps.
- CI passes consistently for the pinned set; release process mentions updating pins.

---

## 4. [High] Remove or use Redis in docker-compose

**Title:** Either use Redis in the app or remove it from docker-compose

**Labels:** `high priority`, `docker`, `architecture`

**Description:**

`docker-compose.yml` defines a `redis` service and the backend `depends_on: redis`. The application code does not use Redis; rate limiting is in-memory (see `app/api/middleware/rate_limit.py`: "use Redis in production"). This adds unnecessary complexity and a dependency that can affect startup/health if Redis is ever required later but not configured.

**Options (choose one and implement):**

- **A)** Remove `redis` from `docker-compose.yml` and `depends_on` so the backend starts without Redis; document that rate limiting is in-memory and that multi-instance production should add Redis later.
- **B)** Implement Redis-backed rate limiting and document `REDIS_URL` (or similar) for production.

**Acceptance criteria:**

- docker-compose and docs are consistent: either Redis is used and documented, or it is removed and the app runs without it.

---

## 5. [High] Harden /health and startup so Docker healthcheck passes reliably

**Title:** Harden /health and startup so Docker healthcheck passes reliably

**Labels:** `high priority`, `docker`, `reliability`

**Description:**

The Docker healthcheck runs `curl -f http://localhost:8000/health` with a 40s start period. If the app is slow to start (heavy imports, LLM/NCBI checks), the container can be marked unhealthy and restarted even though the app would have been fine.

**Tasks:**

- Ensure `/health` is lightweight (no external API calls, minimal dependencies); optional: add a `/health/ready` that does dependency checks if needed.
- Consider increasing `start_period` or retries in `docker-compose.yml` if startup is legitimately slow, and document expected startup time.
- Ensure the app does not block startup on optional services (e.g. LLM) so that `/health` can return 200 as soon as the process is up.

**Acceptance criteria:**

- A fresh `docker compose up` (or `BioAnalyzer start`) results in the backend container becoming healthy within the configured timeout when env and resources are correct.
- Health endpoint response time is documented or measured so operators know what to expect.

---

## 6. [High] Validate and document .env loading in Docker

**Title:** Validate and document .env loading for Docker/CLI start

**Labels:** `high priority`, `documentation`, `docker`

**Description:**

Backend containers may not have access to `.env` (e.g. when started via CLI or from a different working directory). Users see "Environment variables will be loaded from .env only" but the container can still start without those vars, leading to failed analyses and unclear errors.

**Tasks:**

- Document in README/SETUP_GUIDE: where to place `.env` and how Docker Compose and the CLI pass it into the backend container (e.g. `env_file: .env` in compose, and that compose is run from project root).
- Optionally: add a startup check in the container that logs clearly if required vars are missing (and, if combined with issue #1, exit in production).

**Acceptance criteria:**

- Docs state explicitly that `.env` must be in the project root and that `docker compose` / `BioAnalyzer start` are run from that root so the backend receives the file.
- One sentence or bullet on "if analyses fail with auth errors, check that the container has API keys" with a link to env/docs.

---

## 7. [High] Add security headers and CORS documentation for production

**Title:** Add security headers and document CORS for production

**Labels:** `high priority`, `security`, `production`

**Description:**

Production deployments behind a reverse proxy or with a separate frontend need correct CORS and security headers. Currently CORS is configurable via config; security headers (e.g. X-Content-Type-Options, X-Frame-Options, CSP) are not explicitly set.

**Tasks:**

- Add middleware or document how to set security headers (e.g. in Nginx/Traefik or in FastAPI) for production.
- Document `CORS_ORIGINS` and recommended production values (e.g. no `*` in production) in DEPLOYMENT_REQUIREMENTS or PRODUCTION_DEPLOYMENT.

**Acceptance criteria:**

- Production deployment docs describe how to configure CORS and at least one way to add security headers.
- No default CORS `*` when `ENVIRONMENT=production` (or document that it must be overridden).

---

## 8. [High] Duplicate pyarrow in config/requirements.txt

**Title:** Remove duplicate pyarrow entry in config/requirements.txt

**Labels:** `high priority`, `dependencies`, `cleanup`

**Description:**

`config/requirements.txt` lists `pyarrow>=14.0.0` twice (lines 65–66). This is redundant and can confuse dependency resolvers or audit tools.

**Acceptance criteria:**

- Single `pyarrow>=14.0.0` line in `config/requirements.txt`.
- CI and local install unchanged.

---

## 9. [High] Add defusedxml to config/requirements.txt if not present

**Title:** Ensure defusedxml is in config/requirements.txt for XML parsing

**Labels:** `high priority`, `dependencies`, `security`

**Description:**

The codebase uses `defusedxml` for safe parsing of PubMed/PMC XML in `app/services/data_retrieval.py` and `app/services/standalone_pubmed_retriever.py`. If `defusedxml` is only in `pyproject.toml`, Docker or installs that use only `config/requirements.txt` may miss it and fall back to stdlib XML (or fail at import).

**Tasks:**

- Ensure `defusedxml>=0.7.1` (or current minimum) is in both `pyproject.toml` and `config/requirements.txt`.
- Confirm CI and Docker build install it.

**Acceptance criteria:**

- Both dependency files include defusedxml; no import errors in production or CI.

---

## 10. [High] Unify API base URL and port configuration

**Title:** Unify API base URL and port configuration (no hardcoded localhost:8000)

**Labels:** `high priority`, `configuration`, `maintainability`

**Description:**

The CLI and some scripts hardcode `http://localhost:8000` in multiple places (e.g. health checks, analyze, qa). This makes it hard to run the API on a different host/port or behind a proxy.

**Tasks:**

- Use a single config source for the API base URL (e.g. `BIOANALYZER_API_URL` or from existing config) everywhere the CLI and scripts call the API.
- Document the env var in README and .env.example so users can point to a different API instance.

**Acceptance criteria:**

- No hardcoded `http://localhost:8000` in CLI/scripts; one env var (or config) controls the API URL.
- README and .env.example document it.

---

## Summary table (high priority)

| # | Title (short) | Focus |
|---|----------------|--------|
| 1 | Fail startup when required env missing (production) | Config, production |
| 2 | Document and fix backend container crash / health not ready | Docker, docs, bug |
| 3 | Pin paper-qa and critical dependencies | Dependencies, CI |
| 4 | Remove or use Redis in docker-compose | Docker, architecture |
| 5 | Harden /health and startup for Docker healthcheck | Docker, reliability |
| 6 | Validate and document .env loading in Docker | Docs, Docker |
| 7 | Security headers and CORS for production | Security, production |
| 8 | Remove duplicate pyarrow in requirements | Dependencies, cleanup |
| 9 | Add defusedxml to config/requirements.txt | Dependencies, security |
| 10 | Unify API base URL/port configuration | Config, maintainability |

---

**Next steps:** Create these issues in your GitHub repo (copy title and description into new issues). If you want, I can generate a second document with **medium** and **low** priority issues (e.g. tests, docs, code quality, optional features).
