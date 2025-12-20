# Production Readiness Checklist

Quick reference checklist for deploying BioAnalyzer Backend to production.

## Pre-Deployment

### Configuration
- [ ] `.env` file created from `.env.example`
- [ ] All required API keys configured (NCBI, at least one LLM)
- [ ] `ENVIRONMENT=production` set
- [ ] `CORS_ORIGINS` configured (NOT `*`)
- [ ] `LOG_LEVEL=INFO` (or appropriate level)
- [ ] `UVICORN_RELOAD=false`
- [ ] `UVICORN_WORKERS` set (2-4x CPU cores)

### Security
- [ ] CORS origins restricted to specific domains
- [ ] Rate limiting enabled (`ENABLE_RATE_LIMITING=true`)
- [ ] Rate limit configured (`RATE_LIMIT_PER_MINUTE`)
- [ ] API keys stored securely (not in code)
- [ ] `.env` file not committed to version control
- [ ] SSL/TLS configured (via reverse proxy)

### Infrastructure
- [ ] Docker and Docker Compose installed
- [ ] Sufficient resources (4GB+ RAM, 20GB+ disk)
- [ ] Reverse proxy configured (Nginx, Traefik, etc.)
- [ ] Health check endpoints accessible
- [ ] Monitoring solution configured

## Deployment

### Docker Setup
- [ ] Production image built: `docker build -t bioanalyzer-backend:latest .`
- [ ] Production compose file reviewed: `docker-compose.prod.yml`
- [ ] Resource limits configured appropriately
- [ ] Volumes mounted correctly (cache, logs, results)
- [ ] Network configuration verified

### Service Startup
- [ ] Services started: `docker compose -f docker-compose.prod.yml up -d`
- [ ] Health check passing: `curl http://localhost:8000/health`
- [ ] Logs reviewed: `docker compose logs -f`
- [ ] No errors in startup logs
- [ ] All containers healthy: `docker compose ps`

## Post-Deployment

### Verification
- [ ] API documentation accessible: `/docs`
- [ ] Health endpoint responding: `/health`
- [ ] Metrics endpoint working: `/api/v1/metrics`
- [ ] Test analysis request successful
- [ ] Rate limiting working (check headers)
- [ ] Request IDs present in responses

### Monitoring
- [ ] Log rotation working
- [ ] Error logs monitored
- [ ] Performance metrics tracked
- [ ] Resource usage within limits
- [ ] Cache hit rates acceptable
- [ ] API response times acceptable

### Maintenance
- [ ] Backup strategy implemented
- [ ] Backup schedule configured
- [ ] Recovery procedure documented
- [ ] Update procedure documented
- [ ] Rollback procedure documented

## Security Review

- [ ] No sensitive data in logs
- [ ] API keys not exposed in responses
- [ ] Input validation working
- [ ] Rate limiting preventing abuse
- [ ] CORS properly configured
- [ ] Error messages don't leak information

## Performance Review

- [ ] Response times acceptable (<5s for v1, <10s for v2)
- [ ] Cache hit rate >60%
- [ ] Memory usage stable
- [ ] CPU usage acceptable
- [ ] No memory leaks
- [ ] Database size manageable

## Documentation

- [ ] Production deployment guide reviewed
- [ ] Environment variables documented
- [ ] API endpoints documented
- [ ] Troubleshooting guide available
- [ ] Contact information updated

## Quick Commands

```bash
# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f bioanalyzer-backend

# Health check
curl http://localhost:8000/health

# Restart services
docker compose -f docker-compose.prod.yml restart

# Stop services
docker compose -f docker-compose.prod.yml down

# Update and restart
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Emergency Contacts

- **System Admin**: [Your contact]
- **Development Team**: [Team contact]
- **Infrastructure**: [Infra contact]

## Notes

- Keep this checklist updated
- Review quarterly
- Document any custom configurations
- Keep deployment logs

