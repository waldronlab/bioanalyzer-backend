# BioAnalyzer Backend

A specialized AI-powered backend API for analyzing scientific papers for BugSigDB curation readiness.

## Overview

BioAnalyzer Backend is a standalone Python API that analyzes scientific papers to extract 6 essential fields required for BugSigDB curation:

1. **Host Species** - What organism is being studied (e.g., Human, Mouse, Rat)
2. **Body Site** - Where the microbiome sample was collected (e.g., Gut, Oral, Skin)
3. **Condition** - What disease/treatment/exposure is being studied
4. **Sequencing Type** - What molecular method was used (e.g., 16S, metagenomics)
5. **Taxa Level** - What taxonomic level was analyzed (e.g., phylum, genus, species)
6. **Sample Size** - Number of samples analyzed

## Features

- **REST API**: Clean, well-documented REST endpoints
- **CLI Tool**: Command-line interface for terminal usage
- **AI-Powered Analysis**: Uses advanced NLP models for field extraction
- **Batch Processing**: Analyze multiple papers at once
- **Multiple Output Formats**: JSON, CSV, and table formats
- **Caching**: Built-in caching for improved performance
- **Health Monitoring**: System health checks and metrics

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Install from Source

```bash
# Clone the repository
git clone https://github.com/your-repo/bioanalyzer-backend.git
cd bioanalyzer-backend

# Install dependencies
pip install -r config/requirements.txt

# Install the package
pip install -e .
```

### Install with CLI Support

```bash
pip install -e .[cli]
```

## Usage

### Quick Start

```bash
# 1. Build containers
BioAnalyzer build

# 2. Start application
BioAnalyzer start

# 3. Analyze a paper
BioAnalyzer analyze 12345678

# 4. Check status
BioAnalyzer status

# 5. Stop when done
BioAnalyzer stop
```

### User-Friendly CLI Commands

```bash
# Setup Commands
BioAnalyzer build                    # Build Docker containers
BioAnalyzer start                    # Start the application
BioAnalyzer stop                     # Stop the application
BioAnalyzer restart                  # Restart the application
BioAnalyzer status                   # Check system status

# Analysis Commands
BioAnalyzer analyze <pmid>           # Analyze a single paper
BioAnalyzer analyze <pmid1,pmid2>    # Analyze multiple papers
BioAnalyzer analyze --file <file>    # Analyze papers from file
BioAnalyzer fields                   # Show field information

# Output Options
BioAnalyzer analyze <pmid> --format json|csv|table
BioAnalyzer analyze <pmid> --output results.json
BioAnalyzer analyze <pmid> --verbose
```

### Web Interface

Once started, visit:
- **Main Interface**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Advanced Usage

```bash
# API Server (for development)
python main.py --host 0.0.0.0 --port 8080

# CLI Tool (for development)
python cli.py analyze 12345678
python cli.py fields
```

### API Endpoints

#### Analyze Paper
```http
GET /api/v1/analyze/{pmid}
```

Analyze a single paper for BugSigDB fields.

**Example Response:**
```json
{
  "pmid": "12345678",
  "title": "Gut microbiome analysis in patients with IBD",
  "authors": ["Smith J", "Doe A"],
  "journal": "Nature Medicine",
  "publication_date": "2023-01-01",
  "fields": {
    "host_species": {
      "status": "PRESENT",
      "value": "Human",
      "confidence": 0.95,
      "reason_if_missing": null
    },
    "body_site": {
      "status": "PRESENT", 
      "value": "Gut",
      "confidence": 0.92,
      "reason_if_missing": null
    },
    "condition": {
      "status": "PRESENT",
      "value": "Inflammatory Bowel Disease",
      "confidence": 0.88,
      "reason_if_missing": null
    },
    "sequencing_type": {
      "status": "PRESENT",
      "value": "16S rRNA sequencing",
      "confidence": 0.90,
      "reason_if_missing": null
    },
    "taxa_level": {
      "status": "PRESENT",
      "value": "Genus",
      "confidence": 0.85,
      "reason_if_missing": null
    },
    "sample_size": {
      "status": "PRESENT",
      "value": "150",
      "confidence": 0.93,
      "reason_if_missing": null
    }
  },
  "curation_summary": "All essential fields are present and well-documented.",
  "analysis_timestamp": "2023-12-01T10:30:00Z",
  "processing_time": 2.5,
  "model_used": "biobert-base"
}
```

#### Get Field Information
```http
GET /api/v1/fields
```

Get information about the 6 essential BugSigDB fields.

#### Health Check
```http
GET /health
```

Check system health and status.

## Configuration

### Environment Variables

- `UVICORN_RELOAD`: Enable auto-reload (true/false)
- `LOG_LEVEL`: Set log level (debug/info/warning/error)
- `API_HOST`: API server host (default: 0.0.0.0)
- `API_PORT`: API server port (default: 8000)

### Configuration Files

- `config/requirements.txt`: Python dependencies
- `config/setup.py`: Package configuration
- `app/models/config.py`: Application configuration

## Development

### Project Structure

```
bioanalyzer-backend/
├── app/                    # Main application code
│   ├── api/               # API layer
│   │   ├── models/        # Pydantic models
│   │   ├── routers/       # API routes
│   │   └── utils/         # API utilities
│   ├── core/              # Core functionality
│   ├── models/            # ML models and config
│   ├── services/          # Business logic
│   └── utils/             # Utilities
├── config/                # Configuration files
├── scripts/               # Utility scripts
├── tests/                 # Test files
├── docs/                  # Documentation
├── cli.py                 # CLI interface
├── main.py                # API server entry point
└── setup.py               # Package setup
```

### Running Tests

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Run tests with coverage
pytest --cov=app
```

### Code Quality

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

## Docker Support

### Build Docker Image

```bash
docker build -t bioanalyzer-backend .
```

### Run with Docker

```bash
# Run API server
docker run -p 8000:8000 bioanalyzer-backend

# Run CLI
docker run -it bioanalyzer-backend python cli.py analyze 12345678
```

## API Integration

### Python Client Example

```python
import requests

# Analyze a paper
response = requests.get("http://localhost:8000/api/v1/analyze/12345678")
result = response.json()

# Get field information
response = requests.get("http://localhost:8000/api/v1/fields")
fields = response.json()
```

### cURL Examples

```bash
# Analyze a paper
curl -X GET "http://localhost:8000/api/v1/analyze/12345678"

# Get field information
curl -X GET "http://localhost:8000/api/v1/fields"

# Health check
curl -X GET "http://localhost:8000/health"
```

## Performance

- **Caching**: Built-in caching reduces redundant API calls
- **Batch Processing**: Efficient processing of multiple papers
- **Async Support**: Non-blocking API operations
- **Memory Management**: Optimized for large-scale analysis

## Monitoring

- **Health Checks**: `/health` endpoint for system status
- **Metrics**: `/metrics` endpoint for performance data
- **Logging**: Comprehensive logging for debugging
- **Error Handling**: Graceful error handling and reporting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

