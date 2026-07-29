from typing import Optional

from fastapi import HTTPException, Request

from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever


def get_unified_qa(request: Request) -> UnifiedQA:
    """
    Return the UnifiedQA singleton created at startup.

    Raises 503 if it never initialized (e.g. missing/invalid
    GEMINI_API_KEY) — same contract /qa relied on before.
    """
    qa = getattr(request.app.state, "unified_qa", None)
    if qa is None:
        raise HTTPException(
            status_code=503,
            detail="QA service not available. Check GEMINI_API_KEY configuration.",
        )
    return qa


def get_unified_qa_optional(request: Request) -> Optional[UnifiedQA]:
    """Same service, but returns None instead of raising — used by health checks."""
    return getattr(request.app.state, "unified_qa", None)


def get_pubmed_retriever(request: Request) -> Optional[PubMedRetriever]:
    """Return the PubMedRetriever singleton created at startup, or None."""
    return getattr(request.app.state, "pubmed_retriever", None)
