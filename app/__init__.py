"""
BugSigDB Analyzer Application Package
====================================

This package contains the main application logic for the BugSigDB Analyzer.
"""

__version__ = "1.0.0"
__author__ = "BugSigDB Team"
__description__ = "A comprehensive tool for analyzing and curating microbiome signature data"

# Import main components for easy access
from .api.app import app
from .utils.config import *

__all__ = ["app"] + [name for name in dir() if not name.startswith('_')] 