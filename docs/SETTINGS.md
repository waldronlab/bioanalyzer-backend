# BioAnalyzer Settings System

Flexible configuration system with support for multiple loading sources, preset configurations, settings inheritance, and migration.

## Overview

The settings system uses Pydantic models for validation and supports:

- Multiple loading sources: File (JSON/YAML), environment variables, CLI arguments
- Preset configurations: Fast, balanced, high_quality, development, production
- Settings inheritance: Inherit from base settings files
- Validation: Automatic validation with helpful error messages
- CLI commands: View, save, load, and manage settings
- Migration: Migrate old settings to new format

## Quick Start

### View Current Settings

```bash
BioAnalyzer settings view
```

### Save Current Settings

```bash
BioAnalyzer settings save
```

### Apply a Preset

```bash
BioAnalyzer settings preset fast --save
```

### Load Settings from File

```bash
BioAnalyzer settings load --file config.json --apply
```

## Settings Schema

The settings are organized into logical groups:

### API Configuration (`api`)

- `timeout`: API timeout in seconds (default: 30)
- `analysis_timeout`: Total analysis timeout in seconds (default: 45)
- `gemini_timeout`: Gemini API timeout in seconds (default: 30)
- `frontend_timeout`: API client timeout in seconds (default: 60)
- `ncbi_timeout`: NCBI API timeout in seconds (default: 60)
- `ncbi_rate_limit_delay`: NCBI rate limit delay in seconds (default: 0.34)
- `max_concurrent_requests`: Maximum concurrent requests (default: 3)
- `verify_ssl`: Verify SSL certificates (default: true)

### LLM Configuration (`llm`)

- `provider`: LLM provider (openai, anthropic, gemini, ollama, llamafile)
- `model`: Specific model to use
- `gemini_api_key`: Gemini API key
- `openai_api_key`: OpenAI API key
- `anthropic_api_key`: Anthropic API key
- `ollama_base_url`: Ollama server URL (default: http://localhost:11434)

### RAG Configuration (`rag`)

- `enabled`: Enable RAG features (default: true)
- `top_k_chunks`: Number of top chunks to use (default: 10)
- `rerank_method`: Re-ranking method - keyword, llm, hybrid (default: hybrid)
- `summary_length`: Summary length - short, medium, long (default: medium)
- `summary_quality`: Summary quality - fast, balanced, high (default: balanced)
- `summary_provider`: LLM provider for summarization
- `summary_model`: Model for summarization
- `use_cache`: Enable summary caching (default: true)
- `max_summary_key_points`: Maximum key points per summary (default: 5)

### Cache Configuration (`cache`)

- `enabled`: Enable caching (default: true)
- `validity_hours`: Cache validity in hours (default: 24)
- `max_size`: Maximum cache entries (default: 1000)
- `directory`: Cache directory (default: cache)

### Rate Limiting (`rate_limit`)

- `enabled`: Enable rate limiting (default: true)
- `requests_per_minute`: Requests per minute limit (default: 60)

### Logging Configuration (`logging`)

- `level`: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
- `format`: Log format string
- `file_format`: File log format string
- `directory`: Log directory (default: logs)
- `max_file_size`: Maximum log file size in bytes (default: 10MB)
- `max_files`: Maximum number of rotated log files (default: 5)

### Retrieval Configuration (`retrieval`)

- `use_fulltext`: Use full text retrieval (default: false)
- `ncbi_api_key`: NCBI API key
- `email`: Email for NCBI API requests
- `ncbi_api_url`: NCBI API URL

### Security Configuration (`security`)

- `cors_origins`: CORS allowed origins (default: ["*"])
- `enable_request_id`: Enable request ID tracking (default: true)

## Loading Settings

Settings are loaded with the following priority (highest to lowest):

1. CLI overrides (highest priority)
2. File settings (JSON or YAML)
3. Preset settings
4. Environment variables
5. Defaults (lowest priority)

### From File

Create a settings file (JSON or YAML):

**settings.json:**
```json
{
  "version": "1.0.0",
  "preset": "balanced",
  "api": {
    "timeout": 30,
    "analysis_timeout": 45
  },
  "rag": {
    "summary_quality": "balanced",
    "top_k_chunks": 10
  }
}
```

**settings.yaml:**
```yaml
version: "1.0.0"
preset: "balanced"
api:
  timeout: 30
  analysis_timeout: 45
rag:
  summary_quality: "balanced"
  top_k_chunks: 10
```

Load from file:
```python
from app.core.settings import BioAnalyzerSettings

settings = BioAnalyzerSettings.from_file(Path("settings.json"))
```

### From Environment Variables

Environment variables are automatically loaded. The naming convention follows:
- `API_TIMEOUT` → `api.timeout`
- `LLM_PROVIDER` → `llm.provider`
- `RAG_SUMMARY_QUALITY` → `rag.summary_quality`
- etc.

```python
from app.core.settings import BioAnalyzerSettings

settings = BioAnalyzerSettings.from_env()
```

### From Preset

```python
from app.core.settings import BioAnalyzerSettings

settings = BioAnalyzerSettings.from_preset("fast")
```

### Using Settings Manager

The `SettingsManager` provides a convenient way to load settings from multiple sources:

```python
from app.core.settings import SettingsManager

manager = SettingsManager()
settings = manager.load(
    from_file=Path("settings.json"),
    from_env=True,
    from_preset="balanced",
    cli_overrides={"api": {"timeout": 60}}
)
```

## Preset Configurations

### Fast

Optimized for speed with minimal quality trade-offs:

- Short summaries
- Fast quality mode
- Keyword-based re-ranking
- Reduced chunk count (5)
- Lower timeouts

```bash
BioAnalyzer settings preset fast --save
```

### Balanced (Default)

Balanced between speed and quality:

- Medium summaries
- Balanced quality mode
- Hybrid re-ranking
- Standard chunk count (10)
- Standard timeouts

```bash
BioAnalyzer settings preset balanced --save
```

### High Quality

Maximum quality with longer processing time:

- Long summaries
- High quality mode
- LLM-based re-ranking
- Increased chunk count (20)
- Extended timeouts

```bash
BioAnalyzer settings preset high_quality --save
```

### Development

Development environment settings:

- DEBUG logging level
- Caching enabled
- Development environment

```bash
BioAnalyzer settings preset development --save
```

### Production

Production environment settings:

- INFO logging level
- Rate limiting enabled
- Security features enabled
- Production environment

```bash
BioAnalyzer settings preset production --save
```

## Settings Inheritance

Settings files can inherit from other settings files:

**base.json:**
```json
{
  "api": {
    "timeout": 30
  },
  "rag": {
    "enabled": true
  }
}
```

**custom.json:**
```json
{
  "inherit_from": "base.json",
  "api": {
    "timeout": 60
  }
}
```

When loading `custom.json`, it will inherit all settings from `base.json` and override with values from `custom.json`.

## CLI Commands

### View Settings

View current settings in various formats:

```bash
# Table format (default)
BioAnalyzer settings view

# JSON format
BioAnalyzer settings view --format json

# YAML format
BioAnalyzer settings view --format yaml

# Save to file
BioAnalyzer settings view --format json --output settings.json
```

### Save Settings

Save current settings to file:

```bash
# Save to default location (~/.bioanalyzer/settings.json)
BioAnalyzer settings save

# Save to custom location
BioAnalyzer settings save --file config.json

# Save as YAML
BioAnalyzer settings save --format yaml

# Save preset configuration
BioAnalyzer settings save --preset fast --file fast-config.json
```

### Load Settings

Load settings from file:

```bash
# Load from file
BioAnalyzer settings load --file config.json

# Load and apply to environment
BioAnalyzer settings load --file config.json --apply
```

### Apply Preset

Apply a preset configuration:

```bash
# View preset (doesn't save)
BioAnalyzer settings preset fast

# Apply and save preset
BioAnalyzer settings preset fast --save
```

### Migrate Settings

Migrate old settings to new format:

```bash
BioAnalyzer settings migrate --file old-settings.json --output new-settings.json
```

## Migration

The settings system includes a migration utility to convert old settings formats to the new format.

### Automatic Migration

When loading old settings, the system will attempt to automatically map old keys to new structure:

- `api_timeout` → `api.timeout`
- `llm_provider` → `llm.provider`
- `rag_enabled` → `rag.enabled`

### Manual Migration

Use the CLI command:

```bash
BioAnalyzer settings migrate --file old-settings.json
```

This will create a new file with `.new` extension containing the migrated settings.

## API Reference

### BioAnalyzerSettings

Main settings class.

**Methods:**

- `from_file(file_path: Path) -> BioAnalyzerSettings`: Load from file
- `from_env() -> BioAnalyzerSettings`: Load from environment
- `from_preset(preset_name: str) -> BioAnalyzerSettings`: Load preset
- `to_file(file_path: Path, format: str = 'json')`: Save to file
- `merge(other: BioAnalyzerSettings) -> BioAnalyzerSettings`: Merge settings
- `apply_to_environment()`: Apply to environment variables

### SettingsManager

Settings manager for loading and saving.

**Methods:**

- `load(**kwargs) -> BioAnalyzerSettings`: Load settings
- `save(settings, file_path, format)`: Save settings
- `get_settings() -> BioAnalyzerSettings`: Get current settings
- `migrate_settings(old_file, new_file) -> BioAnalyzerSettings`: Migrate settings

### Global Functions

- `load_settings(**kwargs) -> BioAnalyzerSettings`: Load using global manager
- `get_settings() -> BioAnalyzerSettings`: Get current settings
- `save_settings(settings, **kwargs)`: Save using global manager

## Examples

### Programmatic Usage

```python
from app.core.settings import load_settings, get_settings, save_settings

# Load settings
settings = load_settings(
    from_file=Path("config.json"),
    from_preset="balanced"
)

# Get current settings
current = get_settings()

# Modify and save
current.rag.top_k_chunks = 15
save_settings(current)
```

### Integration with Application

```python
from app.core.settings import load_settings

# Load settings at startup
settings = load_settings(
    from_file=Path("settings.json"),
    from_env=True
)

# Apply to environment for backward compatibility
settings.apply_to_environment()

# Use settings in your code
timeout = settings.api.timeout
rag_enabled = settings.rag.enabled
```

## Best Practices

1. **Use presets for common configurations**: Start with a preset and customize as needed
2. **Store sensitive data in environment variables**: Don't commit API keys to settings files
3. **Use inheritance for shared configurations**: Create base settings and inherit in specific environments
4. **Version your settings**: Include version field for migration tracking
5. **Validate before deployment**: Use `settings view` to verify configuration

## Troubleshooting

### Settings not loading

- Check file path is correct
- Verify JSON/YAML syntax is valid
- Check file permissions

### Validation errors

- Review error message for specific field
- Check enum values (e.g., summary_quality must be "fast", "balanced", or "high")
- Verify numeric ranges (e.g., timeout must be between 1-300)

### Environment variables not applied

- Ensure `from_env=True` when loading
- Check environment variable names match expected format
- Use `--apply` flag when loading from file via CLI

## See Also

- [Architecture Documentation](ARCHITECTURE.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
- [Quick Start Guide](QUICKSTART.md)

