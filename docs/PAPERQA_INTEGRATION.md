# Paper-QA Integration Guide

## Overview

BioAnalyzer uses Paper-QA as an agent for LLM interactions instead of making direct calls to the Gemini API. This provides:

- Multi-LLM Support: Paper-QA supports multiple LLM providers (Gemini, OpenAI, Claude, etc.) via litellm
- Agent-Based Reasoning: Better paper analysis through agent-based question answering
- Flexible Architecture: Easy to switch between different LLM providers without code changes

## Installation

### Option 1: Install from Local Directory (Recommended)

If you have the `paper-qa` directory in the project root:

```bash
pip install -e paper-qa/
```

### Option 2: Install from PyPI

```bash
pip install paper-qa>=5.0.0
```

### Option 3: Install via requirements.txt

```bash
pip install -r config/requirements.txt
```

## Configuration

### Environment Variables

Set your Gemini API key (or other LLM provider key):

```bash
export GEMINI_API_KEY=your_api_key_here
```

For other LLM providers, Paper-QA uses litellm which supports many providers. See [Paper-QA documentation](https://github.com/Future-House/paper-qa) for details.

### Using Paper-QA vs Direct Gemini API

By default, `UnifiedQA` uses Paper-QA agent. To disable Paper-QA and use direct Gemini API calls:

```python
from app.models.unified_qa import UnifiedQA

# Use Paper-QA (default)
qa = UnifiedQA(use_gemini=True, gemini_api_key="...", use_paperqa=True)

# Use direct Gemini API (fallback)
qa = UnifiedQA(use_gemini=True, gemini_api_key="...", use_paperqa=False)
```

## How It Works

`UnifiedQA.chat()` - what the main analysis pipeline actually calls
(`app/services/bugsigdb_analyzer.py`) - tries providers in this order,
verified against `app/models/unified_qa.py`:

1. **Paper-QA** (`PaperQAAgent`), when available and a Gemini API key is set
2. **LiteLLM** (`LLMProviderManager`), if Paper-QA is unavailable or errors -
   this is also how non-Gemini providers (OpenAI, Anthropic, Ollama) get
   used, since Paper-QA in this integration is Gemini-only
3. **GeminiQA** direct API call, as the last resort

All three provide a compatible `chat()` interface, so callers don't need to
know which one actually answered.

## Architecture

```
BioAnalyzer Code
    ↓
UnifiedQA.chat() (wrapper)
    ↓
PaperQAAgent (Gemini via litellm)   -- tried first
    ↓ (if unavailable/fails)
LLMProviderManager (LiteLLM: Gemini/OpenAI/Anthropic/Ollama)  -- tried second
    ↓ (if unavailable/fails)
GeminiQA (direct Gemini API call)  -- last resort
```

## Benefits

1. **Agent-First**: LLM requests go through the Paper-QA agent first when
   it's available, falling back to LiteLLM or a direct Gemini call only if
   Paper-QA is unavailable or errors (see How It Works above)
2. **Better Analysis**: Agent-based reasoning improves paper analysis quality
3. **LLM Flexibility**: Easy to switch to other LLMs (OpenAI, Claude, etc.) by changing settings
4. **Backward Compatible**: Existing code continues to work

## Troubleshooting

### Paper-QA Not Found

If you see "Paper-QA not available, falling back to GeminiQA":

1. Install Paper-QA: `pip install -e paper-qa/` or `pip install paper-qa`
2. Check that the `paper-qa` directory exists in the project root
3. Verify Python path includes the project root

### Import Errors

If you get import errors:

```bash
# Make sure you're in the project root
cd /path/to/BioAnalyzer-Backend

# Install Paper-QA
pip install -e paper-qa/

# Or install from PyPI
pip install paper-qa
```

### API Key Issues

Ensure your API key is set:

```bash
export GEMINI_API_KEY=your_key_here
```

Or pass it explicitly:

```python
qa = UnifiedQA(use_gemini=True, gemini_api_key="your_key_here")
```

## Testing

The integration is backward compatible. Existing tests should continue to work. To verify Paper-QA is being used:

1. Check logs for "PaperQAAgent initialized successfully"
2. If you see "GeminiQA initialized", Paper-QA is not being used (check installation)

## Future Enhancements

- Support for other LLM providers via Paper-QA settings
- Enhanced paper analysis using Paper-QA's advanced RAG capabilities
- Better field extraction through agent-based reasoning

