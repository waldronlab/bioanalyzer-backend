# 🚀 Quick Start Guide

Get BugSigDB Analyzer up and running in 5 minutes!

## ⚡ Prerequisites Check

Make sure you have:
- ✅ Python 3.8+ installed
- ✅ Git installed
- ✅ Internet connection

## 🚀 5-Minute Setup

### Option 1: Automated Setup (Recommended)

#### Linux/Mac Users
```bash
git clone https://github.com/waldronlab/BugsigdbAnalyzer.git
cd BugsigdbAnalyzer
chmod +x setup.sh
./setup.sh
```

#### Windows Users
```bash
git clone https://github.com/waldronlab/BugsigdbAnalyzer.git
cd BugsigdbAnalyzer
setup.bat
```

### Option 2: Manual Setup

#### 1. Clone & Navigate (1 min)
```bash
git clone https://github.com/waldronlab/BugsigdbAnalyzer.git
cd BugsigdbAnalyzer
```

#### 2. Setup Environment (2 min)
```bash
# Create virtual environment
python3 -m venv .venv

# Activate it (Linux/Mac)
source .venv/bin/activate

# OR Activate it (Windows)
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### 3. Get API Keys (2 min)

##### NCBI API Key (PubMed access)
1. Go to [NCBI Account](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)
2. Sign in → Generate API key
3. Copy the key

##### Model API Key (for automated analysis)
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in → Create API key
3. Copy the key

#### 4. Configure (30 seconds)
```bash
# Create environment file
cat > .env << EOF
NCBI_API_KEY=your_ncbi_key_here
GEMINI_API_KEY=your_model_key_here
EMAIL=your_email@example.com
DEFAULT_MODEL=gemini
EOF

# Edit with your actual keys
nano .env  # or use any text editor
```

#### 5. Run! (30 seconds)
```bash
python3 start.py
```

🎉 **Done!** Open http://127.0.0.1:8000 in your browser

## 🔍 Test It Works

1. **Visit**: http://127.0.0.1:8000
2. **Enter a PMID**: Try `12345` (or any valid PMID)
3. **Click Analyze**: Watch the AI analyze the paper!

## 🆘 Common Issues

### "Module not found" errors?
```bash
# Make sure virtual environment is active
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### "Port already in use"?
```bash
# Use different port
python3 start.py --port 8001

# Then visit http://127.0.0.1:8001
```

### API key errors?
```bash
# Check your .env file
cat .env

# Make sure keys are correct and no extra spaces
```

## 📚 Next Steps

- 📖 Read the [full README](README.md)
- 🔌 Explore the [API documentation](http://127.0.0.1:8000/docs)
- 🧪 Run the [test suite](README.md#testing)
- 🚀 Deploy to production

---

**Need help?** Check the [troubleshooting section](README.md#troubleshooting) in the main README! 