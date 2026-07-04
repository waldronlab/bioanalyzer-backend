from app.normalization.grounding import TIER_AUTO, TIER_NONE, TIER_REVIEW, tier_for
from app.normalization.types import NormalizedTerm


def test_tier_none_when_no_ontology_id():
    term = NormalizedTerm(
        label="stool",
        ontology_id="",
        status="PARTIALLY_PRESENT",
        mapping_confidence=0.5,
    )
    assert tier_for(term) == TIER_NONE


def test_tier_auto_for_full_confidence_present_match():
    term = NormalizedTerm(
        label="Homo sapiens",
        ontology_id="NCBITaxon:9606",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    assert tier_for(term) == TIER_AUTO


def test_tier_review_for_partial_confidence_match():
    term = NormalizedTerm(
        label="Mus musculus",
        ontology_id="NCBITaxon:10090",
        status="PARTIALLY_PRESENT",
        mapping_confidence=0.9,
    )
    assert tier_for(term) == TIER_REVIEW


def test_tier_review_for_live_lookup_match():
    term = NormalizedTerm(
        label="duodenum",
        ontology_id="UBERON:0002114",
        status="PRESENT",
        mapping_confidence=0.9,
    )
    assert tier_for(term) == TIER_REVIEW
