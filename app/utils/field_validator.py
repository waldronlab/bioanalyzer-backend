"""
Enhanced Field Validation and Extraction Utilities

This module provides comprehensive validation and extraction utilities for the 6 essential BugSigDB curation fields.
It ensures consistent field structure and improves extraction accuracy.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class FieldValidationResult:
    """Result of field validation."""
    is_valid: bool
    confidence: float
    status: str
    extracted_value: str
    reason_if_missing: str
    suggestions_for_curation: str

class EnhancedFieldValidator:
    """Enhanced field validator for BugSigDB curation fields."""
    
    def __init__(self):
        # Define field-specific validation patterns
        self.field_patterns = {
            "host_species": {
                "human": [r"human", r"patients?", r"participants?", r"subjects?", r"volunteers?"],
                "mouse": [r"mouse", r"mice", r"murine", r"c57bl", r"balb/c"],
                "rat": [r"rat", r"rats", r"rattus"],
                "environmental": [r"environmental?", r"environment", r"indoor", r"outdoor", r"built environment", r"natural environment"],
                "mixed": [r"mixed", r"combination", r"both human and"]
            },
            "body_site": {
                "gut": [r"gut", r"intestine", r"intestinal", r"stool", r"feces", r"fecal", r"colon"],
                "oral": [r"oral", r"mouth", r"saliva", r"dental", r"tooth", r"teeth", r"tongue"],
                "skin": [r"skin", r"cutaneous", r"dermal", r"epidermal"],
                "vaginal": [r"vaginal", r"vagina", r"cervical", r"cervix"],
                "lung": [r"lung", r"respiratory", r"airway", r"bronchial"],
                "indoor": [r"indoor", r"building", r"room", r"office", r"home", r"restroom", r"bathroom", r"hospital", r"school"],
                "outdoor": [r"outdoor", r"soil", r"air", r"water", r"surface"]
            },
            "condition": {
                "disease": [r"ibd", r"crohn", r"ulcerative colitis", r"obesity", r"diabetes", r"cancer", r"tumor"],
                "treatment": [r"antibiotic", r"treatment", r"intervention", r"therapy"],
                "comparative": [r"men vs women", r"healthy vs", r"before vs after", r"control vs", r"comparison"],
                "environmental": [r"seasonal", r"temporal", r"spatial", r"geographic", r"climatic"]
            },
            "sequencing_type": {
                "16s": [r"16s", r"16s rrna", r"16s ribosomal", r"v4", r"v3-v4", r"amplicon"],
                "metagenomics": [r"metagenomic", r"metagenomics", r"shotgun", r"whole genome", r"wgs"],
                "metatranscriptomics": [r"metatranscriptomic", r"metatranscriptomics", r"rna-seq", r"transcriptome"],
                "other": [r"sequencing", r"next-generation", r"ngs", r"illumina", r"pacbio"]
            },
            "taxa_level": {
                "phylum": [r"phylum", r"phyla", r"proteobacteria", r"actinobacteria", r"bacteroidetes", r"firmicutes"],
                "genus": [r"genus", r"genera", r"bacteroides", r"prevotella", r"lactobacillus", r"bifidobacterium"],
                "species": [r"species", r"e\. coli", r"b\. fragilis", r"l\. acidophilus", r"b\. longum"],
                "family": [r"family", r"families", r"enterobacteriaceae", r"lactobacillaceae", r"bifidobacteriaceae"]
            },
            "sample_size": {
                "numeric": [r"n\s*=\s*\d+", r"\d+\s*participants?", r"\d+\s*samples?", r"\d+\s*subjects?"],
                "descriptive": [r"multiple", r"several", r"various", r"different", r"longitudinal", r"time points?"]
            }
        }
        
        # Define confidence thresholds
        self.confidence_thresholds = {
            "PRESENT": (0.8, 1.0),
            "PARTIALLY_PRESENT": (0.4, 0.7),
            "ABSENT": (0.0, 0.3)
        }
    
    def validate_field(self, field_name: str, field_data: Dict, text: Optional[str] = '') -> Dict:
        """
        Validate a specific field based on extracted data and optional text content.
        
        Args:
            field_name: Name of the field to validate
            field_data: Data extracted by the LLM for this field
            text: Optional full text content for validation
            
        Returns:
            Dict with validation details: {'score': float, 'notes': str}
        """
        try:
            # Get the content value for the field
            content_value = field_data.get('value', '') or field_data.get('primary', '') or field_data.get('site', '') or ''
            
            if not content_value or content_value.lower() in ["unknown", "not specified", ""]:
                return {'score': 0.0, 'notes': "No content extracted"}
            
            # Validate against patterns if text provided
            pattern_match = self._check_pattern_match(field_name, content_value, text) if text else {'confidence': 0.5}
            
            if pattern_match["confidence"] >= 0.8:
                status = "PRESENT"
                score = min(1.0, pattern_match["confidence"] + 0.1)
            elif pattern_match["confidence"] >= 0.4:
                status = "PARTIALLY_PRESENT"
                score = pattern_match["confidence"]
            else:
                status = "ABSENT"
                score = 0.0
            
            notes = self._get_validation_notes(field_name, status, content_value, text)
            
            return {
                'score': score,
                'notes': notes
            }
            
        except Exception as e:
            logger.error(f"Error validating field {field_name}: {str(e)}")
            return {'score': 0.0, 'notes': f"Validation error: {str(e)}"}
    
    def _check_pattern_match(self, field_name: str, content_value: str, text: str) -> Dict[str, float]:
        """Check how well the content matches expected patterns."""
        if field_name not in self.field_patterns:
            return {"confidence": 0.0, "matches": []}
        
        text_lower = text.lower()
        content_lower = content_value.lower()
        
        best_match = {"confidence": 0.0, "matches": []}
        
        for category, patterns in self.field_patterns[field_name].items():
            category_matches = []
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    category_matches.append(pattern)
            
            if category_matches:
                # Check if content matches the category
                if any(re.search(pattern, content_lower, re.IGNORECASE) for pattern in category_matches):
                    confidence = min(1.0, len(category_matches) * 0.2 + 0.6)
                else:
                    confidence = min(1.0, len(category_matches) * 0.1 + 0.3)
                
                if confidence > best_match["confidence"]:
                    best_match = {"confidence": confidence, "matches": category_matches}
        
        return best_match
    
    def _get_validation_notes(self, field_name: str, status: str, content_value: str, text: str) -> str:
        """Get notes for the validation result."""
        if status == "PRESENT":
            return "Field is complete and matches expected patterns"
        elif status == "PARTIALLY_PRESENT":
            return f"Partial information found: {content_value}. Consider reviewing for additional details"
        else:
            return f"No clear information found for {field_name}. Review paper for additional information"

class FieldExtractionEnhancer:
    """Enhances field extraction with post-processing improvements."""
    
    def __init__(self):
        self.validator = EnhancedFieldValidator()
    
    def validate_field(self, field_name: str, field_data: Dict) -> Dict:
        """
        Validate a specific field.
        
        Args:
            field_name: Name of the field to validate
            field_data: Data for this field
            
        Returns:
            Dict with 'score' and 'notes'
        """
        # Call the validator's validate_field, passing empty text since it's optional
        return self.validator.validate_field(field_name, field_data)
    
    def enhance_extraction(self, extracted_data: Dict, full_text: str) -> Dict:
        """
        Enhance extracted data with validation and post-processing.
        
        Args:
            extracted_data: Raw extracted data from LLM
            full_text: Full text content for validation
            
        Returns:
            Enhanced extraction data
        """
        enhanced_data = {}
        
        for field_name in ["host_species", "body_site", "condition", "sequencing_type", "taxa_level", "sample_size"]:
            if field_name in extracted_data:
                # Validate the field
                validation_result = self.validator.validate_field(field_name, extracted_data[field_name], full_text)
                
                # Update the field with validation results
                enhanced_data[field_name] = {
                    "primary" if field_name == "host_species" else 
                    "site" if field_name == "body_site" else
                    "description" if field_name == "condition" else
                    "method" if field_name == "sequencing_type" else
                    "level" if field_name == "taxa_level" else "size": validation_result.extracted_value,
                    "confidence": validation_result.confidence,
                    "status": validation_result.status,
                    "reason_if_missing": validation_result.reason_if_missing,
                    "suggestions_for_curation": validation_result.suggestions_for_curation
                }
            else:
                # Create default structure for missing field
                enhanced_data[field_name] = self._create_default_field_structure(field_name)
        
        # Add summary fields
        missing_fields = [field for field, data in enhanced_data.items() if data.get("status") != "PRESENT"]
    
        enhanced_data["missing_fields"] = missing_fields
        enhanced_data["curation_preparation_summary"] = self._generate_curation_summary(missing_fields)
        
        return enhanced_data
    
    def _create_default_field_structure(self, field_name: str) -> Dict:
        """Create default structure for a missing field."""
        return {
            "primary" if field_name == "host_species" else 
            "site" if field_name == "body_site" else
            "description" if field_name == "condition" else
            "method" if field_name == "sequencing_type" else
            "level" if field_name == "taxa_level" else "size": "Unknown",
            "confidence": 0.0,
            "status": "ABSENT",
            "reason_if_missing": "Field not found in analysis",
            "suggestions_for_curation": f"Review paper for {field_name.replace('_', ' ')} information"
        }
    
    def _generate_curation_summary(self, missing_fields: List[str]) -> str:
        """Generate a summary of what's needed for curation."""
        if not missing_fields:
            return "All required fields are present. Paper is ready for curation."
        
        if len(missing_fields) == 1:
            return f"Missing 1 field: {missing_fields[0]}. Review paper for this information."
        elif len(missing_fields) <= 3:
            return f"Missing {len(missing_fields)} fields: {', '.join(missing_fields)}. Paper needs additional review."
        else:
            return f"Missing {len(missing_fields)} fields: {', '.join(missing_fields)}. Paper requires significant review before curation."