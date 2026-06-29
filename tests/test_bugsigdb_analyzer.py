import pytest

# defusedxml may not be installed in lightweight test environments
pytest.importorskip("defusedxml")

from app.services.bugsigdb_analyzer import (
    _parse_pmc_sections,
    extract_year,
    prepare_analysis_context,
)


def test_parse_pmc_sections_with_namespaced_title():
    xml = """<article xmlns="http://example.com">
      <body>
        <sec>
          <title>Methods</title>
          <p>Experimental details here.</p>
        </sec>
      </body>
    </article>"""

    sections = _parse_pmc_sections(xml)

    assert sections.get("METHODS") == "Experimental details here."


def test_prepare_analysis_context_respects_char_limit():
    abstract = "Abstract text " + "A" * 30
    full_text = (
        "<article><body><sec><title>Methods</title>"
        f"<p>{'B' * 100}</p></sec></body></article>"
    )

    context = prepare_analysis_context(abstract, full_text, char_limit=80)

    assert len(context) <= 80
    assert context.startswith("ABSTRACT:")


def test_extract_year_full_pubdate():
    assert extract_year("2021-05-02") == 2021


def test_extract_year_year_only_pubdate():
    # NCBI's PubDate/Year element gives just the year, with nothing else.
    assert extract_year("2019") == 2019


def test_extract_year_missing_pubdate():
    # No PubDate element at all -> retriever passes through "".
    assert extract_year("") is None


def test_extract_year_unparseable_pubdate():
    # Some records have a season/range instead of a parseable date, e.g.
    # "Spring" with no year, or stray non-numeric text.
    assert extract_year("Spring") is None
    assert extract_year(None) is None
