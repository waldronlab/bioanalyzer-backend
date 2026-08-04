from conftest import import_with_fallback


def test_fetch_paper_metadata_handles_no_response(monkeypatch):
    """
    fetch_paper_metadata should return a structured error when the
    underlying _make_request returns no data (e.g., network failure).
    """
    PubMedRetriever = import_with_fallback("data_retrieval", "PubMedRetriever")

    # PubMedRetriever.__init__ calls _verify_connectivity(), which makes a
    # real NCBI network request by design. Patch it to a no-op before
    # construction so this test stays hermetic, matching every sibling test
    # in tests/test_data_retrieval.py.
    monkeypatch.setattr(PubMedRetriever, "_verify_connectivity", lambda self, **k: None)

    retriever = PubMedRetriever(api_key=None)

    def _fake_make_request(endpoint, params, retries=None):
        return None

    monkeypatch.setattr(retriever, "_make_request", _fake_make_request)

    result = retriever.fetch_paper_metadata("12345678")
    assert isinstance(result, dict)
    assert "error" in result
    assert "PubMed unreachable" in result["error"]
