"""
BugSigDB Analyzer Application Package
====================================

This package contains the main application logic for the BugSigDB Analyzer.
"""

__version__ = "1.0.0"
__author__ = "WaldronLab"
__description__ = "A comprehensive tool for identifying curatable microbiome signatures"

from .utils.config import *

# api.app is NOT imported here. Eagerly importing it triggers services/__init__.py
# → data_retrieval → defusedxml/FastAPI which may not be present in lightweight
# test environments, and freezes sys.modules['app'] before subpackages like
# app.normalization are registered.
# Use get_app() below, or import directly: from app.api.app import app


def get_app():
    """Lazy loader for the FastAPI application instance."""
    from .api.app import app as _app  # noqa: PLC0415
    return _app


_has_fastapi: bool = False
try:
    import fastapi as _fastapi  # noqa: F401
    _has_fastapi = True
except ImportError:
    pass

__all__ = ["get_app", "__version__"]
