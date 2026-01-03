"""
Tests for field validation utilities in app/utils/field_validator.py

This test file works in both Docker and local environments without requiring
manual PYTHONPATH configuration. The conftest.py module handles path setup automatically.
"""

import pytest

from app.utils.field_validator import EnhancedFieldValidator, FieldExtractionEnhancer


class TestEnhancedFieldValidator:
    """Tests for EnhancedFieldValidator class."""

    def test_init(self):
        validator = EnhancedFieldValidator()
        assert validator.field_patterns is not None
        for field in [
            "host_species",
            "body_site",
            "condition",
            "sequencing_type",
            "taxa_level",
            "sample_size",
        ]:
            assert field in validator.field_patterns

    def test_validate_field_empty_value(self):
        validator = EnhancedFieldValidator()
        result = validator.validate_field("host_species", {"value": ""}, "")
        assert result["score"] == 0.0
        assert "No content extracted" in result["notes"]

    def test_validate_field_unknown_value(self):
        validator = EnhancedFieldValidator()
        result = validator.validate_field("host_species", {"value": "unknown"}, "")
        assert result["score"] == 0.0

    def test_validate_field_with_text(self):
        validator = EnhancedFieldValidator()
        test_cases = [
            ("host_species", {"value": "Human"}, "This study included 50 human participants with IBD."),
            ("host_species", {"value": "Mouse"}, "We used C57BL/6 mice in this experiment."),
            ("body_site", {"site": "Gut"}, "Fecal samples were collected from the gut microbiome."),
            ("body_site", {"site": "Oral"}, "Saliva samples were collected from the oral cavity."),
            ("sequencing_type", {"method": "16S rRNA"}, "We performed 16S rRNA sequencing using V4 region."),
            ("sequencing_type", {"method": "Shotgun metagenomics"}, "Whole genome shotgun metagenomics was performed."),
            ("condition", {"description": "IBD"}, "Patients with inflammatory bowel disease (IBD) were recruited."),
            (
                "taxa_level",
                {"level": "Genus"},
                "Analysis was performed at the genus level, including Bacteroides and Prevotella.",
            ),
            ("sample_size", {"size": "50"}, "A total of n=50 participants were included in this study."),
        ]

        for field, data, text in test_cases:
            result = validator.validate_field(field, data, text)
            assert result["score"] > 0.0
            assert "notes" in result

    def test_validate_field_without_text(self):
        validator = EnhancedFieldValidator()
        result = validator.validate_field("host_species", {"value": "Human"}, "")
        assert "score" in result
        assert "notes" in result

    def test_validate_field_invalid_field_name(self):
        validator = EnhancedFieldValidator()
        result = validator.validate_field("invalid_field", {"value": "Test"}, "Some text")
        assert "score" in result

    def test_check_pattern_match(self):
        validator = EnhancedFieldValidator()
        result = validator._check_pattern_match(
            "host_species", "Human", "This study included human patients and mouse models."
        )
        assert "confidence" in result and result["confidence"] > 0.0

        result = validator._check_pattern_match("body_site", "Gut", "Fecal samples from the gut were analyzed.")
        assert "confidence" in result

    def test_get_validation_notes(self):
        validator = EnhancedFieldValidator()
        notes_present = validator._get_validation_notes("host_species", "PRESENT", "Human", "Text")
        notes_partial = validator._get_validation_notes("host_species", "PARTIALLY_PRESENT", "Human", "Text")
        notes_absent = validator._get_validation_notes("host_species", "ABSENT", "", "Text")
        for notes in [notes_present, notes_partial, notes_absent]:
            assert isinstance(notes, str) and len(notes) > 0


class TestFieldExtractionEnhancer:
    """Tests for FieldExtractionEnhancer class."""

    def test_init(self):
        enhancer = FieldExtractionEnhancer()
        assert isinstance(enhancer.validator, EnhancedFieldValidator)

    def test_validate_field(self):
        enhancer = FieldExtractionEnhancer()
        result = enhancer.validate_field("host_species", {"value": "Human"})
        assert "score" in result and "notes" in result

    def test_enhance_extraction_various_cases(self):
        enhancer = FieldExtractionEnhancer()
        extracted_data = {"host_species": {"value": "Human"}, "body_site": {"site": "Gut"}}
        full_text = "This study included human participants. Fecal samples were collected from the gut."

        result = enhancer.enhance_extraction(extracted_data, full_text)
        for key in ["host_species", "body_site", "missing_fields", "curation_preparation_summary"]:
            assert key in result

        result_empty = enhancer.enhance_extraction({}, "Some text content.")
        for key in ["host_species", "body_site", "condition", "sequencing_type", "taxa_level", "sample_size"]:
            assert key in result_empty

    def test_create_default_field_structure(self):
        enhancer = FieldExtractionEnhancer()
        default = enhancer._create_default_field_structure("host_species")
        for key in ["primary", "confidence", "status", "reason_if_missing", "suggestions_for_curation"]:
            assert key in default
        assert default["status"] == "ABSENT"

    def test_generate_curation_summary(self):
        enhancer = FieldExtractionEnhancer()
        summaries = [
            enhancer._generate_curation_summary([]),
            enhancer._generate_curation_summary(["host_species"]),
            enhancer._generate_curation_summary(["host_species", "body_site", "condition"]),
            enhancer._generate_curation_summary(
                ["host_species", "body_site", "condition", "sequencing_type", "taxa_level"]
            ),
        ]
        for summary in summaries:
            assert isinstance(summary, str) and len(summary) > 0
