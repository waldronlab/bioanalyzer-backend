import pytest


def test_fetch_paper_metadata_handles_no_response(monkeypatch):
    """
    fetch_paper_metadata should return a structured error when the
    underlying _make_request returns no data (e.g., network failure).
    """
    import sys
    import importlib.util
    from pathlib import Path

    # Try direct import first
    try:
        from app.services.data_retrieval import PubMedRetriever
    except ImportError:
        # Fallback: use importlib to load directly from file
        # Use project root path instead of hardcoded /app/app
        project_root = Path(__file__).parent.parent
        data_retrieval_path = project_root / "app" / "services" / "data_retrieval.py"

        if not data_retrieval_path.exists():
            pytest.skip("data_retrieval.py not found")

        spec = importlib.util.spec_from_file_location(
            "data_retrieval", str(data_retrieval_path)
        )
        if spec is None or spec.loader is None:
            pytest.skip("Could not load data_retrieval module")

        data_retrieval_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(data_retrieval_module)
        PubMedRetriever = data_retrieval_module.PubMedRetriever

    retriever = PubMedRetriever(api_key=None)

    def _fake_make_request(endpoint, params, retries=None):
        return None

    monkeypatch.setattr(retriever, "_make_request", _fake_make_request)

    result = retriever.fetch_paper_metadata("12345678")
    assert isinstance(result, dict)
    assert "error" in result
    assert "PubMed unreachable" in result["error"]
