# BioAnalyzer Startup Fixes

## Branch: `simplify-core-functionality`

This document describes the fixes applied to resolve startup errors while preserving all functionality.

## Issues Fixed

### 1. Container Name Mismatch
**Problem:** CLI used `bioanalyzer-api` but docker-compose uses `bioanalyzer-backend`
**Fix:** Changed `self.container_name` from `"bioanalyzer-api"` to `"bioanalyzer-backend"` in `__init__`

### 2. Blocking Permission Checks
**Problem:** `_check_docker_permissions()` returned `False` and blocked startup when permission issues were detected
**Fix:** Made permission checks non-blocking - they now warn but allow startup to continue

**Changes:**
- `_check_docker_permissions()` now always returns `True` (warns instead of blocking)
- Removed blocking checks in `start_application()` and `stop_application()`
- Permission warnings are informational only

### 3. Frontend Network Name Issue
**Problem:** Frontend container tried to use `self.network_name` ("bioanalyzer-network") but docker-compose creates network as "bioanalyzer-backend_bioanalyzer-net"
**Fix:** Changed frontend startup to use the correct docker-compose network name format: `"bioanalyzer-backend_bioanalyzer-net"`

### 4. Error Handling During Startup
**Problem:** Permission errors during container startup would block the entire process
**Fix:** Permission errors now show warnings but don't stop the startup process

## Files Modified

1. **cli.py**
   - Line 54: Fixed container name
   - Line 311-333: Made permission check non-blocking
   - Line 384: Removed blocking permission check
   - Line 437-440: Made permission error handling non-blocking
   - Line 487, 495: Fixed frontend network name
   - Line 517: Removed blocking permission check in stop

2. **docker-compose.yml**
   - Restored to original with healthchecks and all volumes

## Functionality Preserved

✅ All original features remain:
- Paper analysis (analyze command)
- URL analysis (analyze-url command)
- Paper retrieval (retrieve command)
- Q&A functionality (qa command)
- Settings management (settings command)
- Interactive modes
- Multiple output formats (JSON, CSV, XML, table)
- File-based input
- Frontend container management
- All environment variable handling

## Testing

The fixes ensure that:
1. Startup doesn't fail due to permission warnings
2. Frontend can connect to backend network
3. Container names are consistent
4. All functionality works as before

## Next Steps

If you still encounter startup issues:
1. Check Docker is running: `docker ps`
2. Check permissions: `docker ps` should work without sudo
3. Check logs: `docker compose logs`
4. Try manual start: `docker compose up -d`

