"""
Services Package for BugSigDB Analyzer
======================================

Contains business logic services for data retrieval, classification, and processing.
"""

# Lazy imports — importing this package does NOT immediately pull in defusedxml,
# FastAPI, or any other heavy dependency. Submodules are loaded on first attribute
# access, so all existing call-sites (from app.services import X) keep working.


def __getattr__(name: str):
    if name == "PubMedRetriever":
        from .data_retrieval import PubMedRetriever

        return PubMedRetriever
    if name == "analyze_paper_simple":
        from .bugsigdb_analyzer import analyze_paper_simple

        return analyze_paper_simple
    if name == "CacheManager":
        from .cache_manager import CacheManager

        return CacheManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["PubMedRetriever", "analyze_paper_simple", "CacheManager"]
