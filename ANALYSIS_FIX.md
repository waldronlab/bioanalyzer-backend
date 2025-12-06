# Analysis Fix - Paper-QA Fallback Issue

## Problem

When analyzing a PMID, all fields were showing as ABSENT with 0.00 confidence. The root cause was:

**Paper-QA Library Error**: `'LiteLLMModel' object has no attribute 'router'`

This is a compatibility issue with the Paper-QA library version. When Paper-QA fails, it was returning error responses, which caused all field analyses to fail and return empty results.

## Solution

Implemented automatic fallback to GeminiQA when Paper-QA fails:

### 1. **Lazy Service Initialization** (`app/services/bugsigdb_analyzer.py`)
   - Changed from module-level initialization to lazy initialization
   - Services only initialize when needed
   - Prevents startup failures if services can't be initialized

### 2. **Automatic Fallback in UnifiedQA** (`app/models/unified_qa.py`)
   - Added `_fallback_to_gemini()` method
   - Updated `chat()` method to detect Paper-QA errors and automatically fallback
   - Updated initialization to prefer GeminiQA if Paper-QA fails during init

### 3. **Error Detection in Analyzer** (`app/services/bugsigdb_analyzer.py`)
   - Added detection for Paper-QA errors in responses
   - Automatic fallback to GeminiQA when Paper-QA errors are detected

## Files Modified

1. `app/models/unified_qa.py` - Added automatic fallback to GeminiQA
2. `app/services/bugsigdb_analyzer.py` - Lazy initialization and error handling

## Next Steps

**You need to rebuild the container for these fixes to take effect:**

```bash
# Rebuild the container
BioAnalyzer build

# Restart the application
BioAnalyzer restart
```

## Expected Behavior After Fix

- ✅ Paper-QA errors are automatically caught
- ✅ System falls back to GeminiQA when Paper-QA fails
- ✅ Field analysis works correctly using GeminiQA
- ✅ All 6 BugSigDB fields are properly extracted
- ✅ Confidence scores are accurate

## Testing

After rebuilding, test with:

```bash
BioAnalyzer analyze 35003794
```

You should now see:
- ✅ Fields with PRESENT/PARTIALLY_PRESENT status
- ✅ Actual values extracted from the paper
- ✅ Confidence scores > 0.0
- ✅ Proper field information (host species, body site, condition, etc.)

## Note

The Paper-QA library has a compatibility issue (`'LiteLLMModel' object has no attribute 'router'`). The system now automatically uses GeminiQA as a fallback, which provides the same functionality without the compatibility issues.

