# Production Deployment Guide

Guide for deploying BioAnalyzer Backend to production with best practices for security, performance, and maintainability.

## Prerequisites

### Required
- Docker 20.0+ and Docker Compose 2.0+
- At least 4GB RAM
- 20GB+ disk space
- NCBI API key
- At least one LLM API key (Gemini, OpenAI, or Anthropic)

### Recommended
- Reverse proxy (Nginx, Traefik, or Cloud Load Balancer)
- SSL/TLS certificates
- Monitoring solution (Prometheus, Grafana, or cloud monitoring)
- Log aggregation (ELK stack, CloudWatch, or similar)

## Environment Configuration

### 1. Create `.env` File

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### 2. Required Configuration

```bash
# Required API Keys
NCBI_API_KEY=your_ncbi_api_key
EMAIL=your_email@example.com (This is not so much crucial)

# At least one LLM provider
GEMINI_API_KEY=your_gemini_key
# OR
OPENAI_API_KEY=your_openai_key
# OR
ANTHROPIC_API_KEY=your_anthropic_key

# Production Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
UVICORN_RELOAD=false
UVICORN_WORKERS=4  # Adjust based on CPU cores

# Security
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
ENABLE_RATE_LIMITING=true
RATE_LIMIT_PER_MINUTE=60
```

### 3. Production-Specific Settings

```bash
# Performance
API_TIMEOUT=30
ANALYSIS_TIMEOUT=45
MAX_CONCURRENT_REQUESTS=10

# Caching
CACHE_VALIDITY_HOURS=24
MAX_CACHE_SIZE=5000

# RAG Configuration (if using v2 API)
RAG_SUMMARY_LENGTH=medium
RAG_SUMMARY_QUALITY=balanced
RAG_RERANK_METHOD=hybrid
```

## Docker Production Setup

### 1. Build Production Image

```bash
docker build -t bioanalyzer-backend:latest .
```

### 2. Run with Docker Compose

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 3. Verify Deployment

```bash
# Check container status
docker compose ps

# Check logs
docker compose logs -f bioanalyzer-backend

# Test health endpoint
curl http://localhost:8000/health
```

## Security Considerations

### 1. CORS Configuration

**Never use `CORS_ORIGINS=*` in production!**

```bash
# Good
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Bad
CORS_ORIGINS=*
```

### 2. API Keys Security

- **Never commit `.env` files to version control**
- Use secrets management (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate API keys regularly
- Use different keys for different environments

### 3. Network Security

- Use reverse proxy with SSL/TLS
- Restrict container network access
- Use firewall rules to limit access
- Enable rate limiting

### 4. Input Validation

The API includes input validation for:
- PMID format (numeric, 1-20 digits)
- Request payloads (Pydantic models)
- URL parameters

### 5. Rate Limiting

Rate limiting is enabled by default:
- 60 requests per minute per IP
- Configurable via `RATE_LIMIT_PER_MINUTE`
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

## Performance Optimization

### 1. Worker Configuration

For production, use multiple workers:

```bash
UVICORN_WORKERS=4  # 2-4x CPU cores
```

Update `main.py` or use gunicorn:

```bash
gunicorn app.api.app:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### 2. Caching Strategy

- Enable SQLite caching (default)
- Set appropriate `CACHE_VALIDITY_HOURS`
- Monitor cache hit rates
- Consider Redis for distributed caching

### 3. Database Optimization

- Regular SQLite VACUUM operations
- Monitor cache size (`MAX_CACHE_SIZE`)
- Implement cache cleanup jobs

### 4. Resource Limits

Set Docker resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 4G
    reservations:
      cpus: '1'
      memory: 2G
```

## Monitoring and Logging

### 1. Log Management

Logs are automatically rotated:
- Main log: `logs/bioanalyzer.log`
- Performance log: `logs/performance.log`
- Error log: `logs/errors.log`
- API log: `logs/api_calls.log`

### 2. Health Checks

Monitor these endpoints:
- `/health` - Basic health check
- `/api/v1/status` - Detailed system status
- `/api/v1/metrics` - Performance metrics

### 3. Request Tracking

Each request gets a unique ID:
- Header: `X-Request-ID`
- Logged in all requests
- Useful for debugging

### 4. Metrics to Monitor

- Request rate and latency
- Error rates (4xx, 5xx)
- Cache hit rates
- LLM API call success rates
- Resource usage (CPU, memory, disk)

## Scaling and High Availability

### 1. Horizontal Scaling

Run multiple instances behind a load balancer:

```yaml
services:
  bioanalyzer-backend:
    deploy:
      replicas: 3
```

### 2. Load Balancer Configuration

Use sticky sessions or stateless design:
- Health check: `/health`
- Timeout: 60+ seconds (for analysis endpoints)
- Connection pooling

### 3. Database Considerations

For multiple instances:
- Use shared Redis for rate limiting
- Use shared SQLite (NFS) or migrate to PostgreSQL
- Implement distributed locking for cache operations

## Backup and Recovery

### 1. Regular Backups

Backup these directories:
- `cache/` - SQLite cache database
- `logs/` - Application logs
- `.env` - Configuration (securely)

### 2. Backup Script

```bash
#!/bin/bash
BACKUP_DIR="/backups/bioanalyzer"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup cache
docker exec bioanalyzer-backend tar czf - /app/cache > "$BACKUP_DIR/cache_$DATE.tar.gz"

# Backup logs
docker exec bioanalyzer-backend tar czf - /app/logs > "$BACKUP_DIR/logs_$DATE.tar.gz"
```

### 3. Recovery Procedure

1. Stop services
2. Restore backups
3. Verify configuration
4. Start services
5. Verify health checks

## Troubleshooting

### Common Issues

#### High Memory Usage
- Reduce `UVICORN_WORKERS`
- Lower `MAX_CACHE_SIZE`
- Enable cache cleanup

#### Slow Response Times
- Check LLM API rate limits
- Increase `API_TIMEOUT`
- Optimize RAG configuration
- Check network latency

#### Rate Limit Errors
- Increase `RATE_LIMIT_PER_MINUTE`
- Use Redis for distributed rate limiting
- Implement API key-based rate limits

#### Cache Issues
- Check disk space
- Verify SQLite file permissions
- Run VACUUM on SQLite database

### Debug Mode

For troubleshooting, enable debug logging:

```bash
LOG_LEVEL=DEBUG
```

**Warning**: Don't use DEBUG in production for extended periods.

## Production Checklist

- [ ] Environment variables configured
- [ ] CORS origins restricted
- [ ] Rate limiting enabled
- [ ] SSL/TLS configured (via reverse proxy)
- [ ] Health checks monitoring
- [ ] Log rotation configured
- [ ] Backup strategy implemented
- [ ] Resource limits set
- [ ] Monitoring configured
- [ ] Error tracking enabled
- [ ] API keys secured
- [ ] Documentation updated
- [ ] Load testing completed
- [ ] Disaster recovery plan documented

## Support

For production issues:
1. Check logs: `docker compose logs -f`
2. Review metrics: `/api/v1/metrics`
3. Check health: `/health`
4. Review error logs: `logs/errors.log`

## Additional Resources

- [FastAPI Production Deployment](https://fastapi.tiangolo.com/deployment/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)

