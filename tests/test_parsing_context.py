"""Section classification and context budgeting (parsing.py).

The LLM used to see at most 8,000 characters, with Methods capped at 3,000
and headings like "Participants"/"Study population" filed under OTHER
(400 chars) - so the cohort description that decides Host Species, Body
Site, Condition and Sample Size usually never reached the model."""

import pytest

pytest.importorskip("defusedxml")

from app.services.bugsigdb_analyzer import parsing
from app.services.bugsigdb_analyzer.parsing import (
    _classify_section_title,
    _parse_pmc_sections,
    prepare_analysis_context,
)


class TestMethodsHeadings:
    @pytest.mark.parametrize(
        "title",
        [
            "Participants",
            "Subjects",
            "Study population",
            "Study design",
            "Study Design and Participants",
            "Cohort description",
            "Enrolment",
            "Enrollment and eligibility",
            "Patient recruitment",
            "Recruitment",
            "Sample collection",
            "Sample collection and DNA extraction",
            "Ethics statement",
            "Ethical approval",
            "Materials and Methods",
            "Statistical analysis",
        ],
    )
    def test_population_and_design_headings_are_methods(self, title):
        assert _classify_section_title(title) == "METHODS"

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Results", "RESULTS"),
            ("Results and Discussion", "RESULTS"),
            ("Main findings", "RESULTS"),
            ("Discussion", "DISCUSSION"),
            ("Conclusions", "DISCUSSION"),
            ("Introduction", "INTRODUCTION"),
            ("Background", "INTRODUCTION"),
            ("Abstract", "ABSTRACT"),
            ("Acknowledgements", "OTHER"),
            ("Funding", "OTHER"),
            ("Author contributions", "OTHER"),
        ],
    )
    def test_other_headings_unchanged(self, title, expected):
        assert _classify_section_title(title) == expected


class TestSupplementaryOrdering:
    def test_supplementary_material_is_not_methods(self):
        # "Supplementary Material" contains "material"; it must not consume
        # the Methods budget with media stubs.
        assert _classify_section_title("Supplementary Material") == "SUPPLEMENTARY"
        assert _classify_section_title("Supplemental Data") == "SUPPLEMENTARY"
        assert _classify_section_title("Appendix A") == "SUPPLEMENTARY"

    def test_supplementation_sections_are_not_supplementary(self):
        # A real Methods subsection in microbiome papers must not be swept
        # into SUPPLEMENTARY by a loose "supplement" match.
        assert _classify_section_title("Probiotic supplementation") != "SUPPLEMENTARY"
        assert _classify_section_title("Dietary supplementation protocol") == "METHODS"


class TestBudgets:
    def test_context_limit_and_section_budgets(self):
        assert parsing._CONTEXT_CHAR_LIMIT >= 24_000
        b = parsing._SECTION_BUDGETS
        assert b["METHODS"] >= 9_000
        assert b["RESULTS"] >= 6_000
        assert b["ABSTRACT"] >= 2_500
        assert b["FULL_TEXT"] >= 20_000
        # Everything the ordered sections can take still fits the limit.
        ordered = ("ABSTRACT", "METHODS", "RESULTS", "INTRODUCTION", "DISCUSSION")
        assert sum(b[k] for k in ordered) <= parsing._CONTEXT_CHAR_LIMIT

    def test_long_methods_section_reaches_the_model(self):
        methods = ("We enrolled participants with IBD. " * 400).strip()  # ~14k chars
        assert len(methods) > 9_000
        xml = (
            "<article><body>"
            "<sec><title>Participants</title>"
            f"<p>{methods}</p></sec>"
            "</body></article>"
        )
        context = prepare_analysis_context("Short abstract.", xml)
        methods_part = context.split("METHODS:\n", 1)[1]
        # Far more than the old 400-char OTHER budget / 3,000-char METHODS cap.
        assert len(methods_part) >= 8_500
        assert methods_part.endswith("[truncated]")

    def test_abstract_then_methods_lead_the_context(self):
        xml = (
            "<article><body>"
            "<sec><title>Introduction</title><p>Intro text.</p></sec>"
            "<sec><title>Results</title><p>Results text.</p></sec>"
            "<sec><title>Study population</title><p>Cohort text.</p></sec>"
            "<sec><title>Discussion</title><p>Discussion text.</p></sec>"
            "</body></article>"
        )
        context = prepare_analysis_context("An abstract.", xml)
        order = [
            context.index("ABSTRACT:"),
            context.index("METHODS:"),
            context.index("RESULTS:"),
            context.index("INTRODUCTION:"),
            context.index("DISCUSSION:"),
        ]
        assert order == sorted(order)
        assert "Cohort text." in context

    def test_total_context_respects_limit(self):
        big = ("x" * 99 + " ") * 400  # 40k chars
        xml = (
            "<article><body>"
            f"<sec><title>Methods</title><p>{big}</p></sec>"
            f"<sec><title>Results</title><p>{big}</p></sec>"
            f"<sec><title>Discussion</title><p>{big}</p></sec>"
            "</body></article>"
        )
        context = prepare_analysis_context("abstract", xml)
        assert len(context) <= parsing._CONTEXT_CHAR_LIMIT

    def test_unsectioned_full_text_gets_large_budget(self):
        body = ("Plain text paragraph about 30 patients. " * 600).strip()
        context = prepare_analysis_context("abstract", body)
        assert "FULL_TEXT:" in context
        assert len(context) > 15_000


def test_labelled_text_uses_new_methods_headings():
    text = "Participants: Forty adults were recruited.\nResults: Alpha diversity fell."
    sections = _parse_pmc_sections(text)
    assert sections["METHODS"] == "Forty adults were recruited."
    assert sections["RESULTS"] == "Alpha diversity fell."
