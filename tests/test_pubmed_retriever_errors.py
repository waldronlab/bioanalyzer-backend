def test_fetch_paper_metadata_handles_no_response(monkeypatch):
    """
    fetch_paper_metadata should return a structured error when the
    underlying _make_request returns no data (e.g., network failure).
    """
    # CRITICAL: Set up path INSIDE test function - pytest may reset it
    import sys
    import importlib.util
    
    # Ensure /app/app is first (where the actual app package is)
    if '/app/app' not in sys.path:
        sys.path.insert(0, '/app/app')
    # Also add /app (parent directory)
    if '/app' not in sys.path:
        sys.path.insert(0, '/app')
    
    # Try direct import first
    try:
        from app.services.data_retrieval import PubMedRetriever
    except ImportError:
        # Fallback: use importlib to load directly from file
        spec = importlib.util.spec_from_file_location(
            "data_retrieval",
            "/app/app/services/data_retrieval.py"
        )
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
