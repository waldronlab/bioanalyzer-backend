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
- Builds the backend Docker image
- Builds the frontend Docker image (if available)
- Prepares all necessary containers

**Example:**
```bash
$ BioAnalyzer build
🔨 Building BioAnalyzer containers...
📦 Building backend image...
✅ Backend image built successfully!
📦 Building frontend image...
✅ Frontend image built successfully!
🎉 All containers built successfully!
```

### `BioAnalyzer start`
Start the BioAnalyzer application.

```bash
BioAnalyzer start                    # Start normally
BioAnalyzer start --interactive      # Start with interactive mode
```

**What it does:**
- Starts the backend API server
- Starts the frontend web interface
- Makes the application available at:
  - Web Interface: http://localhost:3000
  - API Documentation: http://localhost:8000/docs

**Example:**
```bash
$ BioAnalyzer start
🚀 Starting BioAnalyzer application...
🔧 Starting backend API...
⏳ Waiting for backend to be ready...
✅ Backend API is running at http://localhost:8000
🌐 Starting frontend...
✅ Frontend is running at http://localhost:3000

🎉 BioAnalyzer is now running!
📱 Web Interface: http://localhost:3000
🔧 API Documentation: http://localhost:8000/docs
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
✅ Stopped bioanalyzer-api
✅ Stopped bioanalyzer-frontend
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
- Container status
- API health
- Web interface availability

**Example:**
```bash
$ BioAnalyzer status
📊 BioAnalyzer System Status
========================================
Docker: ✅ Available
Backend Image: ✅ Built
Backend Container: ✅ Up 2 minutes (healthy)
Frontend Container: ✅ Up 2 minutes (healthy)
API Health: ✅ Healthy
🌐 Web Interface: http://localhost:3000
🔧 API Documentation: http://localhost:8000/docs
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

**CSV Format:**
```bash
BioAnalyzer analyze 12345678 --format csv
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

## 🌐 Web Interface

Once you start BioAnalyzer, you can also use the web interface:

- **Main Interface:** http://localhost:3000
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

**2. "Backend not found"**
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
- Backend: `BioAnalyzer-Backend/`
- Frontend: `BioAnalyzer-Frontend/`
- Docker Images: `bioanalyzer-backend`, `bioanalyzer-frontend`
- Containers: `bioanalyzer-api`, `bioanalyzer-frontend`

### Environment Variables
- `BIOANALYZER_PATH` - Path to BioAnalyzer backend
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
- **Web Interface:** http://localhost:3000 (when running)
- **GitHub Repository:** https://github.com/your-repo/bioanalyzer-backend

---

**BioAnalyzer CLI - Making BugSigDB analysis simple and accessible! 🧬**
