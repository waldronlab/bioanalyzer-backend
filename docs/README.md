# BioAnalyzer Backend Documentation

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-20.0+-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Comprehensive documentation for BioAnalyzer Backend - an AI-powered system for analyzing scientific papers and retrieving full text content from PubMed for BugSigDB curation readiness assessment. 

## 🚀 Features

- **🔬 Paper Analysis**: Extract 6 essential BugSigDB fields using AI
- **🤖 Multi-Provider LLM Support**: LiteLLM integration for OpenAI, Anthropic, Gemini, Ollama, and Llamafile
- **🧠 Advanced RAG**: Contextual summarization and chunk re-ranking for improved accuracy
- **📥 Full Text Retrieval**: Comprehensive PubMed and PMC data retrieval
- **🌐 REST API**: Versioned API endpoints (v1 and v2) with RAG support
- **💻 CLI Tool**: User-friendly command-line interface
- **📊 Multiple Formats**: JSON, CSV, XML and table output formats
- **⚡ Batch Processing**: Analyze multiple papers simultaneously
- **🔧 Docker Support**: Containerized deployment
- **📈 Monitoring**: Health checks and performance metrics
- **🔄 Caching**: Built-in SQLite caching for improved performance
- **🛡️ Error Handling**: Comprehensive error handling and recovery
- **📚 Documentation**: Extensive documentation and examples

## 🏗️ Architecture

The project follows a layered architecture with clear separation of concerns:

- **API Layer** (`app/api/`): FastAPI-based REST API with versioned endpoints
  - **v1 API**: Backward compatible simple analysis endpoints
  - **v2 API**: RAG-enhanced endpoints with contextual summarization
- **Service Layer** (`app/services/`): Business logic and data processing services
  - **BugSigDBAnalyzer**: Core field extraction service
  - **AdvancedRAGService**: RAG with contextual summarization and chunk re-ranking
  - **ContextualSummarizationService**: Query-aware summarization
  - **ChunkReRanker**: Relevance-based chunk ranking
  - **CacheManager**: SQLite-based caching
- **Model Layer** (`app/models/`): AI models and analysis engines
  - **LLMProviderManager**: Multi-provider LLM support via LiteLLM
  - **UnifiedQA**: Unified interface for QA operations
- **Utility Layer** (`app/utils/`): Shared utilities and helper functions
  - **ChunkingService**: Text chunking for RAG
  - **Configuration Management**: Environment and config handling
- **CLI Interface** (`cli.py`): Command-line interface for direct user interaction
- **Docker Support**: Containerized deployment with multi-stage builds
- **Monitoring**: Health checks, logging, and performance metrics

## 📋 Prerequisites

### For Local Development
- Python 3.8 or higher
- pip (Python package installer)
- Git

### For Docker Deployment
- Docker 20.0 or higher
- Docker Compose 2.0 or higher

### API Keys Required
- **NCBI API key** (required for PubMed access)
- **LLM API key** (at least one required):
  - Google Gemini API key (recommended)
  - OpenAI API key (optional)
  - Anthropic API key (optional)
  - Ollama (local, no API key needed)

## 🛠️ Installation

### Option 1: Docker (Recommended)

#### Quick Start with Docker
```bash
# Clone the repository
git clone https://github.com/waldronlab/BugsigdbAnalyzer.git
cd BugsigdbAnalyzer

# Run the automated Docker setup
chmod +x docker-setup.sh
./docker-setup.sh

# Start the development environment
docker-compose -f docker-compose.dev.yml up -d

# Access the application
# - Direct app: http://localhost:8000
# - Through Nginx: http://localhost:8080
# - API docs: http://localhost:8000/docs
```

#### Production Deployment
```bash
# Start production environment
docker-compose -f docker-compose.prod.yml up -d

# Access the application
# - Main app: http://localhost
# - API docs: http://localhost/docs
# - Monitoring: http://localhost:9090
```

#### Docker Commands Reference
```bash
# View logs
docker-compose -f docker-compose.dev.yml logs -f

# Stop services
docker-compose -f docker-compose.dev.yml down

# Rebuild and restart
docker-compose -f docker-compose.dev.yml up --build -d

# Access container shell
docker exec -it bugsigdb-analyzer-app-dev bash

# View running containers
docker ps

# Check service health
docker-compose -f docker-compose.dev.yml ps
```

### Option 2: Local Development

#### 1. Clone the Repository
```bash
git clone https://github.com/waldronlab/BugsigdbAnalyzer.git
cd BugsigdbAnalyzer
```

#### 2. Create Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Set Up Environment Variables
Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit the `.env` file with your API keys:

```env
# API Keys
NCBI_API_KEY=your_ncbi_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
EMAIL=your_email_here (Optional since user sessions were removed)

# Model Configuration
DEFAULT_MODEL=gemini (Optional)
```

#### 5. Get API Keys

##### NCBI API Key
1. Go to [NCBI Account](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)
2. Sign in or create an account
3. Generate an API key

##### Google Gemini API Key
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Create an API key

## 🚀 Running the Application

### Quick Start with CLI

```bash
# 1. Build containers
BioAnalyzer build

# 2. Start application
BioAnalyzer start

# 3. Analyze a paper
BioAnalyzer analyze 12345678

# 4. Retrieve full paper data
BioAnalyzer retrieve 12345678

# 5. Check status
BioAnalyzer status

# 6. Stop when done
BioAnalyzer stop
```

### Available CLI Commands

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

### Direct API Server

```bash
python3 main.py
```

The application will start on `http://127.0.0.1:8000`

### Advanced Options

```bash
# Run with custom host and port
python3 start.py --host 0.0.0.0 --port 8080

# Run with HTTPS (requires SSL certificates)
python3 start.py --https --port 8443
```

### Alternative Startup Methods

```bash
# Using uvicorn directly
uvicorn web.app:app --host 127.0.0.1 --port 8000 --reload

# Using Python module
python -m web.app
```

## 🌐 Web Interface

Once running, open your browser and navigate to:

- **Main Interface**: `http://127.0.0.1:8000`
- **API Documentation**: `http://127.0.0.1:8000/docs`
- **Alternative API Docs**: `http://127.0.0.1:8000/redoc`

### Using the Web Interface

1. **Paper Analysis**: Enter a PMID or DOI to analyze a specific paper and Get detailed assessment of experimental methods
2. **Single & Batch Analysis**: Upload a list of PMIDs for bulk processing or a single PMID to Check if papers are curatable
3. **Interactive Chat**: Ask questions about papers using the AI assistant

## 🔌 API Usage

### Core Endpoints

#### Paper Analysis (v1 - Simple)
```bash
GET /api/v1/analyze/{pmid}           # Analyze paper for BugSigDB fields
POST /api/v1/analyze/{pmid}          # Analyze paper (POST method)
GET /api/v1/fields                   # Get field information
```

#### Paper Analysis (v2 - RAG-Enhanced)
```bash
GET /api/v2/analyze/{pmid}            # Analyze with RAG features
POST /api/v2/analyze                 # Analyze with custom RAG config
POST /api/v2/analyze/batch           # Batch analysis with RAG
GET /api/v2/rag/config              # Get RAG configuration
```

#### Paper Retrieval
```bash
GET /api/v1/retrieve/{pmid}          # Retrieve full paper data
POST /api/v1/retrieve/batch          # Batch retrieval
GET /api/v1/retrieve/search?q=query # Search papers
```

#### System Endpoints
```bash
GET /health                          # Health check
GET /metrics                         # Performance metrics
GET /docs                            # API documentation
```

### Example API Calls

#### Analyze a Paper
```bash
curl -X GET "http://localhost:8000/api/v1/analyze/12345678"
```

#### Retrieve Paper Data
```bash
curl -X GET "http://localhost:8000/api/v1/retrieve/12345678"
```

#### Batch Retrieval
```bash
curl -X POST "http://localhost:8000/api/v1/retrieve/batch" \
  -H "Content-Type: application/json" \
  -d '{"pmids": ["12345678", "87654321"]}'
```

### WebSocket Endpoint

```javascript
// Connect to WebSocket for real-time analysis
const ws = new WebSocket('ws://127.0.0.1:8000/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Analysis result:', data);
};

// Send analysis request
ws.send(JSON.stringify({
    type: 'analyze_paper',
    pmid: '12345'
}));
```

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_app.py

# Run tests with verbose output
pytest -v

# Run tests in Docker
docker exec -it bugsigdb-analyzer-app-dev pytest
```

## 📁 Project Structure

```
BugsigdbAnalyzer/
├── web/                    # Web application
│   ├── app.py             # FastAPI main application
│   ├── app_test.py        # Test application
│   └── static/            # Frontend assets
│       ├── index.html     # Main interface
│       ├── css/           # Stylesheets
│       └── js/            # JavaScript files
├── models/                 # AI models and QA systems
│   ├── gemini_qa.py       # Google Gemini integration
│   ├── unified_qa.py      # Unified QA system
│   ├── conversation_model.py # Conversational AI model
│   └── config.py          # Model configuration
├── retrieve/               # Data retrieval
│   └── data_retrieval.py  # PubMed data fetching
├── utils/                  # Utilities and helpers
│   ├── config.py          # Configuration management
│   ├── text_processing.py # Text processing utilities
│   ├── methods_scorer.py  # Methods quality scoring
│   └── user_manager.py    # User session management
├── process/                # Data processing pipelines
├── classify/               # Classification models
├── nginx/                  # Nginx configuration
│   ├── nginx.conf         # Production Nginx config
│   ├── nginx.dev.conf     # Development Nginx config
│   └── error_pages/       # Custom error pages
├── monitoring/             # Monitoring configuration
│   └── prometheus.yml     # Prometheus metrics config
├── data/                   # Data files and datasets
├── tests/                  # Test suite
├── results/                # Analysis results
├── cache/                  # Cached data
├── requirements.txt        # Python dependencies
├── Dockerfile              # Production Docker image
├── Dockerfile.dev          # Development Docker image
├── docker-compose.yml      # Production Docker Compose
├── docker-compose.dev.yml  # Development Docker Compose
├── docker-compose.prod.yml # Production Docker Compose
├── start.py               # Application launcher
├── setup.sh               # Linux/Mac setup script
├── setup.bat              # Windows setup script
├── docker-setup.sh        # Docker setup script
├── docker-setup.bat       # Docker setup script for Windows
└── README.md              # This file
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `NCBI_API_KEY` | NCBI API key for PubMed access | Yes | - |
| `GEMINI_API_KEY` | Google Gemini API key | Yes | - |
| `EMAIL` | Contact email for API requests | Yes | - |
| `DEFAULT_MODEL` | Default AI model to use | No | `gemini` |
| `ENVIRONMENT` | Environment (development/production) | No | `development` |
| `REDIS_PASSWORD` | Redis password for production | No | `changeme` |

### Model Configuration

The system supports multiple LLM providers via LiteLLM:

- **OpenAI**: GPT-4, GPT-4o, GPT-3.5-turbo
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus
- **Google Gemini**: Gemini 2.0 Flash, Gemini Pro (recommended)
- **Ollama**: Local models (llama3, mistral, etc.)
- **Llamafile**: Local llamafile models

**Auto-detection**: If `LLM_PROVIDER` is not set, the system auto-detects from available API keys.

### RAG Configuration (v2 API)

The v2 API includes advanced RAG features:
- **Contextual Summarization**: Query-aware summaries of relevant chunks
- **Chunk Re-ranking**: Relevance-based ranking (keyword, LLM, or hybrid)
- **Configurable Parameters**: Control summary length, quality, and re-ranking method

### Docker Configuration

#### Development Environment
- **Ports**: App (8000), Nginx (8080), Redis (6379), PostgreSQL (5432)
- **Volumes**: Code mounted for hot reloading
- **Environment**: Debug logging, development tools

#### Production Environment
- **Ports**: Nginx (80, 443), App (internal), Redis (internal), Prometheus (9090)
- **Volumes**: Persistent data storage
- **Environment**: Production logging, resource limits, health checks

## 📊 Data Sources

- **PubMed**: Primary source for scientific papers
- **BugSigDB**: Reference database for microbial signatures
- **Custom Datasets**: Local data files for testing and development

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements.txt

# Set up pre-commit hooks
pre-commit install

# Run linting
flake8 .
black .

# Or use Docker for development
docker-compose -f docker-compose.dev.yml up -d
```

## 🐛 Troubleshooting

### Common Issues

#### Import Errors
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Or use Docker
docker-compose -f docker-compose.dev.yml up --build
```

#### API Key Issues
```bash
# Check environment variables
echo $NCBI_API_KEY
echo $GEMINI_API_KEY

# Verify .env file exists and is properly formatted
cat .env

# In Docker, check container environment
docker exec -it bugsigdb-analyzer-app-dev env | grep API
```

#### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
python3 start.py --port 8001

# Or use Docker with different ports
docker-compose -f docker-compose.dev.yml up -d
```

#### Docker Issues
```bash
# Check Docker daemon
docker info

# Check container logs
docker-compose -f docker-compose.dev.yml logs

# Restart Docker services
docker-compose -f docker-compose.dev.yml restart

# Clean up Docker resources
docker system prune -a
```

### Logs and Debugging

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

In Docker, view logs:
```bash
# View all service logs
docker-compose -f docker-compose.dev.yml logs -f

# View specific service logs
docker-compose -f docker-compose.dev.yml logs -f app

# View container logs directly
docker logs bugsigdb-analyzer-app-dev
```

## 📚 API Documentation

For detailed API documentation, visit:
- **Interactive Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **BugSigDB Team**: For the microbial signatures database
- **NCBI**: For PubMed data access
- **Google**: For Gemini AI capabilities
- **FastAPI**: For the excellent web framework
- **Docker**: For containerization technology
- **Nginx**: For reverse proxy and load balancing

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/waldronlab/BugsigdbAnalyzer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/waldronlab/BugsigdbAnalyzer/discussions)
- **Email**: [Your Email]

## 🔄 Changelog

### Version 1.0.0
- Initial release
- Basic paper analysis functionality
- Web interface
- PubMed integration
- AI-powered analysis
- Docker containerization
- Nginx reverse proxy
- Production deployment support

---

**Happy analyzing! 🧬🔬**
