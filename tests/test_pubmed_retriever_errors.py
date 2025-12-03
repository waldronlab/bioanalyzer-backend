from app.services.data_retrieval import PubMedRetriever


def test_fetch_paper_metadata_handles_no_response(monkeypatch):
    """
    fetch_paper_metadata should return a structured error when the
    underlying _make_request returns no data (e.g., network failure).
    """
    retriever = PubMedRetriever(api_key=None)

    def _fake_make_request(endpoint, params, retries=None):
        return None

    monkeypatch.setattr(retriever, "_make_request", _fake_make_request)

    result = retriever.fetch_paper_metadata("12345678")
    assert isinstance(result, dict)
    assert "error" in result
    assert "PubMed unreachable" in result["error"]


