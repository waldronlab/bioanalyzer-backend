"""
Tests for the third (URL-based) analysis pipeline's router and background task.

app/api/routers/study_analysis.py has its own exception handling (it does
not go through app/api/app.py's global handler) and stores job state in an
in-memory job_store dict - both are exercised here directly, since neither
had any test coverage before.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from fastapi.testclient import TestClient
    from app.api.app import app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None

from app.api.routers import study_analysis
from app.api.routers.study_analysis import JobStatus, process_url_analysis
from app.models.extraction_schemas import StudyAnalysisResult


# `client` fixture (raise_server_exceptions=False) is provided by
# tests/conftest.py, shared with test_api_endpoints.py, test_integration.py
# and test_bugsigdb_analysis_v2.py. Every endpoint exercised here raises
# HTTPException explicitly (see app/api/routers/study_analysis.py), so
# raise_server_exceptions=False doesn't change any of these tests' outcomes.


@pytest.fixture(autouse=True)
def clear_job_store():
    """job_store is a module-level dict shared across requests - reset per test."""
    study_analysis.job_store.clear()
    yield
    study_analysis.job_store.clear()


# ---------------------------------------------------------------------------
# Router: /analysis-status/{job_id}, /analysis-result/{job_id}
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalysisStatusEndpoint:
    def test_status_unknown_job_returns_404(self, client):
        response = client.get("/api/v1/analysis-status/does-not-exist")
        assert response.status_code == 404

    def test_status_known_job_returns_current_state(self, client):
        study_analysis.job_store["job-1"] = JobStatus(
            job_id="job-1", status="processing", progress="Step 3/7: Processing images"
        )
        response = client.get("/api/v1/analysis-status/job-1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["progress"] == "Step 3/7: Processing images"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalysisResultEndpoint:
    def test_result_unknown_job_returns_404(self, client):
        response = client.get("/api/v1/analysis-result/does-not-exist")
        assert response.status_code == 404

    def test_result_job_not_completed_returns_400(self, client):
        study_analysis.job_store["job-2"] = JobStatus(
            job_id="job-2", status="processing"
        )
        response = client.get("/api/v1/analysis-result/job-2")
        assert response.status_code == 400

    def test_result_completed_job_without_result_returns_500(self, client):
        study_analysis.job_store["job-3"] = JobStatus(
            job_id="job-3", status="completed"
        )
        response = client.get("/api/v1/analysis-result/job-3")
        assert response.status_code == 500

    def test_result_completed_job_returns_result(self, client):
        result = StudyAnalysisResult(
            pmid="123",
            study_id="job-4",
            source_url="https://example.org/paper",
        )
        study_analysis.job_store["job-4"] = JobStatus(
            job_id="job-4", status="completed", result=result
        )
        response = client.get("/api/v1/analysis-result/job-4")
        assert response.status_code == 200
        assert response.json()["pmid"] == "123"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalyzeURLEndpoint:
    def test_analyze_url_enqueues_job_and_returns_pending(self, client):
        with patch.object(study_analysis, "process_url_analysis", AsyncMock()):
            response = client.post(
                "/api/v1/analyze-url", json={"url": "https://example.org/paper"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["job_id"] in study_analysis.job_store


# ---------------------------------------------------------------------------
# process_url_analysis (the 7-step background task)
# ---------------------------------------------------------------------------


def _make_mock_scraper():
    scraper = MagicMock()
    scraper.scrape_url_to_markdown = AsyncMock(
        return_value={"markdown": "# Title\n\nBody text.", "images": [], "files": []}
    )
    scraper.cleanup_downloads = MagicMock()
    return scraper


def _make_mock_image_processor():
    processor = MagicMock()
    processor.process_image_url = AsyncMock(return_value=None)
    processor.cleanup_cache = MagicMock()
    return processor


def _make_mock_converter():
    converter = MagicMock()
    converter.create_enhanced_markdown = AsyncMock(return_value="# Enhanced markdown")
    return converter


def _make_mock_chunker():
    chunker = MagicMock()
    chunker.chunk_markdown = AsyncMock(return_value=["chunk1", "chunk2"])
    return chunker


def _make_mock_vector_store():
    store = MagicMock()
    store.add_texts = AsyncMock(return_value=None)
    return store


def _make_mock_orchestrator(result):
    orchestrator = MagicMock()
    orchestrator.analyze_study = AsyncMock(return_value=result)
    return orchestrator


@pytest.fixture
def study_result():
    return StudyAnalysisResult(
        pmid="job-success",
        study_id="job-success",
        source_url="https://example.org/paper",
        experiments=[],
        total_signatures=0,
    )


@pytest.mark.asyncio
async def test_process_url_analysis_happy_path(monkeypatch, study_result):
    job_id = "job-success"
    study_analysis.job_store[job_id] = JobStatus(job_id=job_id, status="pending")

    mock_scraper = _make_mock_scraper()
    monkeypatch.setattr(
        study_analysis, "WebScraperService", MagicMock(return_value=mock_scraper)
    )
    mock_image_processor = _make_mock_image_processor()
    monkeypatch.setattr(
        study_analysis,
        "ImageProcessorService",
        MagicMock(return_value=mock_image_processor),
    )
    monkeypatch.setattr(
        study_analysis,
        "ConverterService",
        MagicMock(return_value=_make_mock_converter()),
    )
    monkeypatch.setattr(
        study_analysis, "ChunkingService", MagicMock(return_value=_make_mock_chunker())
    )
    monkeypatch.setattr(
        study_analysis,
        "VectorStoreService",
        MagicMock(return_value=_make_mock_vector_store()),
    )
    monkeypatch.setattr(
        study_analysis,
        "AgentOrchestrator",
        MagicMock(return_value=_make_mock_orchestrator(study_result)),
    )
    # No Gemini key configured -> skip visual-LLM init path entirely
    monkeypatch.setattr(study_analysis, "GEMINI_API_KEY", "")

    await process_url_analysis(
        job_id=job_id,
        url="https://example.org/paper",
        embedding_model="gemini/text-embedding-004",
        llm_model="gemini/gemini-2.0-flash",
    )

    job = study_analysis.job_store[job_id]
    assert job.status == "completed"
    assert job.result is study_result
    assert job.error is None
    mock_scraper.cleanup_downloads.assert_called_once()
    mock_image_processor.cleanup_cache.assert_called_once()


@pytest.mark.asyncio
async def test_process_url_analysis_failure_masks_credentials_in_job_error(
    monkeypatch,
):
    """
    Regression test: job_store[job_id].error must use the masked exception
    message, not the raw one - a failure inside the pipeline could otherwise
    leak an API key embedded in an underlying exception's text straight to
    GET /analysis-result/{job_id}'s response (this previously happened with
    the unmasked str(e); fixed in study_analysis.py's except block).
    """
    job_id = "job-failure"
    study_analysis.job_store[job_id] = JobStatus(job_id=job_id, status="pending")

    secret = "sk-supersecretapikey1234567890"
    mock_scraper = _make_mock_scraper()
    mock_scraper.scrape_url_to_markdown = AsyncMock(
        side_effect=RuntimeError(f"connection failed using key={secret}")
    )
    monkeypatch.setattr(
        study_analysis, "WebScraperService", MagicMock(return_value=mock_scraper)
    )

    await process_url_analysis(
        job_id=job_id,
        url="https://example.org/paper",
        embedding_model="gemini/text-embedding-004",
        llm_model="gemini/gemini-2.0-flash",
    )

    job = study_analysis.job_store[job_id]
    assert job.status == "failed"
    assert job.error is not None
    assert secret not in job.error


@pytest.mark.asyncio
async def test_process_url_analysis_updates_progress_through_steps(
    monkeypatch, study_result
):
    job_id = "job-progress"
    study_analysis.job_store[job_id] = JobStatus(job_id=job_id, status="pending")

    progress_snapshots = []
    mock_scraper = _make_mock_scraper()

    async def _tracking_scrape(url):
        progress_snapshots.append(study_analysis.job_store[job_id].progress)
        return {"markdown": "# Title\n\nBody.", "images": [], "files": []}

    mock_scraper.scrape_url_to_markdown = _tracking_scrape
    monkeypatch.setattr(
        study_analysis, "WebScraperService", MagicMock(return_value=mock_scraper)
    )
    monkeypatch.setattr(
        study_analysis,
        "ImageProcessorService",
        MagicMock(return_value=_make_mock_image_processor()),
    )
    monkeypatch.setattr(
        study_analysis,
        "ConverterService",
        MagicMock(return_value=_make_mock_converter()),
    )
    monkeypatch.setattr(
        study_analysis, "ChunkingService", MagicMock(return_value=_make_mock_chunker())
    )
    monkeypatch.setattr(
        study_analysis,
        "VectorStoreService",
        MagicMock(return_value=_make_mock_vector_store()),
    )
    monkeypatch.setattr(
        study_analysis,
        "AgentOrchestrator",
        MagicMock(return_value=_make_mock_orchestrator(study_result)),
    )
    monkeypatch.setattr(study_analysis, "GEMINI_API_KEY", "")

    await process_url_analysis(
        job_id=job_id,
        url="https://example.org/paper",
        embedding_model="gemini/text-embedding-004",
        llm_model="gemini/gemini-2.0-flash",
    )

    assert progress_snapshots == ["Step 1/7: Scraping URL"]
    assert study_analysis.job_store[job_id].status == "completed"
