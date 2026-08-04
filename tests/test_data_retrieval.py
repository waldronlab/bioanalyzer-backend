"""
Tests for app/services/data_retrieval.py::PubMedRetriever - the primary
PubMed/PMC retriever used by the production analysis pipeline (confirmed via
get_pubmed_retriever() in bugsigdb_analyzer.py). Coverage was previously 20%
(tests/test_pubmed_retriever_errors.py exercises only one no-response path).

PubMedRetriever.__init__ calls _verify_connectivity(), which makes a real
NCBI network request by design (never raises - it only logs a warning on
failure). Per CLAUDE.md's "no live network dependency in the suite", every
test here patches _verify_connectivity to a no-op before construction so
these tests stay hermetic regardless of sandbox network access.
"""

import asyncio
import pytest
import requests

from conftest import make_fake_response_class
from app.services.data_retrieval import PubMedRetriever, PubMedRetrieverError


PUBMED_ARTICLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <Article>
        <ArticleTitle>A Study of Gut Microbiome in Humans</ArticleTitle>
        <Abstract><AbstractText>Some abstract text.</AbstractText></Abstract>
        <Journal><Title>Journal of Microbiome Research</Title></Journal>
        <AuthorList>
          <Author><ForeName>Jane</ForeName><LastName>Doe</LastName></Author>
        </AuthorList>
        <Journal>
          <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""

ESUMMARY_XML = """<?xml version="1.0"?>
<eSummaryResult>
  <DocSum>
    <Id>12345678</Id>
    <Item Name="Title" Type="String">Fallback Title</Item>
    <Item Name="FullJournalName" Type="String">Fallback Journal</Item>
    <Item Name="PubDate" Type="String">2020</Item>
    <Item Name="AuthorList" Type="List">
      <Item Name="Author" Type="String">Doe J</Item>
    </Item>
  </DocSum>
</eSummaryResult>"""

ELINK_WITH_PMC_XML = """<?xml version="1.0"?>
<eLinkResult>
  <LinkSet>
    <LinkSetDb>
      <DbTo>pmc</DbTo>
      <LinkName>pubmed_pmc</LinkName>
      <Link><Id>9988776</Id></Link>
    </LinkSetDb>
  </LinkSet>
</eLinkResult>"""

PMC_FULLTEXT_XML = """<?xml version="1.0"?>
<article>
  <article-title>Full Article Title</article-title>
  <abstract>The abstract.</abstract>
  <body><p>Paragraph one.</p><p>Paragraph two.</p></body>
</article>"""

ESEARCH_XML = """<?xml version="1.0"?>
<eSearchResult><IdList><Id>111</Id><Id>222</Id></IdList></eSearchResult>"""


# PubMedRetriever._make_request inspects `error.response.status_code` to
# detect a 429 rate-limit response and apply extra backoff (see
# data_retrieval.py), so the fake response here needs
# set_response_on_error=True for TestMakeRequest's rate-limit test to
# actually exercise that path - unlike
# test_standalone_pubmed_retriever.py's identical-looking fixture, whose
# retriever doesn't inspect the response on error.
_FakeResponse = make_fake_response_class(set_response_on_error=True)


@pytest.fixture
def retriever(monkeypatch):
    monkeypatch.setattr(PubMedRetriever, "_verify_connectivity", lambda self, **k: None)
    return PubMedRetriever(api_key="test-key", email="test@example.com")


class TestVerifyConnectivity:
    def test_succeeds_silently_when_reachable(self, monkeypatch):
        r = PubMedRetriever.__new__(PubMedRetriever)
        r.api_key = None
        r.email = "x@example.com"
        r.session = r._create_session()
        monkeypatch.setattr(r.session, "get", lambda *a, **k: _FakeResponse("ok"))
        r._verify_connectivity(retries=1)  # should not raise

    def test_does_not_raise_when_unreachable(self, monkeypatch):
        r = PubMedRetriever.__new__(PubMedRetriever)
        r.api_key = None
        r.email = "x@example.com"
        r.session = r._create_session()

        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("no network")

        monkeypatch.setattr(r.session, "get", boom)
        monkeypatch.setattr("time.sleep", lambda *_: None)
        r._verify_connectivity(retries=2)  # should not raise


class TestPrepareRequestParamsAndRateLimiting:
    def test_adds_api_key_and_contact_fields(self, retriever):
        params = retriever._prepare_request_params({"db": "pubmed"})
        assert params["api_key"] == "test-key"
        assert params["email"] == "test@example.com"
        assert params["tool"] == "BioAnalyzer"

    def test_omits_api_key_when_none(self, monkeypatch):
        monkeypatch.setattr(
            PubMedRetriever, "_verify_connectivity", lambda self, **k: None
        )
        r = PubMedRetriever(api_key=None, email="x@example.com")
        params = r._prepare_request_params({"db": "pubmed"})
        assert "api_key" not in params

    def test_apply_rate_limiting_sleeps_non_negative_delay(
        self, retriever, monkeypatch
    ):
        captured = {}
        monkeypatch.setattr("time.sleep", lambda d: captured.setdefault("delay", d))
        retriever._apply_rate_limiting()
        assert captured["delay"] >= 0


class TestCalculateBackoffTime:
    def test_doubles_with_attempt(self, retriever):
        assert retriever._calculate_backoff_time(0, False) == 1.0
        assert retriever._calculate_backoff_time(1, False) == 2.0

    def test_rate_limited_applies_extra_multiplier(self, retriever):
        normal = retriever._calculate_backoff_time(1, False)
        limited = retriever._calculate_backoff_time(1, True)
        assert limited == normal * 2.0


class TestValidateField:
    def test_true_for_non_empty(self):
        assert PubMedRetriever.validate_field("value") is True

    def test_false_for_none_or_blank(self):
        assert PubMedRetriever.validate_field(None) is False
        assert PubMedRetriever.validate_field("   ") is False
        assert PubMedRetriever.validate_field("") is False


class TestMakeRequest:
    def test_success(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("ok")
        )
        monkeypatch.setattr("time.sleep", lambda *_: None)
        assert retriever._make_request("efetch.fcgi", {"db": "pubmed"}) == "ok"

    def test_retries_on_rate_limit_then_succeeds(self, retriever, monkeypatch):
        responses = [_FakeResponse("", 429), _FakeResponse("recovered", 200)]

        def fake_get(*a, **k):
            return responses.pop(0)

        monkeypatch.setattr(retriever.session, "get", fake_get)
        monkeypatch.setattr("time.sleep", lambda *_: None)
        result = retriever._make_request("efetch.fcgi", {"db": "pubmed"})
        assert result == "recovered"

    def test_returns_none_after_exhausting_retries(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session,
            "get",
            lambda *a, **k: _FakeResponse("", 500),
        )
        monkeypatch.setattr("time.sleep", lambda *_: None)
        result = retriever._make_request("efetch.fcgi", {"db": "pubmed"}, retries=2)
        assert result is None


class TestFetchPaperMetadata:
    def test_parses_full_article(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "_make_request", lambda *a, **k: PUBMED_ARTICLE_XML
        )
        result = retriever.fetch_paper_metadata("12345678")
        assert result["title"] == "A Study of Gut Microbiome in Humans"
        assert result["journal"] == "Journal of Microbiome Research"
        assert result["publication_date"] == "2021"
        assert "Jane Doe" in result["authors"]

    def test_returns_error_when_no_data(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: None)
        result = retriever.fetch_paper_metadata("12345678")
        assert "error" in result

    def test_returns_error_when_no_article_node(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever,
            "_make_request",
            lambda *a, **k: "<PubmedArticleSet></PubmedArticleSet>",
        )
        result = retriever.fetch_paper_metadata("12345678")
        assert result["error"] == "No article metadata found."

    def test_falls_back_to_esummary_on_parse_error(self, retriever, monkeypatch):
        calls = {"n": 0}

        def fake_make_request(endpoint, params, retries=None):
            calls["n"] += 1
            if endpoint == "efetch.fcgi":
                return "<not<valid"
            return ESUMMARY_XML

        monkeypatch.setattr(retriever, "_make_request", fake_make_request)
        result = retriever.fetch_paper_metadata("12345678")
        assert result["title"] == "Fallback Title"
        assert result["journal"] == "Fallback Journal"

    def test_esummary_fallback_returns_error_when_unreachable(
        self, retriever, monkeypatch
    ):
        def fake_make_request(endpoint, params, retries=None):
            return "<not<valid" if endpoint == "efetch.fcgi" else None

        monkeypatch.setattr(retriever, "_make_request", fake_make_request)
        result = retriever.fetch_paper_metadata("12345678")
        assert result["error"] == "Failed to retrieve esummary fallback."

    def test_esummary_fallback_returns_error_when_no_docsum(
        self, retriever, monkeypatch
    ):
        def fake_make_request(endpoint, params, retries=None):
            if endpoint == "efetch.fcgi":
                return "<not<valid"
            return "<eSummaryResult></eSummaryResult>"

        monkeypatch.setattr(retriever, "_make_request", fake_make_request)
        result = retriever.fetch_paper_metadata("12345678")
        assert result["error"] == "No summary record found."


class TestSearch:
    def test_returns_pmid_list(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: ESEARCH_XML)
        assert retriever.search("gut microbiome") == ["111", "222"]

    def test_returns_empty_list_when_no_data(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: None)
        assert retriever.search("gut microbiome") == []

    def test_returns_empty_list_on_parse_error(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: "<bad<xml")
        assert retriever.search("gut microbiome") == []


class TestGetPaperMetadataAsync:
    def test_delegates_to_sync_fetch(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "fetch_paper_metadata", lambda pmid: {"pmid": pmid}
        )
        result = asyncio.run(retriever.get_paper_metadata_async("12345678"))
        assert result == {"pmid": "12345678"}


class TestGetPmcIdFromPmid:
    def test_resolves_pmc_id_with_prefix(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "_make_request", lambda *a, **k: ELINK_WITH_PMC_XML
        )
        assert retriever._get_pmc_id_from_pmid("12345678") == "PMC9988776"

    def test_returns_none_when_no_data(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: None)
        assert retriever._get_pmc_id_from_pmid("12345678") is None

    def test_returns_none_on_parse_error(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: "<bad<xml")
        assert retriever._get_pmc_id_from_pmid("12345678") is None


class TestGetPmcFulltextById:
    def test_extracts_title_abstract_and_body(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "_make_request", lambda *a, **k: PMC_FULLTEXT_XML
        )
        text = retriever._get_pmc_fulltext_by_id("PMC9988776")
        assert "Full Article Title" in text
        assert "The abstract." in text
        assert "Paragraph one. Paragraph two." in text

    def test_strips_pmc_prefix_from_request_id(self, retriever, monkeypatch):
        captured = {}

        def fake_make_request(endpoint, params, retries=None):
            captured.update(params)
            return PMC_FULLTEXT_XML

        monkeypatch.setattr(retriever, "_make_request", fake_make_request)
        retriever._get_pmc_fulltext_by_id("PMC9988776")
        assert captured["id"] == "9988776"

    def test_returns_empty_string_when_unavailable(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: None)
        assert retriever._get_pmc_fulltext_by_id("PMC9988776") == ""

    def test_returns_empty_string_on_parse_error(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_make_request", lambda *a, **k: "<bad<xml")
        assert retriever._get_pmc_fulltext_by_id("PMC9988776") == ""


class TestGetPmcFulltext:
    def test_returns_text_when_pmc_id_found(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "_get_pmc_id_from_pmid", lambda pmid: "PMC9988776"
        )
        monkeypatch.setattr(
            retriever, "_get_pmc_fulltext_by_id", lambda pmc_id: "full text here"
        )
        assert retriever.get_pmc_fulltext("12345678") == "full text here"

    def test_returns_empty_when_no_pmc_id(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "_get_pmc_id_from_pmid", lambda pmid: None)
        assert retriever.get_pmc_fulltext("12345678") == ""

    def test_returns_empty_on_network_error(self, retriever, monkeypatch):
        def boom(pmid):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(retriever, "_get_pmc_id_from_pmid", boom)
        assert retriever.get_pmc_fulltext("12345678") == ""

    def test_returns_empty_on_unexpected_error(self, retriever, monkeypatch):
        def boom(pmid):
            raise ValueError("totally unexpected")

        monkeypatch.setattr(retriever, "_get_pmc_id_from_pmid", boom)
        assert retriever.get_pmc_fulltext("12345678") == ""


class TestGetPmcFulltextAsync:
    def test_delegates_to_sync_method(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever, "get_pmc_fulltext", lambda pmid: "async text")
        result = asyncio.run(retriever.get_pmc_fulltext_async("12345678"))
        assert result == "async text"


class TestGetFullPaperData:
    def test_combines_metadata_and_fulltext(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever,
            "fetch_paper_metadata",
            lambda pmid: {
                "pmid": pmid,
                "title": "T",
                "abstract": "A",
                "journal": "J",
                "authors": ["X"],
                "publication_date": "2020",
            },
        )
        monkeypatch.setattr(retriever, "get_pmc_fulltext", lambda pmid: "full text")
        result = retriever.get_full_paper_data("12345678")
        assert result["has_full_text"] is True
        assert result["title"] == "T"
        assert result["full_text"] == "full text"

    def test_propagates_metadata_error(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "fetch_paper_metadata", lambda pmid: {"error": "boom"}
        )
        result = retriever.get_full_paper_data("12345678")
        assert result == {"error": "boom"}

    def test_network_error_returns_safe_default_dict(self, retriever, monkeypatch):
        def boom(pmid):
            raise requests.exceptions.ConnectionError("sk-" + "x" * 20)

        monkeypatch.setattr(retriever, "fetch_paper_metadata", boom)
        result = retriever.get_full_paper_data("12345678")
        assert result["pmid"] == "12345678"
        assert result["has_full_text"] is False
        assert "sk-" not in result["error"]


class TestGetFullPaperDataAsync:
    def test_delegates_to_sync_method(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever, "get_full_paper_data", lambda pmid: {"pmid": pmid}
        )
        result = asyncio.run(retriever.get_full_paper_data_async("12345678"))
        assert result == {"pmid": "12345678"}


class TestGetTextsForAnalysisAsync:
    def test_fetches_metadata_and_fulltext_concurrently(self, retriever, monkeypatch):
        monkeypatch.setattr("app.services.data_retrieval.USE_FULLTEXT", True)
        monkeypatch.setattr(
            retriever,
            "get_paper_metadata_async",
            lambda pmid: asyncio.sleep(
                0,
                result={
                    "title": "T",
                    "abstract": "A",
                    "journal": "J",
                    "authors": ["A B"],
                    "publication_date": "2021",
                },
            ),
        )
        monkeypatch.setattr(
            retriever,
            "get_pmc_fulltext_async",
            lambda pmid: asyncio.sleep(0, result="full text"),
        )
        result = asyncio.run(retriever.get_texts_for_analysis_async("12345678"))
        assert result == {
            "title": "T",
            "abstract": "A",
            "full_text": "full text",
            "journal": "J",
            "authors": ["A B"],
            "publication_date": "2021",
        }

    def test_skips_fulltext_when_use_fulltext_false(self, retriever, monkeypatch):
        monkeypatch.setattr("app.services.data_retrieval.USE_FULLTEXT", False)
        monkeypatch.setattr(
            retriever,
            "get_paper_metadata_async",
            lambda pmid: asyncio.sleep(
                0,
                result={
                    "title": "T",
                    "abstract": "A",
                    "journal": "J",
                    "authors": ["A B"],
                    "publication_date": "2021",
                },
            ),
        )
        result = asyncio.run(retriever.get_texts_for_analysis_async("12345678"))
        assert result == {
            "title": "T",
            "abstract": "A",
            "full_text": "",
            "journal": "J",
            "authors": ["A B"],
            "publication_date": "2021",
        }

    def test_metadata_timeout_returns_empty_strings(self, retriever, monkeypatch):
        # asyncio.wait_for() re-raises whatever the wrapped awaitable raises,
        # so a coroutine that itself raises TimeoutError exercises the same
        # `except asyncio.TimeoutError` branch as a real 6s timeout would,
        # without an actual multi-second wait in the test.
        monkeypatch.setattr("app.services.data_retrieval.USE_FULLTEXT", True)

        async def raise_timeout(pmid):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(retriever, "get_paper_metadata_async", raise_timeout)
        monkeypatch.setattr(
            retriever,
            "get_pmc_fulltext_async",
            lambda pmid: asyncio.sleep(0, result="full text"),
        )
        result = asyncio.run(retriever.get_texts_for_analysis_async("12345678"))
        assert result == {
            "title": "",
            "abstract": "",
            "full_text": "full text",
            "journal": "",
            "authors": [],
            "publication_date": "",
        }

    def test_metadata_network_error_returns_empty_dict_fields(
        self, retriever, monkeypatch
    ):
        monkeypatch.setattr("app.services.data_retrieval.USE_FULLTEXT", True)

        async def boom(pmid):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(retriever, "get_paper_metadata_async", boom)
        monkeypatch.setattr(
            retriever,
            "get_pmc_fulltext_async",
            lambda pmid: asyncio.sleep(0, result=""),
        )
        result = asyncio.run(retriever.get_texts_for_analysis_async("12345678"))
        assert result == {
            "title": "",
            "abstract": "",
            "full_text": "",
            "journal": "",
            "authors": [],
            "publication_date": "",
        }

    def test_fulltext_network_error_falls_back_to_empty_string(
        self, retriever, monkeypatch
    ):
        monkeypatch.setattr("app.services.data_retrieval.USE_FULLTEXT", True)

        async def boom(pmid):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(
            retriever,
            "get_paper_metadata_async",
            lambda pmid: asyncio.sleep(
                0,
                result={
                    "title": "T",
                    "abstract": "A",
                    "journal": "J",
                    "authors": ["A B"],
                    "publication_date": "2021",
                },
            ),
        )
        monkeypatch.setattr(retriever, "get_pmc_fulltext_async", boom)
        result = asyncio.run(retriever.get_texts_for_analysis_async("12345678"))
        assert result == {
            "title": "T",
            "abstract": "A",
            "full_text": "",
            "journal": "J",
            "authors": ["A B"],
            "publication_date": "2021",
        }


def test_pubmed_retriever_error_is_an_exception():
    assert issubclass(PubMedRetrieverError, Exception)
