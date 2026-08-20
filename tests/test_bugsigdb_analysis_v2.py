import pytest
from unittest.mock import patch, AsyncMock, MagicMock

try:
    from fastapi.testclient import TestClient
    from app.api.app import app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None


# `client` fixture (raise_server_exceptions=False) is provided by
# tests/conftest.py, shared with test_api_endpoints.py, test_integration.py
# and test_study_analysis.py. Every endpoint exercised here catches Exception
# and re-raises as HTTPException (see app/api/routers/bugsigdb_analysis_v2.py),
# so raise_server_exceptions=False doesn't change any of these tests' outcomes.


def _mock_result(pmid="12345678", in_bugsigdb=True):
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
        "in_bugsigdb": in_bugsigdb,
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
    def test_in_bugsigdb_survives_response_schema(self, mock_analyze, client):
        """Regression test: PaperAnalysisResult (the base of the v2 response
        model) used to omit in_bugsigdb entirely, so FastAPI's response-model
        filtering silently dropped it from every /api/v2 JSON response even
        though analyze_paper_with_rag computed it correctly - v1's Dict[str,
        Any] return type isn't schema-filtered, so v1 never showed this."""
        mock_analyze.return_value = _mock_result(in_bugsigdb=True)
        response = client.get("/api/v2/analyze/12345678")
        assert response.status_code == 200
        assert response.json()["in_bugsigdb"] is True

        mock_analyze.return_value = _mock_result(in_bugsigdb=False)
        response = client.get("/api/v2/analyze/12345678")
        assert response.status_code == 200
        assert response.json()["in_bugsigdb"] is False

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
        results = data["results"]
        assert len(results) == 2
        assert {r["pmid"] for r in results} == {"111", "222"}
        assert data["failed"] == []

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_batch_filters_out_failed_pmids(self, mock_analyze, client):
        # PMIDs must be numeric strings - validate_pmid() rejects anything
        # else before this mock is ever reached, which would otherwise drop
        # BOTH pmids (not just the intentionally-failing one) and make this
        # test's own assertions impossible to satisfy.
        async def side_effect(pmid, rag_config=None, use_rag=True):
            if pmid == "222":
                raise RuntimeError("boom")
            return _mock_result(pmid)

        mock_analyze.side_effect = side_effect
        response = client.post(
            "/api/v2/analyze/batch",
            json={"pmids": ["111", "222"], "use_rag": False, "max_concurrent": 2},
        )
        assert response.status_code == 200
        data = response.json()
        # Successful PMID shows up in `results`, nothing for "222" there.
        assert len(data["results"]) == 1
        assert data["results"][0]["pmid"] == "111"
        # Failed PMID is explicitly reported in `failed`, not silently
        # dropped - callers correlating results to input PMIDs need this
        # signal instead of inferring failure from a shorter list.
        assert len(data["failed"]) == 1
        assert data["failed"][0]["pmid"] == "222"
        # mask_exception_message() only rewrites credential-shaped
        # substrings (API keys, bearer tokens, key=value pairs) - "boom"
        # doesn't match any of those patterns, so it passes through as-is.
        assert "boom" in data["failed"][0]["error"]

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_batch_partial_failure_reconciles_against_request(
        self, mock_analyze, client
    ):
        """3 PMIDs, 1 fails: results/failed counts and the failed PMID must
        reconcile against the request, not just be a filtered-down list."""

        async def side_effect(pmid, rag_config=None, use_rag=True):
            if pmid == "222":
                raise RuntimeError("boom")
            return _mock_result(pmid)

        mock_analyze.side_effect = side_effect
        response = client.post(
            "/api/v2/analyze/batch",
            json={
                "pmids": ["111", "222", "333"],
                "use_rag": False,
                "max_concurrent": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert {r["pmid"] for r in data["results"]} == {"111", "333"}
        assert len(data["failed"]) == 1
        assert data["failed"][0]["pmid"] == "222"

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

    @patch("app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag")
    def test_batch_in_bugsigdb_independent_per_paper(self, mock_analyze, client):
        """Each paper in a batch must carry its own in_bugsigdb value through
        to the final JSON response, independent of the others."""
        membership = {"111": True, "222": False, "333": True, "444": False}

        async def side_effect(pmid, rag_config=None, use_rag=True):
            return _mock_result(pmid, in_bugsigdb=membership[pmid])

        mock_analyze.side_effect = side_effect
        response = client.post(
            "/api/v2/analyze/batch",
            json={
                "pmids": list(membership.keys()),
                "use_rag": False,
                "max_concurrent": 4,
            },
        )
        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) == 4
        actual = {r["pmid"]: r["in_bugsigdb"] for r in results}
        assert actual == membership


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


# --------------------------------------------------------------------------- #
# Genuine (non-hand-mocked) analysis through the real response schema.
#
# Every test above patches analyze_paper_with_rag/analyze_paper_simple
# directly with a hand-built dict that happens to already match
# PaperAnalysisResult's declared fields - which is exactly how the
# FieldAnalysis.suggestions defect (no default, but _build_field_result()
# never emits a "suggestions" key) went unnoticed: it only surfaces when the
# REAL field-extraction dict shape reaches real Pydantic response
# validation. These tests mock only the true external dependencies
# (PubMed retriever, cache manager, LLM) and let the real
# analyze_paper_with_rag/analyze_paper_simple, real _build_field_result(),
# and real is_in_bugsigdb() run, so they exercise the actual
# field-extraction -> PaperAnalysisResult -> FastAPI response chain.
# --------------------------------------------------------------------------- #


def _make_real_retriever(
    abstract="A study of 30 human patients with colorectal cancer using 16S rRNA sequencing.",
    publication_date="2023-01-01",
):
    retriever = MagicMock()
    retriever.get_texts_for_analysis_async = AsyncMock(
        return_value={
            "title": "A Real Pipeline Test Paper",
            "abstract": abstract,
            "full_text": "",
            "publication_date": publication_date,
            "journal": "Test Journal",
            "authors": ["A. Author"],
        }
    )
    return retriever


def _make_real_cache_manager():
    cache_manager = MagicMock()
    cache_manager.get_analysis_result.return_value = None
    cache_manager.is_cache_valid.return_value = False
    cache_manager.store_analysis_result.return_value = None
    return cache_manager


def _make_real_unified_qa(json_text='{"host_species_raw": "human"}'):
    qa = MagicMock()
    qa.chat = AsyncMock(return_value={"text": json_text})
    return qa


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestGenuineAnalysisSchemaContract:
    """Regression coverage for the FieldAnalysis.suggestions response-schema
    defect: a genuine analysis result must pass real Pydantic validation and
    return 200, not 500, and in_bugsigdb must remain correct throughout."""

    def _patches(self, json_text='{"host_species_raw": "human"}', is_present=True):
        return (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                return_value=_make_real_retriever(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                return_value=_make_real_unified_qa(json_text),
            ),
            patch(
                "app.services.bugsigdb_analyzer.is_in_bugsigdb",
                return_value=is_present,
            ),
        )

    def test_genuine_single_paper_v2_analysis_returns_200(self, client):
        """Core regression: real field extraction -> real PaperAnalysisResult
        -> FastAPI response must succeed, not 500."""
        p1, p2, p3, p4 = self._patches(is_present=True)
        with p1, p2, p3, p4:
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        body = response.json()
        assert body["in_bugsigdb"] is True
        for field in body["fields"].values():
            # Absent producer -> must default to None, not be missing/error.
            assert field["suggestions"] is None

    def test_genuine_single_paper_v2_analysis_pmid_absent(self, client):
        p1, p2, p3, p4 = self._patches(is_present=False)
        with p1, p2, p3, p4:
            response = client.get("/api/v2/analyze/87654321?use_rag=false")
        assert response.status_code == 200
        assert response.json()["in_bugsigdb"] is False

    def test_genuine_analysis_with_failed_field_extraction_still_200(self, client):
        """Bad/invalid LLM JSON forces the heuristic fallback path - the
        response schema must still validate regardless of extraction
        quality, and in_bugsigdb must stay independent of it."""
        p1, p2, p3, p4 = self._patches(json_text="not valid json {{{", is_present=True)
        with p1, p2, p3, p4:
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        assert response.json()["in_bugsigdb"] is True

    def test_genuine_multi_paper_v2_batch_returns_200(self, client):
        """Multi-paper batch through the real orchestration + real schema:
        each paper keeps its own independent, correct in_bugsigdb."""
        membership = {"11111111": True, "22222222": False}

        with (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                return_value=_make_real_retriever(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                return_value=_make_real_unified_qa(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.is_in_bugsigdb",
                side_effect=lambda pmid: membership[str(pmid)],
            ),
        ):
            response = client.post(
                "/api/v2/analyze/batch",
                json={
                    "pmids": list(membership.keys()),
                    "use_rag": False,
                    "max_concurrent": 2,
                },
            )
        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) == 2
        actual = {r["pmid"]: r["in_bugsigdb"] for r in results}
        assert actual == membership
        assert data["failed"] == []

    def test_genuine_v1_analysis_unaffected(self, client):
        """v1 never validated through PaperAnalysisResult (Dict[str, Any]
        return type), so it was never broken by this defect - confirm it
        still isn't, after the schema fix."""
        p1, p2, p3, p4 = self._patches(is_present=True)
        with p1, p2, p3, p4:
            response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 200
        assert response.json()["in_bugsigdb"] is True

    def test_suggestions_explicit_value_still_validates(self, client):
        """Backward compatibility: if some future producer DOES supply a
        real suggestions string, it must still pass through unchanged -
        the fix only relaxed the requirement, it didn't remove the field."""
        mock_result = {
            "pmid": "12345678",
            "title": "T",
            "authors": [],
            "journal": "J",
            "publication_date": "2024-01-01",
            "fields": {
                "host_species": {
                    "status": "ABSENT",
                    "value": "",
                    "confidence": 0.0,
                    "reason_if_missing": "Information not found in the paper",
                    "suggestions": "Check the methods section for host species.",
                }
            },
            "curation_summary": "x",
            "analysis_timestamp": "2024-01-01T00:00:00",
            "processing_time": 0.1,
            "model_used": "m",
            "rag_enabled": False,
            "rag_stats": None,
            "rag_config_used": None,
            "in_bugsigdb": True,
        }
        with patch(
            "app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag",
            return_value=mock_result,
        ):
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        body = response.json()
        assert (
            body["fields"]["host_species"]["suggestions"]
            == "Check the methods section for host species."
        )


# --------------------------------------------------------------------------- #
# Ontology-grounding response contract: FieldAnalysis used to declare only
# status/value/confidence/reason_if_missing/suggestions, silently dropping
# ontology_id/mapping_confidence/mapping_tier/mapping_candidates/raw - real
# grounding metadata app.services.bugsigdb_analyzer.__init__'s documented
# "Output contract" says every FieldDict has, and that
# scripts/cli_rendering.py reads directly to build the curator-desk CSV's
# ontology columns. v1 was never affected (Dict[str, Any], unfiltered).
# --------------------------------------------------------------------------- #


def _grounded_field(
    value,
    status="PRESENT",
    ontology_id="",
    mapping_confidence=0.0,
    mapping_tier="none",
    mapping_candidates=None,
    raw="",
    reason_if_missing="",
):
    """A field dict shaped exactly like _build_field_result()'s real output
    (see app/services/bugsigdb_analyzer/field_extraction.py) - used where a
    specific mapping_tier/candidates combination needs to be pinned down
    deterministically rather than coaxed out of the real NLP pipeline."""
    return {
        "status": status,
        "value": value,
        "confidence": 0.85 if status == "PRESENT" else 0.0,
        "reason_if_missing": reason_if_missing,
        "ontology_id": ontology_id,
        "mapping_confidence": mapping_confidence,
        "mapping_tier": mapping_tier,
        "mapping_candidates": mapping_candidates or [],
        "raw": raw,
    }


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestOntologyGroundingResponseContract:
    """Regression coverage proving the v2 HTTP response faithfully exposes
    the ontology-grounding metadata BioAnalyzer already produces, without
    fabricating values for fields that weren't actually grounded."""

    def test_genuine_grounded_field_exposes_ontology_metadata(self, client):
        """Real pipeline (real normalize_host_species + real grounding.tier_for,
        not a hand-mocked dict): a static-dict exact match must reach the
        client as auto-tier with its real NCBITaxon id and full confidence."""
        with (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                return_value=_make_real_retriever(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                return_value=_make_real_unified_qa('{"host_species_raw": "human"}'),
            ),
            patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=True),
        ):
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        hs = response.json()["fields"]["host_species"]
        assert hs["ontology_id"] == "NCBITaxon:9606"
        assert hs["mapping_tier"] == "auto"
        assert hs["mapping_confidence"] == 1.0
        assert isinstance(hs["mapping_candidates"], list)

    def test_genuine_ungrounded_field_does_not_fabricate_values(self, client):
        """A field the real pipeline found nothing for must serialize with
        empty/none grounding data, never a fabricated ontology_id or tier."""
        with (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                return_value=_make_real_retriever(
                    abstract="A study of 30 human patients with colorectal cancer."
                ),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                return_value=_make_real_unified_qa('{"host_species_raw": "human"}'),
            ),
            patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False),
        ):
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        # sample_size is never mentioned in the abstract - real extraction
        # must leave it ABSENT with no grounding, not invent one.
        ss = response.json()["fields"]["sample_size"]
        assert ss["status"] == "ABSENT"
        assert ss["ontology_id"] == ""
        assert ss["mapping_tier"] == "none"
        assert ss["mapping_confidence"] == 0.0
        assert ss["mapping_candidates"] == []

    def test_review_tier_and_candidates_reach_api(self, client):
        """A review-tier mapping (live OLS fallback / ambiguous match) must
        keep its tier and expose its alternative candidates verbatim."""
        mock_result = _mock_result()
        mock_result["fields"] = {
            "condition": _grounded_field(
                "Irritable bowel syndrome",
                status="PRESENT",
                ontology_id="MONDO:0005405",
                mapping_confidence=0.6,
                mapping_tier="review",
                mapping_candidates=[
                    {
                        "label": "Irritable bowel syndrome",
                        "ontology_id": "MONDO:0005405",
                    },
                    {
                        "label": "Inflammatory bowel disease",
                        "ontology_id": "MONDO:0005265",
                    },
                ],
            )
        }
        with patch(
            "app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag",
            return_value=mock_result,
        ):
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        cond = response.json()["fields"]["condition"]
        assert cond["mapping_tier"] == "review"
        assert cond["ontology_id"] == "MONDO:0005405"
        assert cond["mapping_candidates"] == [
            {"label": "Irritable bowel syndrome", "ontology_id": "MONDO:0005405"},
            {"label": "Inflammatory bowel disease", "ontology_id": "MONDO:0005265"},
        ]

    def test_auto_tier_mapping_reaches_api(self, client):
        """An auto-tier mapping must keep its tier - not be downgraded or
        stripped by the schema layer."""
        mock_result = _mock_result()
        mock_result["fields"] = {
            "host_species": _grounded_field(
                "Homo sapiens",
                ontology_id="NCBITaxon:9606",
                mapping_confidence=1.0,
                mapping_tier="auto",
            )
        }
        with patch(
            "app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag",
            return_value=mock_result,
        ):
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        hs = response.json()["fields"]["host_species"]
        assert hs["mapping_tier"] == "auto"
        assert hs["ontology_id"] == "NCBITaxon:9606"

    def test_multiple_fields_independent_mapping_tiers(self, client):
        """Fields in the same response must each keep their own tier -
        auto/review/none must not bleed into each other."""
        mock_result = _mock_result()
        mock_result["fields"] = {
            "host_species": _grounded_field(
                "Homo sapiens",
                ontology_id="NCBITaxon:9606",
                mapping_confidence=1.0,
                mapping_tier="auto",
            ),
            "condition": _grounded_field(
                "Irritable bowel syndrome",
                ontology_id="MONDO:0005405",
                mapping_confidence=0.6,
                mapping_tier="review",
                mapping_candidates=[
                    {
                        "label": "Irritable bowel syndrome",
                        "ontology_id": "MONDO:0005405",
                    }
                ],
            ),
            "sample_size": _grounded_field(
                "",
                status="ABSENT",
                reason_if_missing="Information not found in the paper",
            ),
        }
        with patch(
            "app.api.routers.bugsigdb_analysis_v2.analyze_paper_with_rag",
            return_value=mock_result,
        ):
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        fields = response.json()["fields"]
        assert fields["host_species"]["mapping_tier"] == "auto"
        assert fields["condition"]["mapping_tier"] == "review"
        assert fields["sample_size"]["mapping_tier"] == "none"
        assert fields["host_species"]["ontology_id"] == "NCBITaxon:9606"
        assert fields["condition"]["ontology_id"] == "MONDO:0005405"
        assert fields["sample_size"]["ontology_id"] == ""

    def test_multiple_papers_preserve_independent_ontology_results(self, client):
        """Real pipeline, real per-paper grounding: a batch of 2 papers with
        different host species must each keep their own distinct ontology_id,
        not share/leak state across concurrent batch tasks."""
        abstracts = {
            "11111111": "A study of 15 human patients with Crohn disease.",
            "22222222": "A study of 20 mice with induced colitis.",
        }

        def get_retriever():
            # get_pubmed_retriever() takes no pmid argument (it returns one
            # shared retriever instance); the pmid-specific abstract is
            # selected via get_texts_for_analysis_async's call args instead.
            combined = MagicMock()

            async def get_texts_for_analysis_async(pmid, *args, **kwargs):
                return {
                    "title": f"Paper {pmid}",
                    "abstract": abstracts[str(pmid)],
                    "full_text": "",
                    "publication_date": "2023-01-01",
                    "journal": "J",
                    "authors": ["A"],
                }

            combined.get_texts_for_analysis_async = get_texts_for_analysis_async
            return combined

        def get_qa():
            combined = MagicMock()

            async def chat(prompt, *args, **kwargs):
                # Route on the paper title embedded in "Title:   Paper
                # <pmid>" (EXTRACTION_PROMPT's "PAPER CONTENT" section) -
                # not on abstract wording like "Crohn"/"colitis", since
                # EXTRACTION_PROMPT's own rules text contains a fixed
                # "Crohn's disease" worked example in every single prompt
                # regardless of paper content, which would make routing on
                # that substring match every call the same way.
                if "Paper 11111111" in prompt:
                    return {"text": '{"host_species_raw": "human"}'}
                if "Paper 22222222" in prompt:
                    return {"text": '{"host_species_raw": "mouse"}'}
                return {"text": "{}"}

            combined.chat = chat
            return combined

        with (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                side_effect=get_retriever,
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                side_effect=get_qa,
            ),
            patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=True),
        ):
            response = client.post(
                "/api/v2/analyze/batch",
                json={
                    "pmids": list(abstracts.keys()),
                    "use_rag": False,
                    "max_concurrent": 2,
                },
            )
        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) == 2
        by_pmid = {r["pmid"]: r for r in results}
        human_id = by_pmid["11111111"]["fields"]["host_species"]["ontology_id"]
        mouse_id = by_pmid["22222222"]["fields"]["host_species"]["ontology_id"]
        assert human_id == "NCBITaxon:9606"
        assert mouse_id == "NCBITaxon:10090"
        assert human_id != mouse_id

    def test_v1_still_exposes_ontology_metadata_unchanged(self, client):
        """v1's Dict[str, Any] return type was never schema-filtered, so it
        already exposed ontology_id/mapping_tier/etc - confirm that remains
        true (no fix needed there, per the audit)."""
        with (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                return_value=_make_real_retriever(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                return_value=_make_real_unified_qa('{"host_species_raw": "human"}'),
            ),
            patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=True),
        ):
            response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 200
        hs = response.json()["fields"]["host_species"]
        assert hs["ontology_id"] == "NCBITaxon:9606"
        assert hs["mapping_tier"] == "auto"
        assert "mapping_confidence" in hs
        assert "mapping_candidates" in hs


# --------------------------------------------------------------------------- #
# Top-level analysis fields (year, has_differential_abundance,
# differential_abundance_confidence): app/services/bugsigdb_analyzer/
# __init__.py's documented "Output contract" lists these as always-present
# top-level keys for BOTH analyze_paper_simple and analyze_paper_with_rag
# (confirmed live: simple_analysis.py/rag_analysis.py's result-dict
# assembly always sets all three). PaperAnalysisResult (the base of the v2
# response model) never declared them, so v2 single/POST/batch silently
# dropped all three via response-model filtering - v1 (Dict[str, Any],
# never filtered) was unaffected. Same defect class as the earlier
# in_bugsigdb gap, found during a broader top-to-bottom contract audit.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestTopLevelAnalysisFieldsResponseContract:
    def _real_patches(
        self, abstract, json_text, is_present=True, publication_date="2022-01-01"
    ):
        return (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                return_value=_make_real_retriever(
                    abstract=abstract, publication_date=publication_date
                ),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                return_value=_make_real_unified_qa(json_text),
            ),
            patch(
                "app.services.bugsigdb_analyzer.is_in_bugsigdb",
                return_value=is_present,
            ),
        )

    def test_genuine_v2_single_paper_exposes_year_and_differential_abundance(
        self, client
    ):
        """Real pipeline (real detect_differential_abundance resolution via
        the LLM payload, real extract_year off publication_date): all three
        previously-dropped fields must reach the actual v2 HTTP JSON,
        matching what the service function itself computed."""
        p1, p2, p3, p4 = self._real_patches(
            abstract=(
                "A study of 30 human patients with colorectal cancer. "
                "Bacteroides was significantly enriched and Firmicutes "
                "depleted, FDR < 0.05."
            ),
            json_text=(
                '{"host_species_raw": "human", '
                '"has_differential_abundance": true, '
                '"differential_abundance_confidence": 0.9}'
            ),
            publication_date="2022-01-01",
        )
        with p1, p2, p3, p4:
            response = client.get("/api/v2/analyze/12345678?use_rag=false")
        assert response.status_code == 200
        body = response.json()
        assert body["year"] == 2022
        assert body["has_differential_abundance"] is True
        assert body["differential_abundance_confidence"] == 0.9
        # Unrelated previously-fixed fields must remain intact too.
        assert body["in_bugsigdb"] is True
        assert body["fields"]["host_species"]["ontology_id"] == "NCBITaxon:9606"

    def test_genuine_v2_no_year_no_differential_abundance_not_fabricated(self, client):
        """When the real pipeline finds no year and no differential
        abundance signal, the API must reflect that honestly - "" for
        year (matching extract_year()'s real Optional[int]->"" mapping),
        False/0.0 for the differential-abundance pair - never omitted,
        never invented."""
        p1, p2, p3, p4 = self._real_patches(
            abstract="A study with no clear metadata.",
            json_text='{"host_species_raw": null}',
            is_present=False,
            publication_date="",
        )
        with p1, p2, p3, p4:
            response = client.get("/api/v2/analyze/99999999?use_rag=false")
        assert response.status_code == 200
        body = response.json()
        assert body["year"] == ""
        assert body["has_differential_abundance"] is False
        assert body["differential_abundance_confidence"] == 0.0

    def test_genuine_v1_still_exposes_these_fields_unchanged(self, client):
        """v1 was never affected (Dict[str, Any], unfiltered) - confirm it
        still isn't, after the schema fix."""
        p1, p2, p3, p4 = self._real_patches(
            abstract=(
                "A study of 30 human patients with colorectal cancer. "
                "Bacteroides was significantly enriched and Firmicutes "
                "depleted, FDR < 0.05."
            ),
            json_text=(
                '{"host_species_raw": "human", '
                '"has_differential_abundance": true, '
                '"differential_abundance_confidence": 0.9}'
            ),
            publication_date="2022-01-01",
        )
        with p1, p2, p3, p4:
            response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 200
        body = response.json()
        assert body["year"] == 2022
        assert body["has_differential_abundance"] is True
        assert body["differential_abundance_confidence"] == 0.9

    def test_genuine_v2_batch_preserves_independent_values_per_paper(self, client):
        """Two real papers with different years/differential-abundance
        outcomes in one batch call must each keep their own values."""

        def get_retriever():
            combined = MagicMock()

            async def get_texts_for_analysis_async(pmid, *args, **kwargs):
                if str(pmid) == "11111111":
                    return {
                        "title": "Paper 11111111",
                        "abstract": "A 2019 study of human Crohn disease patients.",
                        "full_text": "",
                        "publication_date": "2019-01-01",
                        "journal": "J",
                        "authors": ["A"],
                    }
                return {
                    "title": "Paper 22222222",
                    "abstract": "A 2021 study of mouse colitis.",
                    "full_text": "",
                    "publication_date": "2021-01-01",
                    "journal": "J",
                    "authors": ["A"],
                }

            combined.get_texts_for_analysis_async = get_texts_for_analysis_async
            return combined

        def get_qa():
            combined = MagicMock()

            async def chat(prompt, *args, **kwargs):
                if "Paper 11111111" in prompt:
                    return {
                        "text": (
                            '{"host_species_raw": "human", '
                            '"has_differential_abundance": true, '
                            '"differential_abundance_confidence": 0.9}'
                        )
                    }
                if "Paper 22222222" in prompt:
                    return {
                        "text": (
                            '{"host_species_raw": "mouse", '
                            '"has_differential_abundance": false, '
                            '"differential_abundance_confidence": 0.0}'
                        )
                    }
                return {"text": "{}"}

            combined.chat = chat
            return combined

        with (
            patch(
                "app.services.bugsigdb_analyzer.get_cache_manager",
                return_value=_make_real_cache_manager(),
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_pubmed_retriever",
                side_effect=get_retriever,
            ),
            patch(
                "app.services.bugsigdb_analyzer.get_unified_qa",
                side_effect=get_qa,
            ),
            patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=True),
        ):
            response = client.post(
                "/api/v2/analyze/batch",
                json={
                    "pmids": ["11111111", "22222222"],
                    "use_rag": False,
                    "max_concurrent": 2,
                },
            )
        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) == 2
        by_pmid = {r["pmid"]: r for r in results}
        assert by_pmid["11111111"]["year"] == 2019
        assert by_pmid["11111111"]["has_differential_abundance"] is True
        assert by_pmid["22222222"]["year"] == 2021
        assert by_pmid["22222222"]["has_differential_abundance"] is False
