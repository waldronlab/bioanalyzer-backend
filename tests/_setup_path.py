"""
Setup module to configure Python path before imports.
This must be imported before any app.* imports in test files.
"""

import sys
from pathlib import Path

# Add the app folder to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

# Add /app/app to path FIRST (Docker has nested structure: /app/app/services/)
if "/app/app" not in sys.path:
    sys.path.insert(0, "/app/app")

# Add /app to path (for Docker containers)
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

# Add project root to path
project_root = Path(__file__).parent.parent
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
