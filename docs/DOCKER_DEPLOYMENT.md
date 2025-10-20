# BugSigDB Analyzer Docker Deployment Guide

This guide provides comprehensive instructions for deploying the BugSigDB Analyzer using Docker and Docker Compose.

## 🐳 Prerequisites

- Docker 20.0+ 
- Docker Compose 2.0+ (or `docker compose` command)
- At least 4GB RAM available
- At least 10GB disk space

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/waldronlab/BugsigdbAnalyzer.git
cd BugsigdbAnalyzer

# Run the automated Docker setup
chmod +x docker-setup.sh
./docker-setup.sh
```

### 2. Configure Environment

Edit the `.env` file with your API keys:

```bash
nano .env
```

Required variables:
```env
NCBI_API_KEY=your_ncbi_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
EMAIL=your_email@example.com
DEFAULT_MODEL=gemini
REDIS_PASSWORD=your_secure_password
ENVIRONMENT=production
```

### 3. Start Services

#### Development Environment
```bash
docker compose -f docker-compose.dev.yml up -d
```

#### Production Environment
```bash
docker compose -f docker-compose.prod.yml up -d
```

### 4. Verify Deployment

```bash
# Check service status
./docker-health-check.sh

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │   Nginx Proxy   │    │  FastAPI App    │
│   (Optional)    │────│   (Port 80/443) │────│  (Port 8000)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │     Redis       │    │   PostgreSQL    │
                       │   (Port 6379)   │    │   (Port 5432)   │
                       └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   Prometheus    │
                       │   (Port 9090)   │
                       └─────────────────┘
```

## 📁 Configuration Files

### Docker Compose Files

- **`docker-compose.yml`**: Base configuration
- **`docker-compose.dev.yml`**: Development environment
- **`docker-compose.prod.yml`**: Production environment

### Nginx Configuration

- **`nginx/nginx.conf`**: Production Nginx configuration
- **`nginx/nginx.dev.conf`**: Development Nginx configuration

### Monitoring

- **`monitoring/prometheus.yml`**: Prometheus metrics configuration

## 🔧 Service Configuration

### FastAPI Application

- **Port**: 8000 (internal), 8000 (dev external)
- **Health Check**: `/health` endpoint
- **Metrics**: `/metrics` endpoint
- **API Documentation**: `/docs` endpoint

### Nginx Reverse Proxy

- **Port**: 80 (HTTP), 443 (HTTPS - future)
- **Load Balancing**: Round-robin to app instances
- **Rate Limiting**: 10 req/s for API, 5 req/s for login
- **Gzip Compression**: Enabled for text-based content
- **Security Headers**: XSS protection, content type, frame options

### Redis Cache

- **Port**: 6379 (dev external), internal only (prod)
- **Persistence**: AOF (Append Only File)
- **Authentication**: Password protected in production

### PostgreSQL Database

- **Port**: 5432 (dev external), internal only (prod)
- **Database**: `bugsigdb_dev` (dev), `bugsigdb_prod` (prod)
- **User**: `bugsigdb_user`
- **Password**: Configurable via environment

### Prometheus Monitoring

- **Port**: 9090 (prod only)
- **Metrics Collection**: 15s intervals
- **Retention**: 200 hours
- **Targets**: App, Nginx, Redis

## 🚦 Health Checks

### Application Health

```bash
# Check app health
curl http://localhost:8000/health

# Check nginx health
curl http://localhost/health

# Check Redis
docker exec bugsigdb-analyzer-redis redis-cli ping

# Check PostgreSQL
docker exec bugsigdb-analyzer-postgres-dev pg_isready -U bugsigdb_user
```

### Docker Health Checks

All services include built-in health checks:

- **App**: HTTP GET to `/health` endpoint
- **Nginx**: HTTP GET to `/health` endpoint  
- **Redis**: `redis-cli ping` command
- **PostgreSQL**: `pg_isready` command

## 📊 Monitoring and Logging

### Prometheus Metrics

- **App Metrics**: `/metrics` endpoint
- **Nginx Metrics**: `/nginx_status` endpoint (future)
- **Redis Metrics**: Redis INFO command (future)

### Log Management

- **Log Driver**: JSON file
- **Rotation**: 10MB max size, 3 files max
- **Retention**: Configurable via Docker Compose

### Resource Monitoring

```bash
# View container stats
docker stats

# View resource usage
docker compose -f docker-compose.prod.yml top

# Monitor logs
docker compose -f docker-compose.prod.yml logs -f [service_name]
```

## 🔒 Security Features

### Network Security

- **Isolated Networks**: Custom bridge network (`172.20.0.0/16`)
- **Port Exposure**: Minimal external port exposure
- **Internal Communication**: Services communicate via internal network

### Application Security

- **Non-root Users**: App runs as `app` user
- **Security Headers**: XSS protection, content type validation
- **Rate Limiting**: API and login rate limiting
- **Input Validation**: Pydantic models for API validation

### Data Security

- **Volume Mounts**: Read-only where possible
- **Environment Variables**: Sensitive data via `.env` file
- **Database Authentication**: Password-protected databases

## 📈 Scaling and Performance

### Horizontal Scaling

```bash
# Scale app instances
docker compose -f docker-compose.prod.yml up -d --scale app=3

# Scale with load balancer
docker compose -f docker-compose.prod.yml up -d --scale app=5
```

### Resource Limits

Production environment includes resource constraints:

- **App**: 1-2GB RAM, 0.5-1.0 CPU
- **Nginx**: 128-256MB RAM, 0.25-0.5 CPU
- **Redis**: 256-512MB RAM, 0.25-0.5 CPU

### Performance Optimization

- **Gzip Compression**: Enabled for text content
- **Keep-alive Connections**: 32 connections per upstream
- **Connection Pooling**: Database connection pooling
- **Caching**: Redis-based caching layer

## 🚨 Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs [service_name]

# Check container status
docker compose -f docker-compose.prod.yml ps

# Restart service
docker compose -f docker-compose.prod.yml restart [service_name]
```

#### Health Check Failures

```bash
# Check endpoint manually
curl -v http://localhost:8000/health

# Check container health
docker inspect bugsigdb-analyzer-app | grep -A 10 Health

# Restart with health check disabled
docker compose -f docker-compose.prod.yml up -d --no-healthcheck
```

#### Port Conflicts

```bash
# Check port usage
sudo netstat -tulpn | grep :80
sudo netstat -tulpn | grep :8000

# Change ports in docker-compose file
ports:
  - "8080:80"  # Change external port
```

#### Resource Issues

```bash
# Check system resources
docker system df
docker stats --no-stream

# Clean up unused resources
docker system prune -a
```

### Debug Mode

```bash
# Start with debug logging
ENVIRONMENT=development LOG_LEVEL=debug docker compose -f docker-compose.dev.yml up -d

# Access container shell
docker exec -it bugsigdb-analyzer-app-dev bash

# View real-time logs
docker compose -f docker-compose.dev.yml logs -f --tail=100
```

## 🔄 Maintenance

### Updates and Upgrades

```bash
# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build

# Zero-downtime deployment
docker compose -f docker-compose.prod.yml up -d --no-deps --build app
```

### Backup and Recovery

```bash
# Backup volumes
docker run --rm -v bugsigdb-analyzer_redis-data:/data -v $(pwd):/backup alpine tar czf /backup/redis-backup.tar.gz -C /data .

# Backup database
docker exec bugsigdb-analyzer-postgres-dev pg_dump -U bugsigdb_user bugsigdb_dev > backup.sql

# Restore from backup
docker exec -i bugsigdb-analyzer-postgres-dev psql -U bugsigdb_user bugsigdb_dev < backup.sql
```

### Cleanup

```bash
# Stop and remove containers
docker compose -f docker-compose.prod.yml down

# Remove volumes (WARNING: Data loss)
docker compose -f docker-compose.prod.yml down -v

# Remove images
docker compose -f docker-compose.prod.yml down --rmi all
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Prometheus Documentation](https://prometheus.io/docs/)

## 🆘 Support

For issues and questions:

1. Check the troubleshooting section above
2. Review container logs: `docker compose logs [service_name]`
3. Run health check: `./docker-health-check.sh`
4. Check GitHub issues: [BugSigDB Analyzer Issues](https://github.com/waldronlab/BugsigdbAnalyzer/issues) 