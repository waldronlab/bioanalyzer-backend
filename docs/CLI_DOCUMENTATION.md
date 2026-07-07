# BioAnalyzer CLI - User-Friendly Command Reference

## 🧬 BioAnalyzer - Curatable Signature Analysis Tool

BioAnalyzer is a user-friendly command-line tool for analyzing scientific papers for BugSigDB curation requirements. It provides simple, intuitive commands that make it easy to analyze papers for the 6 essential BugSigDB fields.

## 📋 Quick Start

```bash
# 1. Build the containers
BioAnalyzer build

# 2. Start the application
BioAnalyzer start

# 3. Analyze a paper
BioAnalyzer analyze 12345678

# 4. Check status
BioAnalyzer status

# 5. Stop when done
BioAnalyzer stop
```

## 🔧 Setup Commands

### `BioAnalyzer build`
Build Docker containers for the application.

```bash
BioAnalyzer build
```

**What it does:**
- Builds the package (backend) Docker image
- Prepares the container for API and CLI use

**Example:**
```bash
$ BioAnalyzer build
🔨 Building BioAnalyzer containers...
📦 Building package image...
✅ Package image built successfully!
✅ All containers built successfully!
```

### `BioAnalyzer start`
Start the BioAnalyzer application.

```bash
BioAnalyzer start                    # Start normally
BioAnalyzer start --interactive      # Start with interactive mode
```

**What it does:**
- Starts the backend API server (and Redis if using docker-compose)
- Makes the API available at http://localhost:8000
- API docs at http://localhost:8000/docs

**Example:**
```bash
$ BioAnalyzer start
🚀 Starting BioAnalyzer application...
🔧 Starting API...
⏳ Waiting for API health (timeout: 60s)...
✅ API is running at http://localhost:8000

🎉 BioAnalyzer backend is now running!
🔧 API: http://localhost:8000
📖 API Documentation: http://localhost:8000/docs
```

### `BioAnalyzer stop`
Stop the BioAnalyzer application.

```bash
BioAnalyzer stop
```

**What it does:**
- Stops all running containers
- Cleans up resources
- Preserves data and cache

**Example:**
```bash
$ BioAnalyzer stop
🛑 Stopping BioAnalyzer application...
✅ Stopped bioanalyzer-package
✅ Stopped bioanalyzer-redis
✅ BioAnalyzer application stopped
```

### `BioAnalyzer restart`
Restart the BioAnalyzer application.

```bash
BioAnalyzer restart
```

**What it does:**
- Stops the application
- Starts it again
- Useful for applying changes

### `BioAnalyzer status`
Check the system status.

```bash
BioAnalyzer status
```

**What it shows:**
- Docker availability
- Package image and container status
- API health

**Example:**
```bash
$ BioAnalyzer status
📊 BioAnalyzer System Status
========================================
Docker: ✅ Available
Package Image: ✅ Built
Package Container: ✅ Up 2 minutes (healthy)
API Health: ✅ Healthy
🔧 API: http://localhost:8000
📖 API Documentation: http://localhost:8000/docs
```

## 🔬 Analysis Commands

### `BioAnalyzer analyze <pmid>`
Analyze a single paper by PMID.

```bash
BioAnalyzer analyze <pmid>                    # Basic analysis
BioAnalyzer analyze <pmid> --format json      # JSON output
BioAnalyzer analyze <pmid> --output file.json # Save to file
BioAnalyzer analyze <pmid> --verbose          # Verbose output
```

**Examples:**
```bash
# Analyze a single paper
BioAnalyzer analyze 12345678

# Analyze with JSON output
BioAnalyzer analyze 12345678 --format json

# Save results to file
BioAnalyzer analyze 12345678 --output results.json

# Verbose analysis
BioAnalyzer analyze 12345678 --verbose
```

### `BioAnalyzer analyze <pmid1,pmid2,pmid3>`
Analyze multiple papers using comma-separated PMIDs.

```bash
BioAnalyzer analyze 12345678,87654321,11223344
BioAnalyzer analyze 12345678,87654321 --format csv
BioAnalyzer analyze 12345678,87654321 --output batch_results.csv
```

**Example:**
```bash
$ BioAnalyzer analyze 12345678,87654321,11223344
🔬 Analyzing 3 paper(s)...
[1/3] Analyzing PMID: 12345678
✅ Analysis completed for PMID 12345678
[2/3] Analyzing PMID: 87654321
✅ Analysis completed for PMID 87654321
[3/3] Analyzing PMID: 11223344
✅ Analysis completed for PMID 11223344
```

### `BioAnalyzer analyze --file <file>`
Analyze papers from a file.

```bash
BioAnalyzer analyze --file pmids.txt
BioAnalyzer analyze --file pmids.csv --format json
BioAnalyzer analyze --file pmids.xlsx --output results.csv
```

**Supported file formats:**
- `.txt` - One PMID per line
- `.csv` - PMIDs in first column
- `.xlsx` - PMIDs in first column

**Example file (pmids.txt):**
```
12345678
87654321
11223344
```

**Example:**
```bash
$ BioAnalyzer analyze --file pmids.txt
📁 Loaded 3 PMIDs from pmids.txt
🔬 Analyzing 3 paper(s)...
[1/3] Analyzing PMID: 12345678
✅ Analysis completed for PMID 12345678
[2/3] Analyzing PMID: 87654321
✅ Analysis completed for PMID 87654321
[3/3] Analyzing PMID: 11223344
✅ Analysis completed for PMID 11223344
```

### `BioAnalyzer fields`
Show information about BugSigDB fields.

```bash
BioAnalyzer fields
```

**What it shows:**
- Description of all 6 essential fields
- Field requirements
- Status value meanings

**Example:**
```bash
$ BioAnalyzer fields

🧬 BioAnalyzer - BugSigDB Essential Fields
==========================================

📋 6 Essential Fields for BugSigDB Curation:

🧬 Host Species (host_species):
   Description: The host organism being studied (e.g., Human, Mouse, Rat)
   Required: Yes

📍 Body Site (body_site):
   Description: Where the microbiome sample was collected (e.g., Gut, Oral, Skin)
   Required: Yes

🏥 Condition (condition):
   Description: What disease, treatment, or exposure is being studied
   Required: Yes

🔬 Sequencing Type (sequencing_type):
   Description: What molecular method was used (e.g., 16S, metagenomics)
   Required: Yes

🌳 Taxa Level (taxa_level):
   Description: What taxonomic level was analyzed (e.g., phylum, genus, species)
   Required: Yes

👥 Sample Size (sample_size):
   Description: Number of samples or participants analyzed
   Required: Yes

📊 Field Status Values:
   ✅ PRESENT: Information is complete and clear
   ⚠️  PARTIALLY_PRESENT: Some information available but incomplete
   ❌ ABSENT: Information is missing
```

### `BioAnalyzer analyze-url <url>`
Analyze complete studies from URLs using the enhanced workflow.

```bash
BioAnalyzer analyze-url https://example.org/study-001
BioAnalyzer analyze-url https://study.com/one --format json
BioAnalyzer analyze-url https://study.com/one --embedding-model ollama/nomic-embed-text
BioAnalyzer analyze-url --file urls.txt --output url_results.txt
```

**Options:**
- `--embedding-model`: Embedding backend (default: `gemini/text-embedding-004`)
- `--llm-model`: LLM for extraction (default: `gemini/gemini-2.0-flash`)
- `--poll-interval`: Seconds between status checks (default: 5)
- `--timeout`: Max seconds to wait per job (default: 300)
- `--format`: `table` (default) or `json`
- `--output`: Save aggregated results to a file

**Sample Flow:**
```bash
BioAnalyzer analyze-url https://journals.org/doi/10.1016/j.sample --format table
```
- Starts a background job via `POST /api/v1/analyze-url`
- Polls `/api/v1/analysis-status/{job_id}`
- Fetches detailed experiments from `/api/v1/analysis-result/{job_id}`
- Displays number of experiments, signatures, readiness, and metadata

## 📊 Output Options

### Output Formats

**Table Format (Default):**
```bash
BioAnalyzer analyze 12345678
```

**JSON Format:**
```bash
BioAnalyzer analyze 12345678 --format json
```

**CSV Format (curator-facing, matches `curator_table`/`curator_table_r`):**

A fixed-schema CSV for handing off predictions to the `curator_table`/
`curator_table_r` review tools - 5 value fields (Host Species, Body Site,
Condition, Sample Size, Sequencing Type; Taxa Level is intentionally
excluded), plus an Ontology ID for the first three, plus Differential
Abundance and In bsgdb. See [CURATOR_DESK_CSV_FORMAT.md](CURATOR_DESK_CSV_FORMAT.md)
for the full column list and contract. Always deduplicated by PMID.

```bash
BioAnalyzer analyze 12345678 --format csv
BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv
```

`--format curator_desk_csv` is an accepted alias for the exact same output
(kept for older scripts/docs) - there is no difference between the two.

**Detailed CSV Format (validation tooling only):**

A separate, older CSV covering all 6 fields (including Taxa Level) with a
full `PRESENT`/`PARTIALLY_PRESENT`/`ABSENT` status per field. This is *not*
what `curator_table`/`curator_table_r` expect - it exists only for internal
validation scripts (e.g. `scripts/eval/confusion_matrix_analysis.py`).

```bash
BioAnalyzer analyze 12345678 --format detailed_csv
```

**XML Format:**
```bash
BioAnalyzer analyze 12345678 --format xml
```

### Save Results

**Save to File:**
```bash
BioAnalyzer analyze 12345678 --output results.json
BioAnalyzer analyze 12345678,87654321 --output batch_results.csv
```

### Verbose Output

**Verbose Mode:**
```bash
BioAnalyzer analyze 12345678 --verbose
```

## 🌐 API

Once you start BioAnalyzer, the backend API is available at:

- **API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## 📖 Complete Examples

### Basic Workflow
```bash
# 1. Build containers
BioAnalyzer build

# 2. Start application
BioAnalyzer start

# 3. Check status
BioAnalyzer status

# 4. Analyze a paper
BioAnalyzer analyze 12345678

# 5. Analyze multiple papers
BioAnalyzer analyze 12345678,87654321,11223344

# 6. Analyze from file
BioAnalyzer analyze --file pmids.txt --format json --output results.json

# 7. Stop when done
BioAnalyzer stop
```

### Advanced Usage
```bash
# Build and start in one go
BioAnalyzer build && BioAnalyzer start

# Analyze with custom output
BioAnalyzer analyze 12345678 --format csv --output paper_analysis.csv --verbose

# Check what fields are analyzed
BioAnalyzer fields

# Restart if needed
BioAnalyzer restart

# Check system health
BioAnalyzer status
```

## ❓ Help and Support

### Get Help
```bash
BioAnalyzer help                    # Show all commands
BioAnalyzer analyze --help         # Show analyze command help
BioAnalyzer start --help           # Show start command help
```

### Common Issues

**1. "Docker not found"**
```bash
# Install Docker first
sudo apt-get install docker.io
sudo systemctl start docker
sudo usermod -aG docker $USER
# Log out and back in
```

**2. "Package container not found"**
```bash
# Make sure you're in the right directory
cd BioAnalyzer-Backend
./BioAnalyzer help
```

**3. "Analysis failed"**
```bash
# Check if backend is running
BioAnalyzer status

# Restart if needed
BioAnalyzer restart
```

**4. "Permission denied"**
```bash
# Make sure the script is executable
chmod +x BioAnalyzer
```

## 🔧 Technical Details

### System Requirements
- Docker and Docker Compose
- Python 3.8+ (for local development)
- 4GB+ RAM recommended
- 2GB+ disk space

### File Locations
- Package: `BioAnalyzer-Backend/`
- Docker Image: `bioanalyzer-package`
- Containers: `bioanalyzer-package`, `bioanalyzer-redis`

### Environment Variables
- `BIOANALYZER_PATH` - Path to BioAnalyzer package
- `DOCKER_HOST` - Docker daemon location

## 🎯 Best Practices

1. **Always build first:** Run `BioAnalyzer build` before starting
2. **Check status:** Use `BioAnalyzer status` to verify everything is running
3. **Use verbose mode:** Add `--verbose` when troubleshooting
4. **Save results:** Use `--output` to save analysis results
5. **Stop when done:** Run `BioAnalyzer stop` to free up resources

## 📚 Additional Resources

- **BugSigDB:** https://bugsigdb.org/
- **API Documentation:** http://localhost:8000/docs (when running)
- **GitHub Repository:** https://github.com/your-repo/bioanalyzer-package

---

**BioAnalyzer CLI - Making BugSigDB analysis simple and accessible! 🧬**
