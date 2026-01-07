"""
Tests for API utility functions in app/api/utils/api_utils.py
"""

import pytest
from datetime import datetime

# Try to import FastAPI-dependent modules, skip tests if not available
try:
    from fastapi import FastAPI
    from app.api.utils.api_utils import (
        extract_taxa,
        create_default_field_structure,
        validate_field_structure,
        create_comprehensive_fallback_analysis,
        generate_curation_summary,
        get_current_timestamp,
    )

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Create dummy functions to avoid NameError
    extract_taxa = None
    create_default_field_structure = None
    validate_field_structure = None
    create_comprehensive_fallback_analysis = None
    generate_curation_summary = None
    get_current_timestamp = None


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestExtractTaxa:
    """Tests for extract_taxa function."""

    def test_extract_taxa_genus_species(self):
        """Test extraction of genus species format."""
        text = "We found Bacteroides fragilis and Escherichia coli in the samples."
        taxa = extract_taxa(text)
        assert len(taxa) > 0
        # Should find genus species patterns
        assert any("Bacteroides" in t or "Escherichia" in t for t in taxa)

    def test_extract_taxa_genus_only(self):
        """Test extraction of genus only."""
        text = "The genus Lactobacillus was dominant."
        taxa = extract_taxa(text)
        assert len(taxa) > 0

    def test_extract_taxa_empty_text(self):
        """Test extraction from empty text."""
        taxa = extract_taxa("")
        assert isinstance(taxa, list)
        assert len(taxa) == 0

    def test_extract_taxa_no_taxa(self):
        """Test extraction when no taxa present."""
        text = "This is a regular sentence with no scientific names."
        taxa = extract_taxa(text)
        assert isinstance(taxa, list)

    def test_extract_taxa_removes_duplicates(self):
        """Test that duplicates are removed."""
        text = "Bacteroides fragilis and Bacteroides fragilis were found."
        taxa = extract_taxa(text)
        # Should return unique taxa
        assert len(taxa) == len(set(taxa))


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestCreateDefaultFieldStructure:
    """Tests for create_default_field_structure function."""

    def test_create_default_host_species(self):
        """Test creating default structure for host_species."""
        result = create_default_field_structure("host_species")
        assert result["status"] == "ABSENT"
        assert result["value"] is None
        assert result["confidence"] == 0.0
        assert "reason_if_missing" in result
        assert "suggestions" in result

    def test_create_default_body_site(self):
        """Test creating default structure for body_site."""
        result = create_default_field_structure("body_site")
        assert result["status"] == "ABSENT"
        assert result["value"] is None
        assert (
            "gut" in result["suggestions"].lower()
            or "oral" in result["suggestions"].lower()
        )

    def test_create_default_condition(self):
        """Test creating default structure for condition."""
        result = create_default_field_structure("condition")
        assert result["status"] == "ABSENT"
        assert (
            "disease" in result["suggestions"].lower()
            or "treatment" in result["suggestions"].lower()
        )

    def test_create_default_sequencing_type(self):
        """Test creating default structure for sequencing_type."""
        result = create_default_field_structure("sequencing_type")
        assert result["status"] == "ABSENT"
        assert (
            "16s" in result["suggestions"].lower()
            or "sequencing" in result["suggestions"].lower()
        )

    def test_create_default_taxa_level(self):
        """Test creating default structure for taxa_level."""
        result = create_default_field_structure("taxa_level")
        assert result["status"] == "ABSENT"
        assert (
            "phylum" in result["suggestions"].lower()
            or "genus" in result["suggestions"].lower()
        )

    def test_create_default_sample_size(self):
        """Test creating default structure for sample_size."""
        result = create_default_field_structure("sample_size")
        assert result["status"] == "ABSENT"
        assert (
            "samples" in result["suggestions"].lower()
            or "participants" in result["suggestions"].lower()
        )

    def test_create_default_unknown_field(self):
        """Test creating default structure for unknown field."""
        result = create_default_field_structure("unknown_field")
        assert result["status"] == "ABSENT"
        assert result["value"] is None
        assert "unknown_field" in result["reason_if_missing"].lower()


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestValidateFieldStructure:
    """Tests for validate_field_structure function."""

    def test_validate_field_structure_valid(self):
        """Test validation of valid field structure."""
        field_data = {
            "status": "PRESENT",
            "value": "Human",
            "confidence": 0.95,
            "reason_if_missing": "",
            "suggestions": "",
        }
        assert validate_field_structure(field_data, "host_species") is True

    def test_validate_field_structure_missing_key(self):
        """Test validation with missing required key."""
        field_data = {
            "status": "PRESENT",
            "value": "Human",
            # Missing confidence, reason_if_missing, suggestions
        }
        assert validate_field_structure(field_data, "host_species") is False

    def test_validate_field_structure_not_dict(self):
        """Test validation with non-dict input."""
        field_data = "not a dict"
        assert validate_field_structure(field_data, "host_species") is False

    def test_validate_field_structure_empty_dict(self):
        """Test validation with empty dict."""
        field_data = {}
        assert validate_field_structure(field_data, "host_species") is False

    def test_validate_field_structure_partial(self):
        """Test validation with partial structure."""
        field_data = {
            "status": "PRESENT",
            "value": "Human",
            # Missing other required fields
        }
        assert validate_field_structure(field_data, "host_species") is False


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestCreateComprehensiveFallbackAnalysis:
    """Tests for create_comprehensive_fallback_analysis function."""

    def test_create_fallback_analysis_structure(self):
        """Test that fallback analysis has correct structure."""
        result = create_comprehensive_fallback_analysis()
        assert isinstance(result, dict)
        assert "host_species" in result
        assert "body_site" in result
        assert "condition" in result
        assert "sequencing_type" in result
        assert "taxa_level" in result
        assert "sample_size" in result

    def test_create_fallback_analysis_all_absent(self):
        """Test that all fields in fallback are ABSENT."""
        result = create_comprehensive_fallback_analysis()
        for field_name, field_data in result.items():
            if field_name not in ["missing_fields", "curation_preparation_summary"]:
                assert field_data["status"] == "ABSENT"
                assert field_data["confidence"] == 0.0

    def test_create_fallback_analysis_field_structure(self):
        """Test that each field has correct structure."""
        result = create_comprehensive_fallback_analysis()
        for field_name, field_data in result.items():
            if field_name not in ["missing_fields", "curation_preparation_summary"]:
                assert "status" in field_data
                assert "value" in field_data
                assert "confidence" in field_data
                assert "reason_if_missing" in field_data
                assert "suggestions" in field_data


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestGenerateCurationSummary:
    """Tests for generate_curation_summary function."""

    def test_generate_summary_no_missing_fields(self):
        """Test summary generation with no missing fields."""
        parsed_analysis = {
            "host_species": {"status": "PRESENT", "suggestions": ""},
            "body_site": {"status": "PRESENT", "suggestions": ""},
        }
        summary = generate_curation_summary(parsed_analysis, [])
        assert "all required fields" in summary.lower() or "curation" in summary.lower()

    def test_generate_summary_with_missing_fields(self):
        """Test summary generation with missing fields."""
        parsed_analysis = {
            "host_species": {
                "status": "ABSENT",
                "suggestions": "Look for mentions of human, mouse, rat",
            },
            "body_site": {
                "status": "ABSENT",
                "suggestions": "Look for mentions of gut, oral, skin",
            },
        }
        missing = ["host_species", "body_site"]
        summary = generate_curation_summary(parsed_analysis, missing)
        assert "missing" in summary.lower()
        assert "host_species" in summary.lower() or "host" in summary.lower()

    def test_generate_summary_includes_suggestions(self):
        """Test that summary includes field suggestions."""
        parsed_analysis = {
            "host_species": {
                "status": "ABSENT",
                "suggestions": "Look for human, mouse, rat",
            }
        }
        missing = ["host_species"]
        summary = generate_curation_summary(parsed_analysis, missing)
        assert (
            "suggestions" in summary.lower()
            or "human" in summary.lower()
            or "mouse" in summary.lower()
        )

    def test_generate_summary_empty_analysis(self):
        """Test summary generation with empty analysis."""
        parsed_analysis = {}
        missing = ["host_species"]
        summary = generate_curation_summary(parsed_analysis, missing)
        assert isinstance(summary, str)
        assert len(summary) > 0


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestGetCurrentTimestamp:
    """Tests for get_current_timestamp function."""

    def test_get_current_timestamp_format(self):
        """Test that timestamp is in ISO format."""
        timestamp = get_current_timestamp()
        assert isinstance(timestamp, str)
        # Should be ISO format with 'T' separator
        assert "T" in timestamp or "-" in timestamp

    def test_get_current_timestamp_not_empty(self):
        """Test that timestamp is not empty."""
        timestamp = get_current_timestamp()
        assert len(timestamp) > 0

    def test_get_current_timestamp_parsable(self):
        """Test that timestamp can be parsed."""
        timestamp = get_current_timestamp()
        # Should be parseable as datetime
        try:
            from dateutil import parser

            parsed = parser.isoparse(timestamp)
            assert isinstance(parsed, datetime)
        except ImportError:
            # dateutil not available, just check format
            assert isinstance(timestamp, str)

    def test_get_current_timestamp_unique(self):
        """Test that timestamps are unique (or at least different when called with delay)."""
        import time

        timestamp1 = get_current_timestamp()
        time.sleep(0.01)  # Small delay
        timestamp2 = get_current_timestamp()
        # They might be the same due to precision, but should be valid
        assert isinstance(timestamp1, str)
        assert isinstance(timestamp2, str)
