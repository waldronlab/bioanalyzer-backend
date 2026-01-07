"""
BugSigDB Analyzer Application Package
====================================

This package contains the main application logic for the BugSigDB Analyzer.
"""

__version__ = "1.0.0"
__author__ = "WaldronLab"
__description__ = "A comprehensive tool for identifying curatable microbiome signatures"

# Import main components for easy access
# Lazy import to avoid requiring FastAPI when only using models
try:
    from .api.app import app

    _has_fastapi = True
except ImportError:
    app = None
    _has_fastapi = False

from .utils.config import *

__all__ = ["app"] + [name for name in dir() if not name.startswith("_")]
