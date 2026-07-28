import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional, TypeVar

from fastapi import FastAPI

from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever
from app.utils.config import GEMINI_API_KEY, NCBI_API_KEY
from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _safe_init(factory: Callable[[], T], service_name: str) -> Optional[T]:
    """Initialize a service at startup; log (don't crash the app) on failure."""
    try:
        return factory()
    except Exception as exc:
        logger.warning(
            "Failed to initialize %s: %s", service_name, mask_exception_message(exc)
        )
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize singletons on startup, expose via app.state, clear on shutdown."""
    app.state.unified_qa = _safe_init(
        lambda: UnifiedQA(use_gemini=True, gemini_api_key=GEMINI_API_KEY),
        "UnifiedQA",
    )
    app.state.pubmed_retriever = _safe_init(
        lambda: PubMedRetriever(api_key=NCBI_API_KEY),
        "PubMedRetriever",
    )

    yield

    app.state.unified_qa = None
    app.state.pubmed_retriever = None
