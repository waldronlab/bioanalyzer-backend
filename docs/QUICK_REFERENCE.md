# BioAnalyzer CLI - Quick Reference Card

## 🚀 Quick Start
```bash
BioAnalyzer build    # Build containers
BioAnalyzer start    # Start application
BioAnalyzer analyze 12345678    # Analyze paper
BioAnalyzer stop     # Stop application
```

## 📋 All Commands

| Command | Description |
|---------|-------------|
| `BioAnalyzer help` | Show help |
| `BioAnalyzer build` | Build Docker containers |
| `BioAnalyzer start` | Start application |
| `BioAnalyzer stop` | Stop application |
| `BioAnalyzer restart` | Restart application |
| `BioAnalyzer status` | Check system status |
| `BioAnalyzer analyze <pmid>` | Analyze single paper |
| `BioAnalyzer analyze <pmid1,pmid2>` | Analyze multiple papers |
| `BioAnalyzer analyze --file <file>` | Analyze from file |
| `BioAnalyzer fields` | Show field information |

## 🔬 Analysis Examples

```bash
# Single paper
BioAnalyzer analyze 12345678

# Multiple papers
BioAnalyzer analyze 12345678,87654321,11223344

# From file
BioAnalyzer analyze --file pmids.txt

# JSON output
BioAnalyzer analyze 12345678 --format json

# Save results
BioAnalyzer analyze 12345678 --output results.json

# Verbose mode
BioAnalyzer analyze 12345678 --verbose
```

## 📊 Output Formats

- `--format table` (default) - Human-readable table
- `--format json` - JSON format
- `--format csv` - CSV format

## 🌐 Web Interface

- **Main App:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs

## ❓ Troubleshooting

```bash
BioAnalyzer status    # Check if running
BioAnalyzer restart   # Restart if issues
BioAnalyzer help      # Get help
```

## 📁 File Formats

- `.txt` - One PMID per line
- `.csv` - PMIDs in first column  
- `.xlsx` - PMIDs in first column

## 🧬 BugSigDB Fields

1. **Host Species** - Organism studied
2. **Body Site** - Sample collection location
3. **Condition** - Disease/treatment studied
4. **Sequencing Type** - Molecular method used
5. **Taxa Level** - Taxonomic level analyzed
6. **Sample Size** - Number of samples

## 📈 Status Values

- ✅ **PRESENT** - Complete information
- ⚠️ **PARTIALLY_PRESENT** - Some information
- ❌ **ABSENT** - Missing information

---

**Need more help?** Run `BioAnalyzer help` or visit the web interface!
