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

1. **Initialization**: `UnifiedQA` tries to initialize `PaperQAAgent` first
2. **Fallback**: If Paper-QA is not available or fails, it falls back to `GeminiQA` (direct API)
3. **Interface**: Both provide the same interface, so existing code works without changes

## Architecture

```
BioAnalyzer Code
    ↓
UnifiedQA (wrapper)
    ↓
PaperQAAgent (Paper-QA agent) → Gemini via litellm
    OR
GeminiQA (direct API) → Gemini API
```

## Benefits

1. **No Direct API Calls**: All LLM requests go through Paper-QA agent
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

