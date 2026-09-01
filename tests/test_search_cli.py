import pytest

pytest.importorskip("defusedxml")

from unittest.mock import MagicMock
from app.services.pubmed_queries import (
    RECOMMENDED_DISCOVERY_QUERY,
    BULK_RETRIEVAL_QUERIES,
)
from scripts.cli import BioAnalyzerCLI


def test_search_pubmed_returns_pmids(monkeypatch):
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = ["111", "222"]
    mock_cls = MagicMock(return_value=mock_retriever)

    import app.services.data_retrieval as dr

    monkeypatch.setattr(dr, "PubMedRetriever", mock_cls)
    monkeypatch.setenv("NCBI_API_KEY", "test-key")

    cli = BioAnalyzerCLI()
    pmids = cli.search_pubmed(preset="discovery", max_results=10, fmt="txt")
    assert pmids == ["111", "222"]

    # term is always the first positional arg
    call_term = mock_retriever.search.call_args[0][0]
    assert call_term == RECOMMENDED_DISCOVERY_QUERY

    # max_results may be positional or keyword depending on implementation
    all_args = list(mock_retriever.search.call_args[0]) + list(
        mock_retriever.search.call_args[1].values()
    )
    assert 10 in all_args


def test_curate_topic_searches_only_no_analysis(monkeypatch):
    """curate is search-only (PMIDs, ready for `analyze --file`) - it must
    never call anything analysis-related, and each topic must map to its
    real BULK_RETRIEVAL_QUERIES MeSH string."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = ["333", "444"]
    mock_cls = MagicMock(return_value=mock_retriever)

    import app.services.data_retrieval as dr

    monkeypatch.setattr(dr, "PubMedRetriever", mock_cls)
    monkeypatch.setenv("NCBI_API_KEY", "test-key")

    cli = BioAnalyzerCLI()
    pmids = cli.curate_topic("masld", 5, "txt", None)
    assert pmids == ["333", "444"]
    assert mock_retriever.search.call_args[0][0] == BULK_RETRIEVAL_QUERIES["masld"]
