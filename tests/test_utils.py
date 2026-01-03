"""
Tests for utility functions in app/utils/utils.py
"""
# Setup Python path before any imports
import sys
sys.path.insert(0, '/app')

import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from app.utils.utils import (  # noqa: E402
    create_cache_key,
    save_json,
    load_json,
    validate_pmid,
    get_sequencing_types,
    get_body_sites,
    format_prediction_output
)


class TestCacheKey:
    """Tests for create_cache_key function."""
    
    def test_create_cache_key_basic(self):
        """Test basic cache key creation."""
        result = create_cache_key("paper", "12345678")
        assert result == "paper_12345678"
    
    def test_create_cache_key_with_special_chars(self):
        """Test cache key with special characters in identifier."""
        result = create_cache_key("analysis", "test-id-123")
        assert result == "analysis_test-id-123"
    
    def test_create_cache_key_empty_prefix(self):
        """Test cache key with empty prefix."""
        result = create_cache_key("", "12345678")
        assert result == "_12345678"


class TestJSONOperations:
    """Tests for JSON save/load operations."""
    
    def test_save_and_load_json_simple(self):
        """Test saving and loading simple JSON data."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = Path(f.name)
        
        try:
            test_data = {"pmid": "12345678", "title": "Test Paper"}
            save_json(test_data, temp_path)
            
            loaded_data = load_json(temp_path)
            assert loaded_data == test_data
        finally:
            temp_path.unlink()
    
    def test_save_and_load_json_nested(self):
        """Test saving and loading nested JSON data."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = Path(f.name)
        
        try:
            test_data = {
                "pmid": "12345678",
                "fields": {
                    "host_species": {"value": "Human", "confidence": 0.95},
                    "body_site": {"value": "Gut", "confidence": 0.92}
                }
            }
            save_json(test_data, temp_path)
            
            loaded_data = load_json(temp_path)
            assert loaded_data == test_data
            assert loaded_data["fields"]["host_species"]["value"] == "Human"
        finally:
            temp_path.unlink()
    
    def test_save_json_unicode(self):
        """Test saving JSON with unicode characters."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = Path(f.name)
        
        try:
            test_data = {"title": "Microbiome Analysis: α-β diversity"}
            save_json(test_data, temp_path)
            
            loaded_data = load_json(temp_path)
            assert loaded_data == test_data
        finally:
            temp_path.unlink()


class TestPMIDValidation:
    """Tests for validate_pmid function."""
    
    def test_validate_pmid_valid(self):
        """Test validation of valid PMID."""
        assert validate_pmid("12345678") is True
        assert validate_pmid("31452104") is True
        assert validate_pmid("1") is True
    
    def test_validate_pmid_invalid(self):
        """Test validation of invalid PMID."""
        assert validate_pmid("abc123") is False
        assert validate_pmid("123-456") is False
        assert validate_pmid("") is False
        assert validate_pmid("PMID123") is False
    
    def test_validate_pmid_edge_cases(self):
        """Test edge cases for PMID validation."""
        assert validate_pmid("0") is True  # Edge case: single digit
        assert validate_pmid("12345678901234567890") is True  # Very long number


class TestSequencingTypes:
    """Tests for get_sequencing_types function."""
    
    def test_get_sequencing_types_returns_list(self):
        """Test that get_sequencing_types returns a list."""
        result = get_sequencing_types()
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_get_sequencing_types_contains_expected(self):
        """Test that expected sequencing types are present."""
        result = get_sequencing_types()
        assert "16S rRNA" in result
        assert "Shotgun metagenomics" in result
        assert "Metatranscriptomics" in result
    
    def test_get_sequencing_types_all_strings(self):
        """Test that all items in the list are strings."""
        result = get_sequencing_types()
        assert all(isinstance(item, str) for item in result)


class TestBodySites:
    """Tests for get_body_sites function."""
    
    def test_get_body_sites_returns_list(self):
        """Test that get_body_sites returns a list."""
        result = get_body_sites()
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_get_body_sites_contains_expected(self):
        """Test that expected body sites are present."""
        result = get_body_sites()
        assert "Gut" in result
        assert "Oral" in result
        assert "Skin" in result
    
    def test_get_body_sites_all_strings(self):
        """Test that all items in the list are strings."""
        result = get_body_sites()
        assert all(isinstance(item, str) for item in result)


class TestFormatPredictionOutput:
    """Tests for format_prediction_output function."""
    
    def test_format_prediction_output_basic(self):
        """Test basic prediction output formatting."""
        result = format_prediction_output(
            pmid="12345678",
            has_signature=True,
            signature_probability=0.95,
            sequencing_type="16S rRNA"
        )
        
        assert result["pmid"] == "12345678"
        assert result["has_signature"] is True
        assert result["signature_probability"] == 0.95
        assert result["sequencing_type"] == "16S rRNA"
    
    def test_format_prediction_output_with_metadata(self):
        """Test prediction output formatting with metadata."""
        metadata = {"field1": "value1", "field2": 42}
        result = format_prediction_output(
            pmid="12345678",
            has_signature=False,
            signature_probability=0.3,
            sequencing_type="Shotgun metagenomics",
            metadata=metadata
        )
        
        assert result["pmid"] == "12345678"
        assert result["has_signature"] is False
        assert result["signature_probability"] == 0.3
        assert result["sequencing_type"] == "Shotgun metagenomics"
        assert result["metadata"] == metadata
    
    def test_format_prediction_output_without_metadata(self):
        """Test prediction output formatting without metadata."""
        result = format_prediction_output(
            pmid="12345678",
            has_signature=True,
            signature_probability=0.8,
            sequencing_type="16S rRNA"
        )
        
        assert "metadata" not in result

