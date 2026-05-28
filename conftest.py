import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent.resolve())
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import os
existing = os.environ.get("PYTHONPATH", "")
if _PROJECT_ROOT not in existing.split(":"):
    os.environ["PYTHONPATH"] = f"{_PROJECT_ROOT}:{existing}" if existing else _PROJECT_ROOT

# Debug: print what pytest sees
print(">>> conftest.py loaded, sys.path[0:3]:", sys.path[:3])
try:
    import app
    print(">>> app.__file__:", app.__file__)
    import app.services
    print(">>> app.services.__file__:", app.services.__file__)
except Exception as e:
    print(">>> IMPORT FAILED:", e)
