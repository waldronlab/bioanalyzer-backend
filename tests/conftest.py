"""
Pytest configuration and fixtures for BioAnalyzer tests.
"""
import sys
import os
from pathlib import Path

# CRITICAL: Add /app and /app/app to path IMMEDIATELY - before any other imports
# This must happen at module level, before pytest imports anything
# The app package is at /app/app, so we need both paths
if '/app/app' not in sys.path:
    sys.path.insert(0, '/app/app')
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# Add the project root to Python path
project_root = Path(__file__).parent.parent
project_root_str = str(project_root)

if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

# Set PYTHONPATH environment variable
os.environ['PYTHONPATH'] = '/app:/app/app:' + project_root_str

# Verify we can import app
try:
    import app
except ImportError:
    # If import fails, ensure /app is definitely in path
    if '/app' not in sys.path:
        sys.path.insert(0, '/app')

def pytest_configure(config):
    """Configure pytest - runs before test collection."""
    # Ensure paths are set - this runs before imports
    if '/app/app' not in sys.path:
        sys.path.insert(0, '/app/app')
    if '/app' not in sys.path:
        sys.path.insert(0, '/app')
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    
    # Verify app can be imported
    try:
        import app
    except ImportError as e:
        print(f"WARNING: Cannot import app module: {e}")
        print(f"Python path: {sys.path}")

def pytest_collection_modifyitems(config, items):
    """Hook that runs after collection but before test execution."""
    # Ensure path is set (redundant but safe)
    if '/app' not in sys.path:
        sys.path.insert(0, '/app')

