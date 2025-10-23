# 🚀 Quick Start Guide

Get BioAnalyzer Backend up and running in 5 minutes!

## ⚡ Prerequisites Check

Make sure you have:
- ✅ **Docker** (recommended) - Version 20.0+ with Docker Compose support
- ✅ **Python 3.8+** (for local installation, optional)
- ✅ **Internet connection**
- ✅ **Git** (for cloning)

## 🚀 5-Minute Setup (Tested & Verified)

### ✅ **Method 1: Docker Setup (Recommended)**

This is the **tested and verified** approach that works on modern Linux systems.

#### 1. Clone & Navigate (1 min)
```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend
```

#### 2. Install CLI Commands (1 min)
```bash
chmod +x install.sh
./install.sh
```

#### 3. Build & Start (2 min)
```bash
# Build Docker image
docker compose build

# Start application
docker compose up -d
```

#### 4. Verify Setup (1 min)
```bash
# Check status
docker compose ps

# Test API
curl http://localhost:8000/health

# Test CLI
export PATH="$PATH:/home/ronald/.local/bin"
BioAnalyzer fields
```

🎉 **Done!** Open http://localhost:8000/docs for API documentation

### **Method 2: Local Python Setup**

⚠️ **Note**: This may encounter issues with externally managed Python environments.

#### 1. Clone & Navigate (1 min)
```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend
```

#### 2. Setup Environment (2 min)
```bash
# Install python3-venv if needed
sudo apt install python3.12-venv python3-full

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r config/requirements.txt
pip install -e .
```

#### 3. Configure API Keys (1 min)
```bash
# Create environment file
cat > .env << EOF
NCBI_API_KEY=your_ncbi_key_here
GEMINI_API_KEY=your_gemini_key_here
EMAIL=your_email@example.com
EOF
```

#### 4. Run! (1 min)
```bash
python main.py
```

## 🔍 Test It Works

### Docker Method
1. **Visit**: http://localhost:8000/docs
2. **Test Health**: http://localhost:8000/health
3. **CLI Test**: `BioAnalyzer fields`

### Local Method
1. **Visit**: http://localhost:8000/docs
2. **Test Health**: http://localhost:8000/health
3. **CLI Test**: `python cli.py fields`

## 🆘 Common Issues & Solutions

### "externally-managed-environment" error?
```bash
# Solution: Use Docker (recommended)
docker compose build
docker compose up -d

# OR install python3-venv
sudo apt install python3.12-venv python3-full
```

### "docker-compose command not found"?
```bash
# Use newer Docker Compose syntax
docker compose build    # Instead of docker-compose build
docker compose up -d    # Instead of docker-compose up -d
```

### "BioAnalyzer command not found"?
```bash
# Add to PATH
export PATH="$PATH:/home/ronald/.local/bin"
# Or restart terminal after running ./install.sh
```

### "Port already in use"?
```bash
# Check what's using port 8000
sudo lsof -i :8000

# Use different port in docker-compose.yml
# Or stop other services
```

### API not responding?
```bash
# Check container status
docker compose ps

# Check logs
docker compose logs

# Restart if needed
docker compose restart
```

## 📊 Verification Checklist

- ✅ Docker container running
- ✅ API responding at http://localhost:8000/health
- ✅ CLI commands working (`BioAnalyzer fields`)
- ✅ API documentation accessible at http://localhost:8000/docs
- ✅ System status shows all green (`BioAnalyzer status`)

## 📚 Next Steps

- 📖 Read the [Complete Setup Guide](../SETUP_GUIDE.md)
- 🔌 Explore the [API documentation](http://localhost:8000/docs)
- 🧪 Test with real PMIDs
- 🚀 Configure API keys for full functionality

---

**Need help?** Check the [troubleshooting section](../README.md#troubleshooting) in the main README! 