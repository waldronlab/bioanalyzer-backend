import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BasicFieldExtractor:
    """
    Heuristic fallback extractor for the 6 BugSigDB fields when the Gemini/LLM model is unavailable.
    Uses keyword and regex-based extraction and MicrobeSigClassifier helpers.
    """

    HOST_SPECIES_KEYWORDS = {
        'human': ['human', 'homo sapiens', 'patient', 'participants'],
        'mouse': ['mouse', 'mice', 'murine', 'mus musculus'],
        'rat': ['rat', 'rattus'],
        'zebrafish': ['zebrafish', 'danio rerio'],
        'fly': ['drosophila', 'fruit fly'],
    }

    TAXA_LEVEL_KEYWORDS = ['phylum', 'class', 'order', 'family', 'genus', 'species']
    
    BODY_SITE_KEYWORDS = {
        'gut': ['gut', 'intestinal', 'stool', 'fecal', 'gastrointestinal', 'colon'],
        'oral': ['oral', 'mouth', 'dental', 'tongue', 'saliva'],
        'skin': ['skin', 'cutaneous', 'epidermal'],
        'respiratory': ['lung', 'respiratory', 'nasal', 'nose'],
        'vaginal': ['vaginal', 'vagina'],
        'urinary': ['urine', 'bladder', 'urethral'],
    }
    
    SEQUENCING_TYPE_KEYWORDS = {
        '16s': ['16s', '16s rrna', '16s ribosomal'],
        'metagenomics': ['metagenomics', 'metagenomic', 'whole genome', 'shotgun'],
        'its': ['its', 'internal transcribed spacer'],
        'amplicon': ['amplicon', 'pcr', 'targeted'],
    }

    SAMPLE_SIZE_REGEX = [
        r"n\s*=\s*(\d{2,4})",
        r"sample[s]?\s*(size|count)?\s*(of|=)?\s*(\d{2,4})",
        r"participant[s]?\s*(\d{2,4})",
        r"(\d{2,4})\s*(sample[s]?|participant[s]?)",
    ]

    def __init__(self):
        # Classifier removed - using keyword-based extraction only
        self.classifier = None

    def extract(self, text: str) -> Dict[str, Dict]:
        """Extract BugSigDB-relevant fields from text using heuristics and classifier."""
        t = (text or '').lower()
        fields: Dict[str, Dict] = {}

        # --- Host species ---
        host_value = None
        for sp, kws in self.HOST_SPECIES_KEYWORDS.items():
            if any(k in t for k in kws):
                host_value = sp
                break
        fields['host_species'] = self._mk_field(host_value)

        # --- Keyword-based extraction for body site, condition, sequencing type ---
        body_site_value = self._extract_body_site(t)
        condition_value = self._extract_condition(t)
        seq_value = self._extract_sequencing_type(t)

        fields['body_site'] = self._mk_field(body_site_value)
        fields['condition'] = self._mk_field(condition_value)
        fields['sequencing_type'] = self._mk_field(seq_value)

        # --- Taxa level keyword search ---
        taxa_value = next((k for k in self.TAXA_LEVEL_KEYWORDS if k in t), None)
        fields['taxa_level'] = self._mk_field(taxa_value)

        # --- Sample size regex detection ---
        sample_value = None
        for rgx in self.SAMPLE_SIZE_REGEX:
            m = re.search(rgx, t)
            if m:
                nums = [g for g in m.groups() if g and g.isdigit()]
                if nums:
                    sample_value = nums[-1]
                    break
        fields['sample_size'] = self._mk_field(sample_value)

        return fields

    def _mk_field(self, value: Optional[str]) -> Dict[str, Optional[str]]:
        """Format extracted field into standard response format."""
        if value is None:
            return {
                'status': 'ABSENT',
                'value': None,
                'confidence': 0.0,
                'reason_if_missing': 'Not detected by heuristic fallback',
                'suggestions': None,
            }
        return {
            'status': 'PRESENT',
            'value': value,
            'confidence': 0.6,  # heuristic confidence
            'reason_if_missing': None,
            'suggestions': None,
        }
    
    def _extract_body_site(self, text: str) -> Optional[str]:
        """Extract body site using keyword matching."""
        for site, keywords in self.BODY_SITE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return site
        return None
    
    def _extract_condition(self, text: str) -> Optional[str]:
        """Extract condition/disease using common patterns."""
        # Look for common patterns like "disease", "disorder", "syndrome", etc.
        condition_patterns = [
            r"(inflammatory\s+bowel\s+disease|ibd)",
            r"(crohn['\"]s?\s+disease)",
            r"(ulcerative\s+colitis)",
            r"(irritable\s+bowel\s+syndrome|ibs)",
            r"(diabetes)",
            r"(obes[ei]ty)",
            r"(autoimmune\s+disease)",
        ]
        
        for pattern in condition_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_sequencing_type(self, text: str) -> Optional[str]:
        """Extract sequencing type using keyword matching."""
        for seq_type, keywords in self.SEQUENCING_TYPE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return seq_type
        return None
