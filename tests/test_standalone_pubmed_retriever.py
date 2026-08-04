"""
Tests for app/services/standalone_pubmed_retriever.py - previously had zero
test coverage (confirmed via coverage report: 0%). Follows the
monkeypatch.setattr(requests, ...)-style HTTP mocking already used in
tests/test_cli_health.py, applied to the instance's `session.get` (this
class uses a requests.Session, not the bare requests module).
"""

import pytest
import requests

from conftest import make_fake_response_class
from app.services.standalone_pubmed_retriever import (
    StandalonePubMedRetriever,
    StandalonePubMedRetrieverError,
)


PUBMED_ARTICLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <Article>
        <ArticleTitle>A Study of Gut Microbiome in Humans</ArticleTitle>
        <Abstract>
          <AbstractText>Background text.</AbstractText>
          <AbstractText>Results text.</AbstractText>
        </Abstract>
        <Journal><Title>Journal of Microbiome Research</Title></Journal>
        <AuthorList>
          <Author><ForeName>Jane</ForeName><LastName>Doe</LastName></Author>
          <Author><ForeName>John</ForeName><LastName>Smith</LastName></Author>
          <Author><CollectiveName>Some Consortium</CollectiveName></Author>
        </AuthorList>
        <Journal>
          <JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""

PUBMED_ARTICLE_NO_YEAR_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <Article>
        <ArticleTitle>Fallback Date Paper</ArticleTitle>
        <ArticleDate><Year>2019</Year></ArticleDate>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""

ELINK_WITH_PMC_XML = """<?xml version="1.0"?>
<eLinkResult>
  <LinkSet>
    <LinkSetDb>
      <DbTo>pmc</DbTo>
      <LinkName>pubmed_pmc</LinkName>
      <Link><Id>1234567</Id></Link>
    </LinkSetDb>
  </LinkSet>
</eLinkResult>"""

ELINK_NO_MATCH_XML = """<?xml version="1.0"?>
<eLinkResult>
  <LinkSet>
    <LinkSetDb>
      <DbTo>other</DbTo>
      <LinkName>something_else</LinkName>
      <Link><Id>999</Id></Link>
    </LinkSetDb>
  </LinkSet>
</eLinkResult>"""

ESEARCH_XML = """<?xml version="1.0"?>
<eSearchResult>
  <IdList>
    <Id>111</Id>
    <Id>222</Id>
  </IdList>
</eSearchResult>"""


# StandalonePubMedRetriever._make_request doesn't inspect the response on
# error, so this fake doesn't need to attach one to the raised HTTPError -
# unlike tests/test_data_retrieval.py's identical-looking fixture, whose
# retriever does.
_FakeResponse = make_fake_response_class(set_response_on_error=False)


@pytest.fixture
def retriever():
    r = StandalonePubMedRetriever(api_key="test-key", email="test@example.com")
    r.RATE_LIMIT_DELAY = 0  # don't actually sleep during tests
    return r


class TestMakeRequest:
    def test_success_on_first_attempt(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("ok-body")
        )
        result = retriever._make_request("efetch.fcgi", {"db": "pubmed"})
        assert result == "ok-body"

    def test_retries_then_succeeds(self, retriever, monkeypatch):
        calls = {"n": 0}

        def flaky_get(*a, **k):
            calls["n"] += 1
            if calls["n"] < 2:
                raise requests.exceptions.ConnectionError("temporary failure")
            return _FakeResponse("recovered")

        monkeypatch.setattr(retriever.session, "get", flaky_get)
        monkeypatch.setattr("time.sleep", lambda *_: None)
        result = retriever._make_request("efetch.fcgi", {"db": "pubmed"})
        assert result == "recovered"
        assert calls["n"] == 2

    def test_returns_none_after_exhausting_retries(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session,
            "get",
            lambda *a, **k: (_ for _ in ()).throw(
                requests.exceptions.ConnectionError("down")
            ),
        )
        monkeypatch.setattr("time.sleep", lambda *_: None)
        result = retriever._make_request("efetch.fcgi", {"db": "pubmed"}, retries=2)
        assert result is None

    def test_raises_http_error_status_treated_as_failure(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("", 500)
        )
        monkeypatch.setattr("time.sleep", lambda *_: None)
        result = retriever._make_request("efetch.fcgi", {"db": "pubmed"}, retries=1)
        assert result is None

    def test_includes_api_key_in_params_when_set(self, retriever, monkeypatch):
        captured = {}

        def capture_get(url, params=None, timeout=None):
            captured.update(params or {})
            return _FakeResponse("ok")

        monkeypatch.setattr(retriever.session, "get", capture_get)
        retriever._make_request("efetch.fcgi", {"db": "pubmed"})
        assert captured.get("api_key") == "test-key"
        assert captured.get("email") == "test@example.com"

    def test_omits_api_key_when_not_set(self, monkeypatch):
        r = StandalonePubMedRetriever(api_key=None, email="x@example.com")
        r.RATE_LIMIT_DELAY = 0
        captured = {}

        def capture_get(url, params=None, timeout=None):
            captured.update(params or {})
            return _FakeResponse("ok")

        monkeypatch.setattr(r.session, "get", capture_get)
        r._make_request("efetch.fcgi", {"db": "pubmed"})
        assert "api_key" not in captured


class TestFetchPaperMetadata:
    def test_parses_full_article(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse(PUBMED_ARTICLE_XML)
        )
        result = retriever.fetch_paper_metadata("12345678")
        assert result["title"] == "A Study of Gut Microbiome in Humans"
        assert result["abstract"] == "Background text. Results text."
        assert result["journal"] == "Journal of Microbiome Research"
        assert result["publication_date"] == "2022"
        assert "Jane Doe" in result["authors"]
        assert "John Smith" in result["authors"]

    def test_skips_authors_without_last_name(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse(PUBMED_ARTICLE_XML)
        )
        result = retriever.fetch_paper_metadata("12345678")
        assert len(result["authors"]) == 2

    def test_falls_back_to_article_date_year(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session,
            "get",
            lambda *a, **k: _FakeResponse(PUBMED_ARTICLE_NO_YEAR_XML),
        )
        result = retriever.fetch_paper_metadata("99999")
        assert result["publication_date"] == "2019"

    def test_returns_error_when_network_unreachable(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: _FakeResponse(""))
        result = retriever.fetch_paper_metadata("12345678")
        assert "error" in result

    def test_returns_error_on_malformed_xml(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("<not<valid")
        )
        result = retriever.fetch_paper_metadata("12345678")
        assert "error" in result
        assert "XML parsing failed" in result["error"]

    def test_returns_error_when_no_article_element(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session,
            "get",
            lambda *a, **k: _FakeResponse("<PubmedArticleSet></PubmedArticleSet>"),
        )
        result = retriever.fetch_paper_metadata("12345678")
        assert result["error"] == "No article metadata found."


class TestGetPmcIdFromPmid:
    def test_resolves_pmc_id_with_prefix_added(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session,
            "get",
            lambda *a, **k: _FakeResponse(ELINK_WITH_PMC_XML),
        )
        pmc_id = retriever._get_pmc_id_from_pmid("12345678")
        assert pmc_id == "PMC1234567"

    def test_returns_none_when_no_matching_linksetdb(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse(ELINK_NO_MATCH_XML)
        )
        assert retriever._get_pmc_id_from_pmid("12345678") is None

    def test_returns_none_when_request_fails(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: _FakeResponse(""))
        assert retriever._get_pmc_id_from_pmid("12345678") is None

    def test_returns_none_on_parse_error(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("<broken<xml")
        )
        assert retriever._get_pmc_id_from_pmid("12345678") is None


class TestFetchPmcXml:
    def test_returns_raw_xml_text(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("<article/>")
        )
        assert retriever._fetch_pmc_xml("PMC1234567") == "<article/>"

    def test_strips_pmc_prefix_from_request_id(self, retriever, monkeypatch):
        captured = {}

        def capture_get(url, params=None, timeout=None):
            captured.update(params or {})
            return _FakeResponse("<article/>")

        monkeypatch.setattr(retriever.session, "get", capture_get)
        retriever._fetch_pmc_xml("PMC1234567")
        assert captured.get("id") == "1234567"

    def test_returns_empty_string_when_unavailable(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: _FakeResponse(""))
        assert retriever._fetch_pmc_xml("PMC1234567") == ""


class TestGetFullPaperData:
    def test_full_success_with_pmc(self, retriever, monkeypatch):
        responses = [
            _FakeResponse(PUBMED_ARTICLE_XML),  # fetch_paper_metadata
            _FakeResponse(ELINK_WITH_PMC_XML),  # _get_pmc_id_from_pmid
            _FakeResponse("<article><body>full text</body></article>"),  # pmc xml
        ]
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: responses.pop(0))
        result = retriever.get_full_paper_data("12345678")
        assert result["pmid"] == "12345678"
        assert result["has_full_text"] is True
        assert "full text" in result["full_text"]

    def test_success_without_pmc_abstract_only(self, retriever, monkeypatch):
        responses = [
            _FakeResponse(PUBMED_ARTICLE_XML),  # metadata
            _FakeResponse(ELINK_NO_MATCH_XML),  # no pmc id found
        ]
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: responses.pop(0))
        result = retriever.get_full_paper_data("12345678")
        assert result["has_full_text"] is False
        assert result["full_text"] == ""
        assert result["title"] == "A Study of Gut Microbiome in Humans"

    def test_metadata_error_short_circuits(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: _FakeResponse(""))
        result = retriever.get_full_paper_data("12345678")
        assert "error" in result

    def test_unexpected_exception_returns_safe_default_dict(
        self, retriever, monkeypatch
    ):
        secret_key = "sk-" + "a1b2c3d4e5f6g7h8i9j0" * 2

        def boom(*a, **k):
            raise RuntimeError(f"request failed with key {secret_key}")

        monkeypatch.setattr(retriever, "fetch_paper_metadata", boom)
        result = retriever.get_full_paper_data("12345678")
        assert result["pmid"] == "12345678"
        assert result["has_full_text"] is False
        assert result["authors"] == []
        assert secret_key not in result["error"]


class TestSearchPapers:
    def test_returns_pmid_list(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse(ESEARCH_XML)
        )
        result = retriever.search_papers("gut microbiome")
        assert result == ["111", "222"]

    def test_returns_empty_list_when_no_data(self, retriever, monkeypatch):
        monkeypatch.setattr(retriever.session, "get", lambda *a, **k: _FakeResponse(""))
        assert retriever.search_papers("gut microbiome") == []

    def test_returns_empty_list_on_parse_error(self, retriever, monkeypatch):
        monkeypatch.setattr(
            retriever.session, "get", lambda *a, **k: _FakeResponse("<bad<xml")
        )
        assert retriever.search_papers("gut microbiome") == []


def test_pubmed_retriever_error_is_an_exception():
    assert issubclass(StandalonePubMedRetrieverError, Exception)
