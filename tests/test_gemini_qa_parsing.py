"""Characterization tests for GeminiQA.parse_enhanced_analysis().

GeminiQA.__init__ calls genai.configure()/genai.list_models() (a real
network call to Google, swallowed by a try/except in the constructor but
still attempted). Tests monkeypatch those before constructing an instance,
mirroring the requests.get monkeypatch pattern in tests/test_cli_health.py.
parse_enhanced_analysis() itself never references `self`, so this is purely
about avoiding the network call at construction time.
"""

import pytest
import google.generativeai as genai

from app.models.gemini_qa import GeminiQA


@pytest.fixture
def qa(monkeypatch):
    monkeypatch.setattr(genai, "configure", lambda **kwargs: None)
    monkeypatch.setattr(genai, "list_models", lambda: [])
    return GeminiQA(api_key="fake-key-for-tests")


READY_RESPONSE = """
**CURATION READINESS ASSESSMENT:**
READY FOR CURATION

**DETAILED EXPLANATION:**
The paper reports differential abundance of gut microbiota.
It includes 16S sequencing data across two cohorts.

**FACTOR-BASED ANALYSIS:**
- General Factors Present: microbial taxa identification, abundance data
- Human/Animal Factors Present: human cohort
- Environmental Factors Present: diet
- Missing Critical Factors: statistical power

**MICROBIAL SIGNATURE ANALYSIS:**
- Presence of microbial signatures: Yes
- Types of signatures found: differential abundance, community composition
- Quality of signature data: High
- Statistical significance: Yes

**CURATABLE CONTENT ASSESSMENT:**
- Missing required fields: none
- Data completeness: Complete

**SPECIFIC REASONS FOR READINESS/NON-READINESS:**
- Contains specific microbial taxa identification
- Includes quantitative abundance data

**CONFIDENCE LEVEL:**
0.92

**EXAMPLES AND EVIDENCE:**
- Table 2 lists differentially abundant genera
- Figure 3 shows community composition shifts
"""

NOT_READY_RESPONSE = """
**CURATION READINESS ASSESSMENT:**
NOT READY FOR CURATION

**DETAILED EXPLANATION:**
The paper only mentions "microbiome" in passing and has no sequencing data.

**FACTOR-BASED ANALYSIS:**
- General Factors Present:
- Human/Animal Factors Present:
- Environmental Factors Present:
- Missing Critical Factors: microbial taxa identification, abundance data

**MICROBIAL SIGNATURE ANALYSIS:**
- Presence of microbial signatures: No
- Types of signatures found:
- Quality of signature data: Low
- Statistical significance: Insufficient

**CURATABLE CONTENT ASSESSMENT:**
- Missing required fields: sequencing data, taxa identification
- Data completeness: Insufficient

**SPECIFIC REASONS FOR READINESS/NON-READINESS:**
- No quantitative or qualitative microbial data
- Purely a narrative review

**CONFIDENCE LEVEL:**
0.81

**EXAMPLES AND EVIDENCE:**
"""


def test_ready_response_classified_as_ready(qa):
    result = qa.parse_enhanced_analysis(READY_RESPONSE)
    assert result["readiness"] == "READY"
    assert "differential abundance" in result["explanation"]
    assert result["microbial_signatures"] == "Present"
    assert result["signature_types"] == [
        "differential abundance",
        "community composition",
    ]
    assert result["data_quality"] == "High"
    assert result["statistical_significance"] == "Yes"
    assert result["data_completeness"] == "Complete"
    assert result["confidence"] == 0.92
    assert result["specific_reasons"] == [
        "Contains specific microbial taxa identification",
        "Includes quantitative abundance data",
    ]
    assert result["examples"] == [
        "Table 2 lists differentially abundant genera",
        "Figure 3 shows community composition shifts",
    ]


def test_not_ready_response_classified_as_not_ready(qa):
    """Regression test: 'NOT READY FOR CURATION' must not be misread as READY.

    'READY FOR CURATION' is a substring of 'NOT READY FOR CURATION', so a
    naive ordering of the if/elif checks previously matched the bare READY
    branch first and silently flipped every correctly-formatted 'not ready'
    verdict to 'READY'.
    """
    result = qa.parse_enhanced_analysis(NOT_READY_RESPONSE)
    assert result["readiness"] == "NOT_READY"
    assert result["microbial_signatures"] == "Absent"
    assert result["data_quality"] == "Low"
    assert result["statistical_significance"] == "Insufficient"
    assert result["data_completeness"] == "Insufficient"
    assert result["missing_fields"] == ["sequencing data", "taxa identification"]
    assert result["confidence"] == 0.81


@pytest.mark.parametrize(
    "line, expected",
    [
        ("READY FOR CURATION", "READY"),
        ("NOT READY FOR CURATION", "NOT_READY"),
        ("This paper is NOT READY for further review", "NOT_READY"),
        ("This paper is READY for curation", "READY"),
        ("Readiness is UNCLEAR at this time", "UNKNOWN"),
        ("UNKNOWN - insufficient information", "UNKNOWN"),
    ],
)
def test_readiness_line_variants(qa, line, expected):
    text = f"**CURATION READINESS ASSESSMENT:**\n{line}\n"
    result = qa.parse_enhanced_analysis(text)
    assert result["readiness"] == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Complete", "Complete"),
        ("Partial", "Partial"),
        ("Insufficient", "Insufficient"),
    ],
)
def test_data_completeness_line_variants(qa, value, expected):
    """Regression test: the label 'Data completeness:' contains the
    substring 'complete' (from 'completeness'), so checking the whole line
    for that keyword previously matched every value as 'Complete'
    regardless of what was actually reported."""
    text = f"**CURATABLE CONTENT ASSESSMENT:**\n- Data completeness: {value}\n"
    result = qa.parse_enhanced_analysis(text)
    assert result["data_completeness"] == expected


def test_factor_based_score_computation(qa):
    text = """
**FACTOR-BASED ANALYSIS:**
- General Factors Present: a, b, c
- Human/Animal Factors Present: d
- Environmental Factors Present: e, f
- Missing Critical Factors: g
"""
    result = qa.parse_enhanced_analysis(text)
    # total_factors = 3 + 1 + 2 = 6; max_factors = 16
    assert result["general_factors_present"] == ["a", "b", "c"]
    assert result["human_animal_factors_present"] == ["d"]
    assert result["environmental_factors_present"] == ["e", "f"]
    assert result["missing_critical_factors"] == ["g"]
    assert result["factor_based_score"] == pytest.approx(6 / 16)


def test_factor_based_score_caps_at_one(qa):
    many = ", ".join(f"factor{i}" for i in range(20))
    text = f"""
**FACTOR-BASED ANALYSIS:**
- General Factors Present: {many}
"""
    result = qa.parse_enhanced_analysis(text)
    assert result["factor_based_score"] == 1.0


def test_empty_input_returns_defaults(qa):
    result = qa.parse_enhanced_analysis("")
    assert result["readiness"] == "UNKNOWN"
    assert result["explanation"] == ""
    assert result["confidence"] == 0.0
    assert result["factor_based_score"] == 0.0


def test_exception_during_parsing_returns_error_dict(qa, monkeypatch):
    """A non-string input can't be .split()'d - parse_enhanced_analysis
    must catch that and return its structured ERROR fallback rather than
    raising, so callers always get a dict back."""
    result = qa.parse_enhanced_analysis(None)
    assert result["readiness"] == "ERROR"
    assert "Error parsing analysis" in result["explanation"]
    assert result["confidence"] == 0.0
    assert result["factor_based_score"] == 0.0
