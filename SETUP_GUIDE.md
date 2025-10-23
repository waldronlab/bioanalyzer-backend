# BioAnalyzer Backend - Complete Setup Guide

## 📋 Overview

This guide documents the **actual steps taken** to successfully build and run the BioAnalyzer Backend system. This is a real-world setup guide based on testing on Ubuntu Linux with Docker.

## 🎯 System Requirements

- **OS**: Mac, Windows and Ubuntu Linux (tested on 6.14.0-33-generic)
- **Docker**: Version 28.5.1+ with Docker Compose support
- **Python**: 3.8+ (for local installation, optional)
- **Memory**: Minimum 2GB RAM recommended
- **Storage**: 1GB free space

## 🚀 Step-by-Step Setup

### Step 1: Project Preparation

```bash
# Navigate to project directory
cd /home/ronald/Desktop/new/bioanalyzer-backend

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

**Expected Output:**
```
🧬 BioAnalyzer System Installation
==================================
[INFO] Installing BioAnalyzer for current user.
[INFO] Creating installation directory: /home/ronald/.local/bin
[INFO] BioAnalyzer backend directory: /home/ronald/Desktop/new/bioanalyzer-backend
[INFO] Installing BioAnalyzer command...
[SUCCESS] BioAnalyzer command installed successfully!
```

### Step 3: Docker Setup (Recommended)

Since modern Linux distributions have externally managed Python environments, Docker is the recommended approach:

```bash
# Build Docker image
docker compose build
```

**Expected Output:**
```
[+] Building 8.2s (8/8) FINISHED
=> [internal] load build definition from Dockerfile
=> [internal] load metadata for docker.io/library/python:3.11-slim
=> [1/8] FROM docker.io/library/python:3.11-slim
=> [2/8] WORKDIR /app
=> [3/8] RUN apt-get update && apt-get install -y gcc g++ curl git
=> [4/8] COPY config/requirements.txt .
=> [5/8] RUN pip install --no-cache-dir -r requirements.txt
=> [6/8] COPY . .
=> [7/8] RUN mkdir -p cache logs results
=> [8/8] RUN chmod +x cli.py
=> exporting to image
=> naming to docker.io/library/bioanalyzer-backend-bioanalyzer-backend
```

### Step 4: Start Application

```bash
# Start application in background
docker compose up -d
```

**Expected Output:**
```
Network bioanalyzer-backend_default  Creating
Network bioanalyzer-backend_default  Created
Container bioanalyzer-backend-bioanalyzer-backend-1  Creating
Container bioanalyzer-backend-bioanalyzer-backend-1  Created
Container bioanalyzer-backend-bioanalyzer-backend-1  Starting
Container bioanalyzer-backend-bioanalyzer-backend-1  Started
```

### Step 5: Verification

#### Check Container Status
```bash
docker compose ps
```

**Expected Output:**
```
NAME                                        IMAGE                                     COMMAND                  SERVICE               CREATED         STATUS                            PORTS
bioanalyzer-backend-bioanalyzer-backend-1   bioanalyzer-backend-bioanalyzer-backend   "python main.py --ho…"   bioanalyzer-backend   4 seconds ago   Up 4 seconds (health: starting)   0.0.0.0:8000->8000/tcp
```

#### Test API Health
```bash
curl http://localhost:8000/health
```

**Expected Output:**
```json
{"status":"healthy","timestamp":"2025-10-23T17:52:40.249451+00:00","version":"1.0.0"}
```

#### Test CLI Commands
```bash
# Add CLI to PATH
export PATH="$PATH:/home/ronald/.local/bin"

# Test fields command
BioAnalyzer fields
```

**Expected Output:**
```
🧬 BioAnalyzer - BugSigDB Essential Fields
==========================================

📋 6 Essential Fields for BugSigDB Curation:

🧬 Host Species (host_species):
   Description: The host organism being studied (e.g., Human, Mouse, Rat)
   Required: Yes
...
```

#### Test System Status
```bash
BioAnalyzer status
```

**Expected Output:**
```
📊 BioAnalyzer System Status
========================================
Docker: ✅ Available
Backend Image: ✅ Built
Backend Container: ✅ Running
API Health: ✅ Healthy
🌐 Web Interface: http://localhost:3000
🔧 API Documentation: http://localhost:8000/docs
```

## 🌐 Access Points

| Service | URL | Status |
|---------|-----|--------|
| **API Server** | http://localhost:8000 | ✅ Running |
| **API Documentation** | http://localhost:8000/docs | ✅ Available |
| **Health Check** | http://localhost:8000/health | ✅ Healthy |
| **Fields Info** | http://localhost:8000/api/v1/fields | ✅ Working |

## 🔧 Configuration

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
export PATH="$PATH:/home/ronald/.local/bin"
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

## 📊 System Status After Setup

✅ **Docker**: Available and working  
✅ **Backend Container**: Running and healthy  
✅ **API Server**: Responding on port 8000  
✅ **CLI Commands**: Installed and functional  
✅ **Health Check**: All systems operational  
✅ **API Documentation**: Available at /docs  

## 🎯 Next Steps

1. **Configure API Keys** (optional): Set GEMINI_API_KEY and NCBI_API_KEY for full functionality
2. **Test Analysis**: Try analyzing real PMIDs using the CLI or API
3. **Explore Documentation**: Visit http://localhost:8000/docs for interactive API documentation
4. **Batch Processing**: Test analyzing multiple papers at once

## 📝 Notes

- The system works **without API keys** but with limited functionality
- Docker approach is **recommended** to avoid Python environment conflicts
- All 6 essential BugSigDB fields are supported
- The system is ready for production use after setup

---

**Setup completed successfully! 🧬**  
The BioAnalyzer Backend is now fully operational and ready to analyze scientific papers for BugSigDB curation readiness.
