"""
Tests for field validation utilities in app/utils/field_validator.py
"""
import pytest
from app.utils.field_validator import (
    EnhancedFieldValidator,
    FieldExtractionEnhancer
)


class TestEnhancedFieldValidator:
    """Tests for EnhancedFieldValidator class."""
    
    def test_init(self):
        """Test validator initialization."""
        validator = EnhancedFieldValidator()
        assert validator.field_patterns is not None
        assert "host_species" in validator.field_patterns
        assert "body_site" in validator.field_patterns
        assert "condition" in validator.field_patterns
        assert "sequencing_type" in validator.field_patterns
        assert "taxa_level" in validator.field_patterns
        assert "sample_size" in validator.field_patterns
    
    def test_validate_field_empty_value(self):
        """Test validation with empty value."""
        validator = EnhancedFieldValidator()
        result = validator.validate_field(
            "host_species",
            {"value": ""},
            ""
        )
        assert result["score"] == 0.0
        assert "No content extracted" in result["notes"]
    
    def test_validate_field_unknown_value(self):
        """Test validation with 'unknown' value."""
        validator = EnhancedFieldValidator()
        result = validator.validate_field(
            "host_species",
            {"value": "unknown"},
            ""
        )
        assert result["score"] == 0.0
    
    def test_validate_field_host_species_human(self):
        """Test validation of host_species field with human."""
        validator = EnhancedFieldValidator()
        field_data = {"value": "Human"}
        text = "This study included 50 human participants with IBD."
        
        result = validator.validate_field("host_species", field_data, text)
        assert result["score"] > 0.0
        assert "score" in result
        assert "notes" in result
    
    def test_validate_field_host_species_mouse(self):
        """Test validation of host_species field with mouse."""
        validator = EnhancedFieldValidator()
        field_data = {"value": "Mouse"}
        text = "We used C57BL/6 mice in this experiment."
        
        result = validator.validate_field("host_species", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_body_site_gut(self):
        """Test validation of body_site field with gut."""
        validator = EnhancedFieldValidator()
        field_data = {"site": "Gut"}
        text = "Fecal samples were collected from the gut microbiome."
        
        result = validator.validate_field("body_site", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_body_site_oral(self):
        """Test validation of body_site field with oral."""
        validator = EnhancedFieldValidator()
        field_data = {"site": "Oral"}
        text = "Saliva samples were collected from the oral cavity."
        
        result = validator.validate_field("body_site", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_sequencing_type_16s(self):
        """Test validation of sequencing_type field with 16S."""
        validator = EnhancedFieldValidator()
        field_data = {"method": "16S rRNA"}
        text = "We performed 16S rRNA sequencing using V4 region."
        
        result = validator.validate_field("sequencing_type", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_sequencing_type_metagenomics(self):
        """Test validation of sequencing_type field with metagenomics."""
        validator = EnhancedFieldValidator()
        field_data = {"method": "Shotgun metagenomics"}
        text = "Whole genome shotgun metagenomics was performed."
        
        result = validator.validate_field("sequencing_type", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_condition_disease(self):
        """Test validation of condition field with disease."""
        validator = EnhancedFieldValidator()
        field_data = {"description": "IBD"}
        text = "Patients with inflammatory bowel disease (IBD) were recruited."
        
        result = validator.validate_field("condition", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_taxa_level_genus(self):
        """Test validation of taxa_level field with genus."""
        validator = EnhancedFieldValidator()
        field_data = {"level": "Genus"}
        text = "Analysis was performed at the genus level, including Bacteroides and Prevotella."
        
        result = validator.validate_field("taxa_level", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_sample_size_numeric(self):
        """Test validation of sample_size field with numeric value."""
        validator = EnhancedFieldValidator()
        field_data = {"size": "50"}
        text = "A total of n=50 participants were included in this study."
        
        result = validator.validate_field("sample_size", field_data, text)
        assert result["score"] > 0.0
    
    def test_validate_field_without_text(self):
        """Test validation without providing text content."""
        validator = EnhancedFieldValidator()
        field_data = {"value": "Human"}
        
        result = validator.validate_field("host_species", field_data, "")
        # Should still return a result, but with lower confidence
        assert "score" in result
        assert "notes" in result
    
    def test_validate_field_invalid_field_name(self):
        """Test validation with invalid field name."""
        validator = EnhancedFieldValidator()
        field_data = {"value": "Test"}
        
        result = validator.validate_field("invalid_field", field_data, "Some text")
        # Should handle gracefully
        assert "score" in result
    
    def test_check_pattern_match_host_species(self):
        """Test pattern matching for host_species."""
        validator = EnhancedFieldValidator()
        text = "This study included human patients and mouse models."
        content = "Human"
        
        result = validator._check_pattern_match("host_species", content, text)
        assert "confidence" in result
        assert result["confidence"] > 0.0
    
    def test_check_pattern_match_body_site(self):
        """Test pattern matching for body_site."""
        validator = EnhancedFieldValidator()
        text = "Fecal samples from the gut were analyzed."
        content = "Gut"
        
        result = validator._check_pattern_match("body_site", content, text)
        assert "confidence" in result
    
    def test_get_validation_notes_present(self):
        """Test validation notes for PRESENT status."""
        validator = EnhancedFieldValidator()
        notes = validator._get_validation_notes(
            "host_species",
            "PRESENT",
            "Human",
            "Text with human participants"
        )
        assert "complete" in notes.lower() or "matches" in notes.lower()
    
    def test_get_validation_notes_partially_present(self):
        """Test validation notes for PARTIALLY_PRESENT status."""
        validator = EnhancedFieldValidator()
        notes = validator._get_validation_notes(
            "host_species",
            "PARTIALLY_PRESENT",
            "Human",
            "Some text"
        )
        assert "partial" in notes.lower() or "consider" in notes.lower()
    
    def test_get_validation_notes_absent(self):
        """Test validation notes for ABSENT status."""
        validator = EnhancedFieldValidator()
        notes = validator._get_validation_notes(
            "host_species",
            "ABSENT",
            "",
            "Some text"
        )
        assert "no clear" in notes.lower() or "review" in notes.lower()


class TestFieldExtractionEnhancer:
    """Tests for FieldExtractionEnhancer class."""
    
    def test_init(self):
        """Test enhancer initialization."""
        enhancer = FieldExtractionEnhancer()
        assert enhancer.validator is not None
        assert isinstance(enhancer.validator, EnhancedFieldValidator)
    
    def test_validate_field(self):
        """Test field validation through enhancer."""
        enhancer = FieldExtractionEnhancer()
        field_data = {"value": "Human"}
        
        result = enhancer.validate_field("host_species", field_data)
        assert "score" in result
        assert "notes" in result
    
    def test_enhance_extraction_with_data(self):
        """Test enhancement with extracted data."""
        enhancer = FieldExtractionEnhancer()
        extracted_data = {
            "host_species": {"value": "Human"},
            "body_site": {"site": "Gut"}
        }
        full_text = "This study included human participants. Fecal samples were collected from the gut."
        
        result = enhancer.enhance_extraction(extracted_data, full_text)
        assert "host_species" in result
        assert "body_site" in result
        assert "missing_fields" in result
        assert "curation_preparation_summary" in result
    
    def test_enhance_extraction_empty_data(self):
        """Test enhancement with empty extracted data."""
        enhancer = FieldExtractionEnhancer()
        extracted_data = {}
        full_text = "Some text content."
        
        result = enhancer.enhance_extraction(extracted_data, full_text)
        # Should create default structures for all fields
        assert "host_species" in result
        assert "body_site" in result
        assert "condition" in result
        assert "sequencing_type" in result
        assert "taxa_level" in result
        assert "sample_size" in result
    
    def test_enhance_extraction_missing_fields(self):
        """Test that missing fields are identified correctly."""
        enhancer = FieldExtractionEnhancer()
        extracted_data = {
            "host_species": {"value": "Human"},
            # Missing other fields
        }
        full_text = "Human participants were studied."
        
        result = enhancer.enhance_extraction(extracted_data, full_text)
        assert "missing_fields" in result
        assert isinstance(result["missing_fields"], list)
    
    def test_enhance_extraction_curation_summary(self):
        """Test that curation summary is generated."""
        enhancer = FieldExtractionEnhancer()
        extracted_data = {
            "host_species": {"value": "Human"}
        }
        full_text = "Human participants."
        
        result = enhancer.enhance_extraction(extracted_data, full_text)
        assert "curation_preparation_summary" in result
        assert isinstance(result["curation_preparation_summary"], str)
        assert len(result["curation_preparation_summary"]) > 0
    
    def test_create_default_field_structure(self):
        """Test creation of default field structure."""
        enhancer = FieldExtractionEnhancer()
        
        result = enhancer._create_default_field_structure("host_species")
        assert "primary" in result or "value" in result
        assert "confidence" in result
        assert "status" in result
        assert result["status"] == "ABSENT"
    
    def test_generate_curation_summary_no_missing(self):
        """Test curation summary with no missing fields."""
        enhancer = FieldExtractionEnhancer()
        result = enhancer._generate_curation_summary([])
        assert "ready" in result.lower() or "present" in result.lower()
    
    def test_generate_curation_summary_one_missing(self):
        """Test curation summary with one missing field."""
        enhancer = FieldExtractionEnhancer()
        result = enhancer._generate_curation_summary(["host_species"])
        assert "1 field" in result.lower() or "missing" in result.lower()
    
    def test_generate_curation_summary_multiple_missing(self):
        """Test curation summary with multiple missing fields."""
        enhancer = FieldExtractionEnhancer()
        result = enhancer._generate_curation_summary(["host_species", "body_site", "condition"])
        assert "3 fields" in result.lower() or "missing" in result.lower()
    
    def test_generate_curation_summary_many_missing(self):
        """Test curation summary with many missing fields."""
        enhancer = FieldExtractionEnhancer()
        missing = ["host_species", "body_site", "condition", "sequencing_type", "taxa_level"]
        result = enhancer._generate_curation_summary(missing)
        assert "significant" in result.lower() or "review" in result.lower()

