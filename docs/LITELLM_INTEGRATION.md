# LiteLLM Multi-Provider LLM Support

## Overview

BioAnalyzer now supports multiple LLM providers through **LiteLLM**, providing a unified interface for:
- **OpenAI** (GPT-4, GPT-4o, GPT-3.5-turbo, etc.)
- **Anthropic** (Claude 3.5 Sonnet, Claude 3 Opus, etc.)
- **Google Gemini** (Gemini 2.0 Flash, Gemini 1.5 Pro, etc.)
- **Local Models** (Ollama, llamafile)

This integration replaces direct API calls with a provider-agnostic abstraction layer, making it easy to switch between providers without code changes.

## Installation

LiteLLM is included in the requirements:

```bash
pip install -r config/requirements.txt
```

Or install directly:

```bash
pip install litellm>=1.50.0
```

## Configuration

### Environment Variables

Set the LLM provider and model using environment variables:

```bash
# Select provider (optional - auto-detects if not set)
export LLM_PROVIDER=openai  # Options: openai, anthropic, gemini, ollama, llamafile

# Select model (optional - uses provider default if not set)
export LLM_MODEL=gpt-4o  # e.g., "gpt-4o", "claude-3-5-sonnet-20241022", "gemini/gemini-2.0-flash"

# Provider-specific API keys
export OPENAI_API_KEY=your_openai_key_here
export ANTHROPIC_API_KEY=your_anthropic_key_here
export GEMINI_API_KEY=your_gemini_key_here

# For local models (Ollama)
export OLLAMA_BASE_URL=http://localhost:11434  # Optional, defaults to localhost:11434
```

### Auto-Detection

If `LLM_PROVIDER` is not set, the system auto-detects the provider based on available API keys in this order:
1. OpenAI (if `OPENAI_API_KEY` is set)
2. Anthropic (if `ANTHROPIC_API_KEY` is set)
3. Gemini (if `GEMINI_API_KEY` is set)
4. Ollama (if `OLLAMA_BASE_URL` or `OLLAMA_HOST` is set)
5. Defaults to Gemini if available, otherwise OpenAI

## Supported Providers and Models

### OpenAI

**Required:** `OPENAI_API_KEY`

**Supported Models:**
- `gpt-4o` (default)
- `gpt-4o-mini`
- `gpt-4-turbo`
- `gpt-4`
- `gpt-3.5-turbo`

**Example:**
```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export OPENAI_API_KEY=sk-...
```

### Anthropic (Claude)

**Required:** `ANTHROPIC_API_KEY`

**Supported Models:**
- `claude-3-5-sonnet-20241022` (default)
- `claude-3-opus-20240229`
- `claude-3-sonnet-20240229`
- `claude-3-haiku-20240307`

**Example:**
```bash
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-3-5-sonnet-20241022
export ANTHROPIC_API_KEY=sk-ant-...
```

### Google Gemini

**Required:** `GEMINI_API_KEY`

**Supported Models:**
- `gemini/gemini-2.0-flash` (default)
- `gemini/gemini-1.5-pro`
- `gemini/gemini-1.5-flash`

**Example:**
```bash
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini/gemini-2.0-flash
export GEMINI_API_KEY=...
```

### Ollama (Local Models)

**Required:** Ollama running locally (no API key needed)

**Supported Models:**
- `ollama/llama3` (default)
- `ollama/llama3.1`
- `ollama/mistral`
- `ollama/codellama`

**Setup:**
1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama3`
3. Configure:

```bash
export LLM_PROVIDER=ollama
export LLM_MODEL=ollama/llama3
export OLLAMA_BASE_URL=http://localhost:11434  # Optional
```

### llamafile (Local Models)

**Required:** llamafile installed locally (no API key needed)

**Supported Models:**
- `llamafile/llama-3.2-3b` (default)
- `llamafile/llama-3.1-8b`

**Setup:**
1. Download and run llamafile: https://github.com/Mozilla-Ocho/llamafile
2. Configure:

```bash
export LLM_PROVIDER=llamafile
export LLM_MODEL=llamafile/llama-3.2-3b
```

## Usage

### Basic Usage

```python
from app.models.unified_qa import UnifiedQA

# Auto-detect provider from environment
qa = UnifiedQA()

# Or specify provider and model explicitly
qa = UnifiedQA(provider="openai", model="gpt-4o")

# Use for chat
response = await qa.chat("What is the microbiome?")
print(response["text"])
print(f"Confidence: {response['confidence']}")
```

### Provider-Specific Usage

```python
# OpenAI
qa = UnifiedQA(provider="openai", model="gpt-4o")

# Anthropic
qa = UnifiedQA(provider="anthropic", model="claude-3-5-sonnet-20241022")

# Gemini
qa = UnifiedQA(provider="gemini", model="gemini/gemini-2.0-flash")

# Ollama (local)
qa = UnifiedQA(provider="ollama", model="ollama/llama3")
```

### Backward Compatibility

The old API still works for backward compatibility:

```python
# Old API (deprecated but still works)
qa = UnifiedQA(use_gemini=True, gemini_api_key="...")

# New API (recommended)
qa = UnifiedQA(provider="gemini", model="gemini/gemini-2.0-flash")
```

## API Reference

### UnifiedQA

```python
class UnifiedQA:
    def __init__(
        self,
        provider: Optional[str] = None,  # Auto-detect if None
        model: Optional[str] = None,      # Use provider default if None
        use_gemini: Optional[bool] = None,  # Deprecated
        gemini_api_key: Optional[str] = None,  # For backward compatibility
        use_paperqa: bool = True  # Use Paper-QA for complex analysis
    )
    
    async def chat(prompt: str) -> Dict[str, Any]
    async def ask_question(question: str, context: Optional[str] = None, pmid: Optional[str] = None) -> Dict
    async def analyze_image(image_url: str, prompt: str, model: Optional[str] = None) -> str
```

### LLMProviderManager

```python
from app.models.llm_provider import LLMProviderManager

# Initialize
manager = LLMProviderManager(provider="openai", model="gpt-4o")

# Chat
response = await manager.chat(
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7,
    max_tokens=1000,
    timeout=60.0
)

# Image analysis
result = await manager.analyze_image(
    image_url="https://example.com/image.png",
    prompt="Describe this image",
    timeout=60.0
)

# Get available providers
providers = LLMProviderManager.get_available_providers()

# Get supported models for a provider
models = LLMProviderManager.get_supported_models("openai")
```

## Migration Guide

### From Direct Gemini API

**Before:**
```python
from app.models.unified_qa import UnifiedQA

qa = UnifiedQA(use_gemini=True, gemini_api_key="...")
```

**After:**
```python
from app.models.unified_qa import UnifiedQA

# Option 1: Use environment variables
export LLM_PROVIDER=gemini
export GEMINI_API_KEY=...
qa = UnifiedQA()

# Option 2: Specify explicitly
qa = UnifiedQA(provider="gemini", model="gemini/gemini-2.0-flash")
```

### From Paper-QA Only

Paper-QA is still supported as a fallback for complex analysis. LiteLLM is now the primary interface, with Paper-QA used when:
- LiteLLM is not available
- Complex agent-based reasoning is needed
- `use_paperqa=True` is explicitly set

## Troubleshooting

### Provider Not Found

If you get "Unknown provider" error:
1. Check that the provider name is correct (lowercase)
2. Verify required API keys are set
3. Check that LiteLLM is installed: `pip install litellm`

### Model Not Found

If you get model errors:
1. Verify the model name matches LiteLLM's format
2. Check provider-specific model naming (e.g., `gemini/gemini-2.0-flash`)
3. For local models, ensure the model is installed/running

### Timeout Errors

Increase timeout in config:
```bash
export GEMINI_TIMEOUT=60  # or appropriate timeout for your provider
```

### Local Models Not Working

For Ollama:
1. Ensure Ollama is running: `ollama serve`
2. Verify model is pulled: `ollama list`
3. Check `OLLAMA_BASE_URL` is correct

For llamafile:
1. Ensure llamafile server is running
2. Check that the model file is accessible

## Benefits

1. **Unified Interface**: Same API for all providers
2. **Easy Switching**: Change providers via environment variables
3. **Backward Compatible**: Existing code continues to work
4. **Local Support**: Run models locally with Ollama/llamafile
5. **Cost Optimization**: Switch providers based on cost/performance needs
6. **Fallback Support**: Automatic fallback to Paper-QA or direct APIs if needed

## Architecture

```
BioAnalyzer Code
    ↓
UnifiedQA
    ↓
LLMProviderManager (LiteLLM) ← Primary path
    ↓
[OpenAI | Anthropic | Gemini | Ollama | llamafile]
    OR
PaperQAAgent (Paper-QA) ← Fallback for complex analysis
    OR
GeminiQA (Direct API) ← Fallback for backward compatibility
```

## See Also

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Paper-QA Integration Guide](./PAPERQA_INTEGRATION.md)
- [Configuration Guide](../app/utils/config.py)

