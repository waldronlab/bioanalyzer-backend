"""PubMed-only extraction inputs: full abstract text, MeSH/keywords, title-only fallback."""

from unittest.mock import Mock

import pytest

from app.services.bugsigdb_analyzer.parsing import (
    build_analysis_text,
    format_index_terms,
)
from app.services.data_retrieval import PubMedRetriever

_PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation>
  <PMID>1</PMID>
  <Article>
    <Journal><Title>Gut Microbes</Title>
      <JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
    <ArticleTitle>Faecal <i>Bacteroides</i> in children</ArticleTitle>
    <Abstract>
      <AbstractText Label="BACKGROUND">Background sentence.</AbstractText>
      <AbstractText Label="METHODS">We sampled <i>Homo sapiens</i> stool from 40 children.</AbstractText>
      <AbstractText Label="UNLABELLED">Plain part.</AbstractText>
    </Abstract>
  </Article>
  <MeshHeadingList>
    <MeshHeading><DescriptorName MajorTopicYN="N">Humans</DescriptorName></MeshHeading>
    <MeshHeading><DescriptorName MajorTopicYN="Y">Gastrointestinal Microbiome</DescriptorName></MeshHeading>
    <MeshHeading>
      <DescriptorName MajorTopicYN="N">RNA, Ribosomal, 16S</DescriptorName>
      <QualifierName MajorTopicYN="Y">genetics</QualifierName>
    </MeshHeading>
  </MeshHeadingList>
  <KeywordList><Keyword>microbiome</Keyword><Keyword> </Keyword></KeywordList>
</MedlineCitation></PubmedArticle></PubmedArticleSet>
"""


@pytest.fixture
def metadata():
    retriever = PubMedRetriever.__new__(PubMedRetriever)
    retriever._make_request = Mock(return_value=_PUBMED_XML)
    return retriever.fetch_paper_metadata("1")


def test_abstract_keeps_text_after_inline_tags_and_section_labels(metadata):
    assert metadata["abstract"] == (
        "BACKGROUND: Background sentence.\n"
        "METHODS: We sampled Homo sapiens stool from 40 children.\n"
        "Plain part."
    )


def test_title_keeps_text_after_inline_tags(metadata):
    assert metadata["title"] == "Faecal Bacteroides in children"


def test_mesh_terms_mark_major_topics(metadata):
    assert metadata["mesh_terms"] == [
        "Humans",
        "Gastrointestinal Microbiome*",
        "RNA, Ribosomal, 16S*",
    ]


def test_keywords_skip_blank_entries(metadata):
    assert metadata["keywords"] == ["microbiome"]


def test_format_index_terms_labels_each_block():
    assert format_index_terms(["Humans", "Feces"], ["gut"]) == (
        "MESH TERMS:\nHumans; Feces\n\nKEYWORDS:\ngut"
    )
    assert format_index_terms([], None) == ""


def test_build_analysis_text_appends_index_terms_after_abstract():
    text = build_analysis_text(
        "Title", "An abstract.", "", mesh_terms=["Humans"], keywords=["gut"]
    )
    assert text == "ABSTRACT:\nAn abstract.\n\nMESH TERMS:\nHumans\n\nKEYWORDS:\ngut"


def test_build_analysis_text_can_leave_index_terms_out():
    text = build_analysis_text(
        "Title",
        "An abstract.",
        "",
        mesh_terms=["Humans"],
        include_index_terms=False,
    )
    assert text == "ABSTRACT:\nAn abstract."


def test_build_analysis_text_falls_back_to_title_without_abstract():
    text = build_analysis_text(
        "Skin microbiome in paediatric eczema", "", "", mesh_terms=["Child"]
    )
    assert text.startswith(
        "TITLE ONLY (no abstract in PubMed):\nSkin microbiome in paediatric eczema"
    )
    assert text.endswith("MESH TERMS:\nChild")


@pytest.mark.parametrize("title", ["", "  ", "N/A"])
def test_build_analysis_text_is_empty_without_any_text(title):
    assert build_analysis_text(title, "", "", mesh_terms=["Humans"]) == ""
