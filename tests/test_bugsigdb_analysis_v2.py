import pytest
from unittest.mock import patch, AsyncMock

try:
    from fastapi.testclient import TestClient
    from app.api.app import app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None


@pytest.fixture
def client():
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available")
    return TestClient(app)


def _mock_result(pmid="12345678"):
    return {
        "pmid": pmid,
        "title": "Test Paper",
        "authors": ["A. Author"],
        "journal": "Test Journal",
        "publication_date": "2024-01-01",
        "fields": {
            "host_species": {
                "status": "PRESENT",
                "value": "Human",
                "confidence": 0.95,
                "reason_if_missing": None,
                "suggestions": None,
            }
        },
        "curation_summary": "Looks curatable.",
        "analysis_timestamp": "2024-01-01T00:00:00",
        "processing_time": 1.23,
        "model_used": "gemini-2.0-flash",
        "rag_enabled": True,
        "rag_stats": None,
        "rag_config_used": None,
    }


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalyzePaperGetV2:
    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_default_rag_enabled(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.get("/api/v2/analyze/12345678")
        assert response.status_code == 200
        assert response.json()["pmid"] == "12345678"
        # use_rag defaults True -> a RAGConfig should have been built and passed
        _, kwargs = mock_analyze.call_args
        assert kwargs["use_rag"] is True
        assert kwargs["rag_config"] is not None
        assert kwargs["rag_config"].enabled is True

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_use_rag_false_passes_no_config(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        assert kwargs["use_rag"] is False
        assert kwargs["rag_config"] is None

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_query_params_override_defaults(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.get(
            "/api/v2/analyze/12345678"
            "?top_k_chunks=3&evidence_k=7&max_sources=4"
            "&rerank_method=llm&summary_length=short&summary_quality=fast"
        )
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        cfg = kwargs["rag_config"]
        assert cfg.top_k_chunks == 3
        assert cfg.evidence_k == 7
        assert cfg.max_sources == 4
        assert cfg.rerank_method == "llm"
        assert cfg.summary_length == "short"
        assert cfg.summary_quality == "fast"

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_not_found_returns_404(self, mock_analyze, client):
        mock_analyze.return_value = None
        response = client.get("/api/v2/analyze/12345678")
        assert response.status_code == 404

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_exception_returns_masked_500(self, mock_analyze, client):
        mock_analyze.side_effect = Exception("secret api key leaked here")
        response = client.get("/api/v2/analyze/12345678")
        assert response.status_code == 500
        assert "secret api key" not in response.text


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalyzePaperPostV2:
    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_post_with_explicit_rag_config(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.post(
            "/api/v2/analyze",
            json={
                "pmid": "12345678",
                "use_rag": True,
                "rag_config": {"enabled": True, "rerank_method": "keyword"},
            },
        )
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        assert kwargs["rag_config"].rerank_method == "keyword"

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_post_use_rag_true_no_config_builds_default(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.post(
            "/api/v2/analyze", json={"pmid": "12345678", "use_rag": True}
        )
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        assert kwargs["rag_config"] is not None

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_post_not_found(self, mock_analyze, client):
        mock_analyze.return_value = None
        response = client.post(
            "/api/v2/analyze", json={"pmid": "12345678", "use_rag": False}
        )
        assert response.status_code == 404

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_post_exception_masked(self, mock_analyze, client):
        mock_analyze.side_effect = Exception("sk-leaked-secret-1234567890")
        response = client.post(
            "/api/v2/analyze", json={"pmid": "12345678", "use_rag": False}
        )
        assert response.status_code == 500
        assert "sk-leaked-secret" not in response.text


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestBatchAnalysisV2:
    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_batch_returns_all_successful_results(self, mock_analyze, client):
        mock_analyze.side_effect = [
            _mock_result("111"),
            _mock_result("222"),
        ]
        response = client.post(
            "/api/v2/analyze/batch",
            json={"pmids": ["111", "222"], "use_rag": False, "max_concurrent": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert {r["pmid"] for r in data} == {"111", "222"}

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_batch_filters_out_failed_pmids(self, mock_analyze, client):
        async def side_effect(pmid, rag_config=None, use_rag=True):
            if pmid == "bad":
                raise RuntimeError("boom")
            return _mock_result(pmid)

        mock_analyze.side_effect = side_effect
        response = client.post(
            "/api/v2/analyze/batch",
            json={"pmids": ["good", "bad"], "use_rag": False, "max_concurrent": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pmid"] == "good"

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_batch_default_rag_config_used_when_enabled(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.post(
            "/api/v2/analyze/batch",
            json={"pmids": ["111"], "use_rag": True, "max_concurrent": 1},
        )
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        assert kwargs["rag_config"] is not None


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestRagConfigEndpoint:
    def test_get_rag_config_returns_defaults_and_options(self, client):
        response = client.get("/api/v2/rag/config")
        assert response.status_code == 200
        data = response.json()
        assert "default_config" in data
        assert set(data["available_rerank_methods"]) >= {"keyword", "llm", "hybrid"}
        assert set(data["available_summary_lengths"]) >= {"short", "medium", "long"}
        assert isinstance(data["available_providers"], list)
        assert len(data["available_providers"]) > 0

    @patch("app.api.routers.bugsigdb_analysis_v2.LLMProviderManager", create=True)
    def test_get_rag_config_falls_back_when_provider_lookup_fails(
        self, mock_manager, client
    ):
        # Importing LLMProviderManager happens lazily inside the handler via
        # `from app.models.llm_provider import LLMProviderManager` - patch the
        # module actually imported from instead, to exercise the except branch.
        with patch(
            "app.models.llm_provider.LLMProviderManager.get_available_providers",
            side_effect=Exception("boom"),
        ):
            response = client.get("/api/v2/rag/config")
        assert response.status_code == 500


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestFieldsEndpointsV2:
    def test_get_essential_fields(self, client):
        response = client.get("/api/v2/fields")
        assert response.status_code == 200
        data = response.json()
        assert "essential_fields" in data
        assert "host_species" in data["essential_fields"]

    def test_get_field_details_known_field(self, client):
        response = client.get("/api/v2/fields/host_species")
        assert response.status_code == 200

    def test_get_field_details_unknown_field(self, client):
        response = client.get("/api/v2/fields/not_a_real_field")
        assert response.status_code in (404, 400)


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalyzePaperV1Legacy:
    """Coverage for the /api/v1 wrapper endpoints. These call
    analyze_paper_simple directly (NOT analyze_paper_with_rag(use_rag=False))
    — see the module docstring in bugsigdb_analysis_v2.py for why that
    distinction matters. Patch target is analyze_paper_simple, imported at
    module scope in app.api.routers.bugsigdb_analysis_v2.
    """

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_simple")
    def test_get_success(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 200
        assert response.json()["pmid"] == "12345678"

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_simple")
    def test_get_passes_force_refresh(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.get("/api/v1/analyze/12345678?refresh=true")
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        assert kwargs["force_refresh"] is True

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_simple")
    def test_get_default_no_refresh(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 200
        _, kwargs = mock_analyze.call_args
        assert kwargs["force_refresh"] is False

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_simple")
    def test_post_success(self, mock_analyze, client):
        mock_analyze.return_value = _mock_result()
        response = client.post("/api/v1/analyze/12345678")
        assert response.status_code == 200
        assert response.json()["pmid"] == "12345678"

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_simple")
    def test_not_found_returns_404(self, mock_analyze, client):
        mock_analyze.return_value = None
        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 404
        # carried over from the old TestBugSigDBAnalysisEndpoints
        assert "failed" in response.json()["detail"].lower()

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_simple")
    def test_exception_returns_masked_500(self, mock_analyze, client):
        mock_analyze.side_effect = Exception("secret api key leaked here")
        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 500
        assert "secret api key" not in response.text
        # carried over from the old TestBugSigDBAnalysisEndpoints
        assert "error" in response.json()["detail"].lower()

    def test_get_essential_fields_v1_shape(self, client):
        response = client.get("/api/v1/fields")
        assert response.status_code == 200
        data = response.json()
        assert "essential_fields" in data
        # carried over from the old TestBugSigDBAnalysisEndpoints — status
        # values and full per-field structure, not just presence of the key
        assert "status_values" in data
        essential_fields = data["essential_fields"]
        for name in (
            "host_species",
            "body_site",
            "condition",
            "sequencing_type",
            "sample_size",
        ):
            assert name in essential_fields
        for field_name, field_info in essential_fields.items():
            assert "name" in field_info
            assert "description" in field_info
            assert "required" in field_info
            assert field_info["required"] is True

    def test_get_field_details_v1_known_field(self, client):
        response = client.get("/api/v1/fields/host_species")
        assert response.status_code == 200

    def test_get_field_details_v1_unknown_field(self, client):
        response = client.get("/api/v1/fields/not_a_real_field")
        assert response.status_code in (404, 400)
