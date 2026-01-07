"""
Pytest configuration and fixtures for BioAnalyzer tests.
This module automatically configures Python path for both Docker and local environments.
"""

import sys
import os
from pathlib import Path

# Get the project root (parent of tests directory)
project_root = Path(__file__).parent.parent
project_root_str = str(project_root.resolve())

# Detect if we're running in Docker (check if /app exists and is a directory)
is_docker = Path("/app").exists() and Path("/app").is_dir()

# Configure Python path based on environment
paths_to_add = []

if is_docker:
    # Docker environment: code is at /app/
    # Add /app first (this is where app/ package is located)
    docker_paths = ["/app"]
    for path in docker_paths:
        if path not in sys.path:
            paths_to_add.append(path)
else:
    # Local environment: code is at project root
    # Add project root (this is where app/ package is located)
    if project_root_str not in sys.path:
        paths_to_add.append(project_root_str)

# Add paths to sys.path (insert at beginning for priority)
for path in paths_to_add:
    sys.path.insert(0, path)

# Also ensure project root is always in path (works for both environments)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

# Update PYTHONPATH environment variable
existing_pythonpath = os.environ.get("PYTHONPATH", "")
pythonpath_parts = [p for p in existing_pythonpath.split(":") if p]
for path in paths_to_add + [project_root_str]:
    if path not in pythonpath_parts:
        pythonpath_parts.insert(0, path)
os.environ["PYTHONPATH"] = ":".join(pythonpath_parts)

# Verify we can import app
try:
    import app
except ImportError:
    # If import fails, try adding common paths
    fallback_paths = [
        project_root_str,
        str(project_root / "app"),
        "/app",
        "/app/app",
    ]
    for path in fallback_paths:
        if Path(path).exists() and path not in sys.path:
            sys.path.insert(0, path)
            try:
                import app

                break
            except ImportError:
                continue


def pytest_configure(config):
    """Configure pytest - runs before test collection."""
    # Re-ensure paths are set (pytest may reset them)
    if is_docker:
        docker_paths = ["/app"]
        for path in docker_paths:
            if path not in sys.path:
                sys.path.insert(0, path)

    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    # Verify app can be imported
    try:
        import app
    except ImportError as e:
        print(f"WARNING: Cannot import app module: {e}")
        print(f"Python path: {sys.path}")
        print(f"Project root: {project_root_str}")
        print(f"Is Docker: {is_docker}")


def pytest_collection_modifyitems(config, items):
    """Hook that runs after collection but before test execution."""
    # Ensure path is set (redundant but safe)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    if is_docker and "/app" not in sys.path:
        sys.path.insert(0, "/app")
