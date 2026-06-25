"""
Pure parsing/scoring helpers for Gemini LLM responses, extracted from
GeminiQA (app/models/gemini_qa.py). None of these need any instance
state - they only operate on the text/list passed in - so they live here
as plain functions; GeminiQA's same-named methods delegate to them to
keep the existing self.method(...)/qa.method(...) call sites working.
"""

import logging
import re
from typing import Dict, List, Tuple, Union

from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)

# Shared keyword categories - previously duplicated byte-for-byte between
# estimate_category_scores() and extract_found_terms().
RESPONSE_CATEGORIES: Dict[str, List[str]] = {
    "microbiome": ["microbiome", "microbial", "bacteria", "microbiota"],
    "methods": [
        "16s",
        "metagenomic",
        "sequencing",
        "amplicon",
        "shotgun",
        "transcriptomic",
        "qpcr",
        "fish",
    ],
    "analysis": [
        "enriched",
        "depleted",
        "increased",
        "decreased",
        "differential",
        "higher abundance",
        "lower abundance",
    ],
    "body_sites": [
        "gut",
        "oral",
        "skin",
        "lung",
        "vaginal",
        "intestinal",
        "colon",
        "mouth",
        "dermal",
        "epidermis",
        "airway",
        "bronchial",
        "cervical",
    ],
    "diseases": [
        "ibd",
        "cancer",
        "tumor",
        "carcinoma",
        "neoplasm",
        "obesity",
        "diabetes",
        "infection",
        "autoimmune",
        "arthritis",
        "lupus",
        "multiple sclerosis",
    ],
}


def estimate_confidence(key_findings: List[str]) -> float:
    if not key_findings:
        return 0.0
    return min(1.0, 0.3 + 0.15 * len(key_findings))


def estimate_category_scores(key_findings: List[str]) -> Dict[str, float]:
    text = " ".join(key_findings).lower()
    scores = {}
    for cat, keywords in RESPONSE_CATEGORIES.items():
        count = sum(1 for kw in keywords if kw in text)
        scores[cat] = min(1.0, count / max(1, len(keywords)))
    return scores


def parse_gemini_output(
    key_findings: List[str],
) -> Tuple[List[str], List[str]]:
    findings = []
    suggested_topics = []
    in_suggested = False
    for line in key_findings:
        if "Suggested Topics" in line or "Suggested Topics for Future Research" in line:
            in_suggested = True
            continue
        if in_suggested:
            if line.strip().startswith("*") or line.strip().startswith("-"):
                suggested_topics.append(line.strip("*- ").strip())
            elif line.strip() == "" or line.strip().startswith("**"):
                continue
            else:
                in_suggested = False
        if not in_suggested:
            findings.append(line)
    return findings, suggested_topics


def extract_found_terms(key_findings: List[str]) -> Dict[str, List[str]]:
    text = " ".join(key_findings).lower()
    found = {}
    for cat, keywords in RESPONSE_CATEGORIES.items():
        found[cat] = [kw for kw in keywords if kw in text]
    return found


def _empty_curation_analysis() -> Dict[str, Union[str, float, List[str]]]:
    return {
        "readiness": "UNKNOWN",
        "explanation": "",
        "microbial_signatures": "Unknown",
        "signature_types": [],
        "data_quality": "Unknown",
        "statistical_significance": "Unknown",
        "required_fields": [],
        "missing_fields": [],
        "data_completeness": "Unknown",
        "specific_reasons": [],
        "confidence": 0.0,
        "examples": [],
        "general_factors_present": [],
        "human_animal_factors_present": [],
        "environmental_factors_present": [],
        "missing_critical_factors": [],
        "factor_based_score": 0.0,
    }


def parse_enhanced_analysis(
    analysis_text: str,
) -> Dict[str, Union[str, float, List[str]]]:
    try:
        lines = analysis_text.split("\n")
        curation_analysis = _empty_curation_analysis()

        current_section = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "CURATION READINESS ASSESSMENT:" in line:
                current_section = "readiness"
                continue
            elif "DETAILED EXPLANATION:" in line:
                current_section = "explanation"
                continue
            elif "FACTOR-BASED ANALYSIS:" in line:
                current_section = "factor_analysis"
                continue
            elif "MICROBIAL SIGNATURE ANALYSIS:" in line:
                current_section = "signatures"
                continue
            elif "CURATABLE CONTENT ASSESSMENT:" in line:
                current_section = "content"
                continue
            elif "SPECIFIC REASONS" in line:
                current_section = "reasons"
                continue
            elif "CONFIDENCE LEVEL:" in line:
                current_section = "confidence"
                continue
            elif "EXAMPLES AND EVIDENCE:" in line:
                current_section = "examples"
                continue

            if current_section == "readiness":
                line_upper = line.upper()
                # Check the "NOT READY..." variants first: "READY FOR CURATION"
                # is a substring of "NOT READY FOR CURATION", so checking the
                # bare READY phrases first would misclassify NOT_READY as READY.
                if "NOT READY FOR CURATION" in line_upper:
                    curation_analysis["readiness"] = "NOT_READY"
                elif "READY FOR CURATION" in line_upper:
                    curation_analysis["readiness"] = "READY"
                elif "NOT READY" in line_upper:
                    curation_analysis["readiness"] = "NOT_READY"
                elif "READY" in line_upper and "NOT" not in line_upper:
                    curation_analysis["readiness"] = "READY"
                elif "UNKNOWN" in line_upper or "UNCLEAR" in line_upper:
                    curation_analysis["readiness"] = "UNKNOWN"
            elif current_section == "explanation":
                curation_analysis["explanation"] += line + " "
            elif current_section == "factor_analysis":
                if "General Factors Present:" in line:
                    factors_text = line.split(":", 1)[1] if ":" in line else ""
                    curation_analysis["general_factors_present"] = [
                        f.strip() for f in factors_text.split(",") if f.strip()
                    ]
                elif "Human/Animal Factors Present:" in line:
                    factors_text = line.split(":", 1)[1] if ":" in line else ""
                    curation_analysis["human_animal_factors_present"] = [
                        f.strip() for f in factors_text.split(",") if f.strip()
                    ]
                elif "Environmental Factors Present:" in line:
                    factors_text = line.split(":", 1)[1] if ":" in line else ""
                    curation_analysis["environmental_factors_present"] = [
                        f.strip() for f in factors_text.split(",") if f.strip()
                    ]
                elif "Missing Critical Factors:" in line:
                    factors_text = line.split(":", 1)[1] if ":" in line else ""
                    curation_analysis["missing_critical_factors"] = [
                        f.strip() for f in factors_text.split(",") if f.strip()
                    ]
            elif current_section == "signatures":
                if "Presence of microbial signatures:" in line:
                    if "yes" in line.lower():
                        curation_analysis["microbial_signatures"] = "Present"
                    elif "no" in line.lower():
                        curation_analysis["microbial_signatures"] = "Absent"
                    elif "partial" in line.lower():
                        curation_analysis["microbial_signatures"] = "Partial"
                elif "Types of signatures found:" in line:
                    types_text = line.split(":", 1)[1] if ":" in line else ""
                    curation_analysis["signature_types"] = [
                        t.strip() for t in types_text.split(",") if t.strip()
                    ]
                elif "Quality of signature data:" in line:
                    if "high" in line.lower():
                        curation_analysis["data_quality"] = "High"
                    elif "medium" in line.lower():
                        curation_analysis["data_quality"] = "Medium"
                    elif "low" in line.lower():
                        curation_analysis["data_quality"] = "Low"
                elif "Statistical significance:" in line:
                    if "yes" in line.lower():
                        curation_analysis["statistical_significance"] = "Yes"
                    elif "no" in line.lower():
                        curation_analysis["statistical_significance"] = "No"
                    elif "insufficient" in line.lower():
                        curation_analysis["statistical_significance"] = "Insufficient"
            elif current_section == "content":
                if "Missing required fields:" in line:
                    fields_text = line.split(":", 1)[1] if ":" in line else ""
                    curation_analysis["missing_fields"] = [
                        f.strip() for f in fields_text.split(",") if f.strip()
                    ]
                elif "Data completeness:" in line:
                    # Check only the value after the colon, not the whole line -
                    # the label itself ("completeness") contains "complete" as a
                    # substring, which would otherwise always match first.
                    value = (line.split(":", 1)[1] if ":" in line else "").lower()
                    if "insufficient" in value:
                        curation_analysis["data_completeness"] = "Insufficient"
                    elif "partial" in value:
                        curation_analysis["data_completeness"] = "Partial"
                    elif "complete" in value:
                        curation_analysis["data_completeness"] = "Complete"
            elif current_section == "reasons":
                if line.startswith("-") or line.startswith("*"):
                    curation_analysis["specific_reasons"].append(
                        line.lstrip("- *").strip()
                    )
            elif current_section == "confidence":
                confidence_match = re.search(r"(\d+\.?\d*)", line)
                if confidence_match:
                    curation_analysis["confidence"] = float(confidence_match.group(1))
            elif current_section == "examples":
                if line.startswith("-") or line.startswith("*"):
                    curation_analysis["examples"].append(line.lstrip("- *").strip())

        curation_analysis["explanation"] = curation_analysis["explanation"].strip()
        total_factors = (
            len(curation_analysis["general_factors_present"])
            + len(curation_analysis["human_animal_factors_present"])
            + len(curation_analysis["environmental_factors_present"])
        )
        max_factors = 16
        curation_analysis["factor_based_score"] = min(1.0, total_factors / max_factors)

        return curation_analysis

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error("Error parsing enhanced analysis: %s", safe_error)
        result = _empty_curation_analysis()
        result["readiness"] = "ERROR"
        result["explanation"] = f"Error parsing analysis: {safe_error}"
        return result
