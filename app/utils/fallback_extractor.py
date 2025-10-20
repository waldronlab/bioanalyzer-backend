import re
import logging
from typing import Dict, List, Optional

from app.services.bugsigdb_classifier import MicrobeSigClassifier

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

    SAMPLE_SIZE_REGEX = [
        r"n\s*=\s*(\d{2,4})",
        r"sample[s]?\s*(size|count)?\s*(of|=)?\s*(\d{2,4})",
        r"participant[s]?\s*(\d{2,4})",
        r"(\d{2,4})\s*(sample[s]?|participant[s]?)",
    ]

    def __init__(self):
        # Initialize classifier for metadata-based extraction
        try:
            self.classifier = MicrobeSigClassifier()
            logger.info("BasicFieldExtractor: MicrobeSigClassifier initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize MicrobeSigClassifier: {e}")
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

        # --- Classifier-based body site, condition, sequencing type ---
        body_site_value = None
        condition_value = None
        seq_value = None

        if self.classifier:
            try:
                prediction = self.classifier.analyze_text(t)
                body_site_value = prediction.get("body_site")
                condition_value = prediction.get("condition")
                seq_value = prediction.get("sequencing_type")
            except Exception as e:
                logger.error(f"Classifier analysis failed: {e}")

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
