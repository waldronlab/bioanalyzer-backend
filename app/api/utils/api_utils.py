"""
Shared utility functions for API endpoints.
"""
import re
import logging
from typing import Dict, List, Optional
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)


def extract_taxa(text: str) -> List[str]:
    """Extract potential taxa from text."""
    # This is a simplified implementation
    taxa_patterns = [
        r'\b[A-Z][a-z]+ [a-z]+\b',  # Genus species
        r'\b[A-Z][a-z]+\b',  # Genus only
    ]
    
    taxa = []
    for pattern in taxa_patterns:
        matches = re.findall(pattern, text)
        taxa.extend(matches)
    
    return list(set(taxa))


def create_default_field_structure(field_name: str) -> Dict:
    """Create a default structure for a missing field."""
    field_structures = {
        "host_species": {
            "status": "ABSENT",
            "value": None,
            "confidence": 0.0,
            "reason_if_missing": "No host species information found in the paper",
            "suggestions": "Look for mentions of human, mouse, rat, or other study organisms"
        },
        "body_site": {
            "status": "ABSENT", 
            "value": None,
            "confidence": 0.0,
            "reason_if_missing": "No body site information found in the paper",
            "suggestions": "Look for mentions of gut, oral, skin, or other sampling sites"
        },
        "condition": {
            "status": "ABSENT",
            "value": None,
            "confidence": 0.0,
            "reason_if_missing": "No condition information found in the paper",
            "suggestions": "Look for disease names, treatments, or exposure conditions"
        },
        "sequencing_type": {
            "status": "ABSENT",
            "value": None,
            "confidence": 0.0,
            "reason_if_missing": "No sequencing type information found in the paper",
            "suggestions": "Look for mentions of 16S, metagenomics, or other sequencing methods"
        },
        "taxa_level": {
            "status": "ABSENT",
            "value": None,
            "confidence": 0.0,
            "reason_if_missing": "No taxonomic level information found in the paper",
            "suggestions": "Look for mentions of phylum, genus, species, or other taxonomic levels"
        },
        "sample_size": {
            "status": "ABSENT",
            "value": None,
            "confidence": 0.0,
            "reason_if_missing": "No sample size information found in the paper",
            "suggestions": "Look for numbers of samples, participants, or study groups"
        }
    }
    
    return field_structures.get(field_name, {
        "status": "ABSENT",
        "value": None,
        "confidence": 0.0,
        "reason_if_missing": f"No {field_name} information found in the paper",
        "suggestions": f"Look for {field_name} related information in the paper"
    })


def validate_field_structure(field_data: Dict, field_name: str) -> bool:
    """Validate that a field has the correct structure."""
    required_keys = {
        "status", "value", "confidence", "reason_if_missing", "suggestions"
    }
    
    if not isinstance(field_data, dict):
        return False
    
    return required_keys.issubset(field_data.keys())


def create_comprehensive_fallback_analysis() -> Dict:
    """Create a comprehensive fallback analysis when parsing completely fails."""
    return {
        "host_species": create_default_field_structure("host_species"),
        "body_site": create_default_field_structure("body_site"),
        "condition": create_default_field_structure("condition"),
        "sequencing_type": create_default_field_structure("sequencing_type"),
        "taxa_level": create_default_field_structure("taxa_level"),
        "sample_size": create_default_field_structure("sample_size")
    }


def generate_curation_summary(parsed_analysis: Dict, missing_fields: List[str]) -> str:
    """Generate a summary of what's needed for curation."""
    if not missing_fields:
        return "This paper contains all required fields for BugSigDB curation."
    
    summary_parts = [f"Missing fields for curation: {', '.join(missing_fields)}"]
    
    for field in missing_fields:
        if field in parsed_analysis and "suggestions" in parsed_analysis[field]:
            suggestion = parsed_analysis[field]["suggestions"]
            if suggestion:
                summary_parts.append(f"- {field.replace('_', ' ').title()}: {suggestion}")
    
    return " ".join(summary_parts)


def get_paper_metadata_from_csv(pmid: str, csv_path: str = 'data/full_dump.csv') -> Optional[Dict]:
    """Get paper metadata from CSV file."""
    try:
        import csv
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            # Skip comment lines (starting with #) or skip first 2 lines
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get('pmid') == pmid:
                    return {
                        'title': row.get('title', ''),
                        'authors': row.get('authors', ''),
                        'journal': row.get('journal', ''),
                        'publication_date': row.get('publication_date', '')
                    }
    except Exception as e:
        logger.error(f"Error reading CSV metadata for PMID {pmid}: {e}")
    
    return None


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(pytz.UTC).isoformat()
