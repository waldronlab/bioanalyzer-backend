# BioAnalyzer Backend

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-20.0+-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A comprehensive AI-powered backend system for analyzing and Identifying scientific papers that contain curatable microbiome Signatures  (curation readiness assessment.)

> **✅ Tested Setup**: This project has been successfully built and tested on Ubuntu Linux with Docker. See [SETUP_GUIDE.md](SETUP_GUIDE.md) for verified setup steps.

## 🧬 Overview

BioAnalyzer Backend is a specialized system that combines advanced AI analysis with comprehensive PubMed data retrieval to evaluate scientific papers for BugSigDB curation readiness. The system extracts 6 essential fields required for microbial signature curation and provides full text retrieval capabilities.

### Key Capabilities

- **🔬 Paper Analysis**: Extract 6 essential BugSigDB fields using AI
- **📥 Full Text Retrieval**: Comprehensive PubMed and PMC data retrieval
- **🌐 REST API**: Clean, well-documented REST endpoints
- **💻 CLI Tool**: User-friendly command-line interface
- **📊 Multiple Formats**: JSON, CSV,XML and table output formats
- **⚡ Batch Processing**: Analyze multiple papers simultaneously
- **🔧 Docker Support**: Containerized deployment
- **📈 Monitoring**: Health checks and performance metrics

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    BioAnalyzer Backend                      │
├─────────────────────────────────────────────────────────────┤
│  CLI Interface (cli.py)                                    │
│  ├── Analysis Commands                                      │
│  ├── Retrieval Commands                                     │
│  └── System Management                                      │
├─────────────────────────────────────────────────────────────┤
│  API Layer (app/api/)                                       │
│  ├── FastAPI Application                                    │
│  ├── Router Modules                                         │
│  └── Request/Response Models                                │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (app/services/)                             │
│  ├── PubMedRetriever                                        │
│  ├── PubMedRetrievalService                                 │
│  ├── StandalonePubMedRetriever                              │
│  └── BugSigDBAnalyzer                                       │
├─────────────────────────────────────────────────────────────┤
│  Model Layer (app/models/)                                 │
│  ├── GeminiQA                                               │
│  ├── UnifiedQA                                              │
│  └── Configuration                                          │
├─────────────────────────────────────────────────────────────┤
│  Utility Layer (app/utils/)                                │
│  ├── Configuration Management                              │
│  ├── Text Processing                                        │
│  └── Performance Logging                                    │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Input**: PMID(s) via CLI or API
2. **Retrieval**: Fetch metadata and full text from PubMed/PMC
3. **Analysis**: AI-powered field extraction using Gemini
4. **Processing**: Format and validate results
5. **Output**: Structured data in multiple formats

## 🚀 Quick Start

### Prerequisites

- **Docker** (recommended) - Version 20.0+ with Docker Compose support
- **Python 3.8+** (for local installation)
- **NCBI API key** (optional, for higher rate limits)
- **Google Gemini API key** (optional, for AI analysis)

### Installation & Setup

#### ✅ **Method 1: Docker Installation (Recommended & Tested)**

This is the **recommended approach** as it avoids Python environment conflicts and provides a clean, isolated setup.

```bash
# 1. Navigate to the project directory
cd /path/to/bioanalyzer-backend

# 2. Install CLI commands system-wide
chmod +x install.sh
./install.sh

# 3. Build Docker image
docker compose build

# 4. Start the application
docker compose up -d

# 5. Verify installation
docker compose ps
curl http://localhost:8000/health
```

**Expected Output:**
```json
{"status":"healthy","timestamp":"2025-10-23T17:52:40.249451+00:00","version":"1.0.0"}
```

#### **Method 2: Local Python Installation**

⚠️ **Note**: This method may encounter issues with externally managed Python environments on modern Linux distributions.

```bash
# Clone and setup
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

# Create virtual environment (if python3-venv is available)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r config/requirements.txt
pip install -e .

# Set up environment (optional)
cp .env.example .env
# Edit .env with your API keys
```

### 🧪 **Verification Steps**

After installation, verify the system is working:

```bash
# 1. Check Docker container status
docker compose ps

# 2. Test API health
curl http://localhost:8000/health

# 3. Test CLI commands (add to PATH first)
export PATH="$PATH:/home/ronald/.local/bin"
BioAnalyzer fields
BioAnalyzer status

# 4. View API documentation
# Open browser: http://localhost:8000/docs
```

## 📖 Usage

### CLI Commands

#### System Management
```bash
BioAnalyzer build                    # Build Docker containers
BioAnalyzer start                    # Start the application
BioAnalyzer stop                     # Stop the application
BioAnalyzer restart                  # Restart the application
BioAnalyzer status                   # Check system status
```

#### Paper Analysis
```bash
BioAnalyzer analyze 12345678         # Analyze single paper
BioAnalyzer analyze 12345678,87654321 # Analyze multiple papers
BioAnalyzer analyze --file pmids.txt # Analyze from file
BioAnalyzer fields                   # Show field information
```

#### Paper Retrieval (NEW!)
```bash
BioAnalyzer retrieve 12345678        # Retrieve single paper
BioAnalyzer retrieve 12345678,87654321 # Retrieve multiple papers
BioAnalyzer retrieve --file pmids.txt # Retrieve from file
BioAnalyzer retrieve 12345678 --save  # Save individual files
BioAnalyzer retrieve 12345678 --format json # JSON output
BioAnalyzer retrieve 12345678 --output results.csv # Save to file
```

### API Endpoints

#### Analysis Endpoints
```http
GET /api/v1/analyze/{pmid}           # Analyze paper for BugSigDB fields
GET /api/v1/fields                    # Get field information
GET /health                           # System health check
```

#### Retrieval Endpoints (NEW!)
```http
GET /api/v1/retrieve/{pmid}           # Retrieve full paper data
POST /api/v1/retrieve/batch           # Batch retrieval
GET /api/v1/retrieve/search?q=query   # Search papers
```

### Web Interface

Once started, access:
- **Main Interface**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `NCBI_API_KEY` | NCBI API key for higher rate limits | Yes | - |
| `GEMINI_API_KEY` | Google Gemini API key for AI analysis | Yes | - |
| `EMAIL` | Contact email for API requests | Yes | bioanalyzer@example.com |
| `USE_FULLTEXT` | Enable full text retrieval | No | true |
| `API_TIMEOUT` | API request timeout (seconds) | No | 30 |
| `NCBI_RATE_LIMIT_DELAY` | Rate limiting delay (seconds) | No | 0.34 |

### Configuration Files

- `config/requirements.txt`: Python dependencies
- `app/utils/config.py`: Application configuration
- `docker-compose.yml`: Docker services configuration

## 📊 The 6 Essential BugSigDB Fields

The system analyzes papers for these critical fields:

1. **🧬 Host Species**: The organism being studied (Human, Mouse, Rat, etc.)
2. **📍 Body Site**: Sample collection location (Gut, Oral, Skin, etc.)
3. **🏥 Condition**: Disease/treatment/exposure being studied
4. **🔬 Sequencing Type**: Molecular method used (16S, metagenomics, etc.)
5. **🌳 Taxa Level**: Taxonomic level analyzed (phylum, genus, species, etc.)
6. **👥 Sample Size**: Number of samples or participants

### Field Status Values

- **✅ PRESENT**: Information about the microbiom signtaure is complete and clear
- **⚠️ PARTIALLY_PRESENT**: Some information available but incomplete
- **❌ ABSENT**: Information is missing

## 🏛️ Architecture Details

### Service Layer Architecture

#### PubMedRetriever
- **Purpose**: Core PubMed data retrieval
- **Features**: Metadata extraction, PMC full text retrieval
- **Dependencies**: requests, xml.etree.ElementTree
- **Rate Limiting**: NCBI-compliant request throttling

#### PubMedRetrievalService
- **Purpose**: High-level paper retrieval service
- **Features**: Batch processing, file operations, result formatting
- **Dependencies**: PubMedRetriever
- **Error Handling**: Comprehensive error management

#### StandalonePubMedRetriever
- **Purpose**: Lightweight retrieval without full service stack
- **Features**: Independent operation, minimal dependencies
- **Use Case**: CLI operations, standalone scripts
- **Dependencies**: requests only

#### BugSigDBAnalyzer
- **Purpose**: AI-powered field extraction
- **Features**: Gemini integration, field analysis, confidence scoring
- **Dependencies**: google-generativeai, app.models
- **Output**: Structured field data with confidence scores

### Data Flow Architecture

```
Input (PMID) → Retrieval → Analysis → Processing → Output
     ↓            ↓          ↓          ↓         ↓
   CLI/API   PubMedRetriever  GeminiQA  Formatter  JSON/CSV/Table
```

### Error Handling Strategy

1. **Network Errors**: Retry with exponential backoff
2. **API Errors**: Graceful degradation with fallback methods
3. **Parsing Errors**: Error reporting with context
4. **Missing Data**: Clear indication of unavailable information

## 🔍 API Examples

### Analysis Request
```bash
curl -X GET "http://localhost:8000/api/v1/analyze/12345678"
```

### Retrieval Request
```bash
curl -X GET "http://localhost:8000/api/v1/retrieve/12345678"
```

### Batch Retrieval
```bash
curl -X POST "http://localhost:8000/api/v1/retrieve/batch" \
  -H "Content-Type: application/json" \
  -d '{"pmids": ["12345678", "87654321"]}'
```

### Response Format
```json
{
  "pmid": "12345678",
  "title": "Gut microbiome analysis in patients with IBD",
  "abstract": "This study examines...",
  "journal": "Nature Medicine",
  "authors": ["Smith J", "Doe A"],
  "publication_date": "2023",
  "full_text": "Complete paper text...",
  "has_full_text": true,
  "fields": {
    "host_species": {
      "status": "PRESENT",
      "value": "Human",
      "confidence": 0.95
    },
    "body_site": {
      "status": "PRESENT",
      "value": "Gut",
      "confidence": 0.92
    }
  },
  "retrieval_timestamp": "2023-12-01T10:30:00Z"
}
```

## 🧪 Testing

### Run Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=app

# Specific module
pytest tests/test_retrieval.py

# In Docker
docker exec -it bioanalyzer-api pytest
```

### Test Coverage
- Unit tests for all service classes
- Integration tests for API endpoints
- CLI command testing
- Error handling validation

## 📁 Project Structure

```
bioanalyzer-backend/
├── app/                           # Main application code
│   ├── api/                      # API layer
│   │   ├── app.py               # FastAPI application
│   │   ├── models/              # Pydantic models
│   │   ├── routers/             # API routes
│   │   └── utils/               # API utilities
│   ├── models/                   # AI models and configuration
│   │   ├── gemini_qa.py         # Gemini AI integration
│   │   ├── unified_qa.py         # Unified QA system
│   │   └── config.py            # Model configuration
│   ├── services/                 # Business logic services
│   │   ├── data_retrieval.py    # Core PubMed retrieval
│   │   ├── pubmed_retrieval_service.py # High-level service
│   │   ├── standalone_pubmed_retriever.py # Standalone retriever
│   │   └── bugsigdb_analyzer.py  # Field analysis
│   └── utils/                    # Utilities and helpers
│       ├── config.py             # Configuration management
│       ├── text_processing.py    # Text processing utilities
│       └── performance_logger.py # Performance monitoring
├── config/                       # Configuration files
│   ├── requirements.txt         # Python dependencies
│   ├── setup.py                 # Package configuration
│   └── pytest.ini              # Test configuration
├── docs/                         # Documentation
│   ├── README.md                # Main documentation
│   ├── DOCKER_DEPLOYMENT.md     # Docker deployment guide
│   └── QUICKSTART.md            # Quick start guide
├── scripts/                      # Utility scripts
│   ├── log_cleanup.py           # Log management
│   ├── performance_monitor.py   # Performance monitoring
│   └── log_dashboard.py         # Log visualization
├── tests/                        # Test suite
│   ├── test_api.py              # API tests
│   ├── test_retrieval.py        # Retrieval tests
│   └── test_cli.py              # CLI tests
├── cli.py                        # CLI interface
├── main.py                       # API server entry point
├── docker-compose.yml            # Docker services
├── Dockerfile                    # Docker image
└── README.md                     # This file
```

## 🚀 Deployment

### Docker Deployment

#### Development
```bash
# Build and start development environment
docker-compose up -d

# View logs
docker-compose logs -f

# Access container
docker exec -it bioanalyzer-api bash
```

#### Production
```bash
# Build production image
docker build -t bioanalyzer-backend:latest .

# Run production container
docker run -d -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -e NCBI_API_KEY=your_key \
  bioanalyzer-backend:latest
```

### Local Deployment

#### API Server
```bash
# Start API server
python main.py

# Or with uvicorn
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload
```

#### CLI Usage
```bash
# Direct CLI usage
python cli.py analyze 12345678
python cli.py retrieve 12345678 --save
```

## 📈 Performance

### Optimization Features

- **Caching**: Built-in caching for frequently accessed papers
- **Rate Limiting**: NCBI-compliant request throttling
- **Batch Processing**: Efficient multi-paper processing
- **Async Support**: Non-blocking API operations
- **Memory Management**: Optimized for large-scale analysis

### Performance Metrics

- **Analysis Speed**: ~2-5 seconds per paper
- **Retrieval Speed**: ~1-3 seconds per paper
- **Throughput**: 10-20 papers per minute
- **Memory Usage**: ~100-200MB base + 50MB per concurrent request

## 🔧 Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r config/requirements.txt
pip install -e .[dev]

# Set up pre-commit hooks
pre-commit install
```

### Code Quality

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .

# Run tests
pytest
```

### Adding New Features

1. **Service Layer**: Add new services in `app/services/`
2. **API Endpoints**: Add routes in `app/api/routers/`
3. **CLI Commands**: Extend `cli.py` with new commands
4. **Models**: Add Pydantic models in `app/api/models/`

## 🐛 Troubleshooting

### Common Issues & Solutions

#### **Python Environment Issues**
```bash
# Error: externally-managed-environment
# Solution: Use Docker (recommended) or install python3-venv
sudo apt install python3.12-venv python3-full
python3 -m venv .venv
source .venv/bin/activate
```

#### **Docker Compose Issues**
```bash
# Error: docker-compose command not found
# Solution: Use newer Docker Compose syntax
docker compose build    # Instead of docker-compose build
docker compose up -d    # Instead of docker-compose up -d
```

#### **CLI Command Not Found**
```bash
# Error: BioAnalyzer command not found
# Solution: Add to PATH
export PATH="$PATH:/home/ronald/.local/bin"
# Or restart terminal after running ./install.sh
```

#### **API Not Responding**
```bash
# Check container status
docker compose ps

# Check logs
docker compose logs

# Restart if needed
docker compose restart
```

#### **Missing API Keys**
```bash
# Warning: GeminiQA not initialized
# This is normal - system works without API keys
# For full functionality, set environment variables:
export GEMINI_API_KEY="your_gemini_key"
export NCBI_API_KEY="your_ncbi_key"
```

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

## 📚 Documentation

- **🚀 Quick Start**: [QUICKSTART.md](docs/QUICKSTART.md) - Get running in 5 minutes
- **📖 Complete Setup Guide**: [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed setup steps (tested & verified)
- **🏗️ Architecture Guide**: [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **🐳 Docker Guide**: [DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md)
- **🔧 API Documentation**: http://localhost:8000/docs (when running)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add tests for new functionality
- Update documentation for API changes
- Use type hints for all functions
- Write comprehensive docstrings

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **BugSigDB Team**: For the microbial signatures database
- **NCBI**: For PubMed data access and E-utilities API
- **Google**: For Gemini AI capabilities
- **FastAPI**: For the excellent web framework
- **Docker**: For containerization technology

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/waldronlab/bioanalyzer-backend/issues)
- **Discussions**: [GitHub Discussions](https://github.com/waldronlab/bioanalyzer-backend/discussions)
- **Documentation**: [Project Wiki](https://github.com/waldronlab/bioanalyzer-backend/wiki)

---

**Happy analyzing! 🧬🔬**
