# BioAnalyzer Backend - Complete Setup Guide

This guide documents the actual steps taken to successfully build and run the BioAnalyzer Backend system. Based on testing on Ubuntu Linux with Docker.

## System Requirements

- OS: Mac, Windows and Ubuntu Linux (tested on 6.14.0-33-generic)
- Docker: Version 28.5.1+ with Docker Compose support
- Python: 3.8+ (for local installation, optional)
- Memory: Minimum 2GB RAM recommended
- Storage: 1GB free space

## Step-by-Step Setup

### Step 1: Project Preparation

```bash
# Navigate to project directory
cd /home/<computer_user_bame>/Desktop/new/bioanalyzer-backend

# Verify project structure
ls -la
# Should show: cli.py, main.py, install.sh, docker-compose.yml, etc.
```

### Step 2: Install CLI Commands

```bash
# Make install script executable
chmod +x install.sh

# Run installation script
./install.sh
```

### Step 3: Docker Setup (Recommended)

Since modern Linux distributions have externally managed Python environments, Docker is the recommended approach:

```bash
docker compose build
```

### Step 4: Start Application

```bash
docker compose up -d
```

### Step 5: Verification

#### Check Container Status
```bash
docker compose ps
```

#### Test API Health
```bash
curl http://localhost:8000/health
```

#### Test CLI Commands
```bash
export PATH="$PATH:/home/<computer_user_name>/.local/bin"
BioAnalyzer fields
```

#### Test System Status
```bash
BioAnalyzer status
```

## Access Points

| Service | URL |
|---------|-----|
| API Server | http://localhost:8000 |
| API Documentation | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| Fields Info | http://localhost:8000/api/v1/fields |

## Configuration

### Environment Variables (Optional)

The system works without API keys, but for full functionality:

```bash
# Set in your shell or .env file
export GEMINI_API_KEY="your_gemini_api_key"
export NCBI_API_KEY="your_ncbi_api_key"
export EMAIL="your_email@example.com"
```

### Docker Configuration

The system uses these Docker settings:
- **Port**: 8000 (mapped to host)
- **Volumes**: cache, logs, results directories
- **Health Check**: Every 30 seconds
- **Restart Policy**: unless-stopped

## 🧪 Testing Commands

### API Testing
```bash
# Health check
curl http://localhost:8000/health

# Get field information
curl http://localhost:8000/api/v1/fields

# Analyze a paper (replace with real PMID)
curl http://localhost:8000/api/v1/analyze/12345678
```

### CLI Testing
```bash
# Show help
BioAnalyzer help

# Show fields
BioAnalyzer fields

# Check status
BioAnalyzer status

# Analyze paper (replace with real PMID)
BioAnalyzer analyze 12345678
```

## 🐛 Troubleshooting

### Issue: Python Environment Conflicts
**Problem**: `externally-managed-environment` error
**Solution**: Use Docker (recommended) or install python3-venv
```bash
sudo apt install python3.12-venv python3-full
python3 -m venv .venv
source .venv/bin/activate
```

### Issue: Docker Compose Not Found
**Problem**: `docker-compose command not found`
**Solution**: Use newer Docker Compose syntax
```bash
docker compose build    # Instead of docker-compose build
docker compose up -d    # Instead of docker-compose up -d
```

### Issue: CLI Command Not Found
**Problem**: `BioAnalyzer command not found`
**Solution**: Add to PATH
```bash
export PATH="$PATH:/home/<computer_user_bame>/.local/bin"
# Or restart terminal after running ./install.sh
```

### Issue: Container Not Starting
**Problem**: Container fails to start
**Solution**: Check logs and restart
```bash
docker compose logs
docker compose restart
```

### Issue: API Not Responding
**Problem**: API endpoints return errors
**Solution**: Check container health
```bash
docker compose ps
docker compose logs --tail=20
```

## System Status After Setup

✅ **Docker**: Available and working  
✅ **Backend Container**: Running and healthy  
✅ **API Server**: Responding on port 8000  
✅ **CLI Commands**: Installed and functional  
✅ **Health Check**: All systems operational  
✅ **API Documentation**: Available at /docs  

## Next Steps

1. **Configure API Keys** (optional): Set GEMINI_API_KEY and NCBI_API_KEY for full functionality
2. **Test Analysis**: Try analyzing real PMIDs using the CLI or API
3. **Explore Documentation**: Visit http://localhost:8000/docs for interactive API documentation
4. **Batch Processing**: Test analyzing multiple papers at once


**Setup completed successfully! 🧬**  
