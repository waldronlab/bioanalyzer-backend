"""Guard against benchmark-answer leakage into the extraction prompt.

The Condition benchmark (pmids.ground_truth.json and the fresh held-out set
under benchmark_results/testset-fresh-20261113/) is only an honest measure if
the prompt does not hand the model the answers. An earlier prompt listed
"diet", "high fat diet", "delivery method", "colorectal cancer",
"Parkinson's disease" and others as examples - all of them curated labels in
the test sets. These tests fail if any example term in EXTRACTION_PROMPT or
ESSENTIAL_FIELDS matches (or is a near-variant of) a test-set Condition label.

They load the ground-truth files when present and skip otherwise (the
benchmark files are not part of every checkout). Do not "fix" a failure by
editing the ground truth: pick an example that is not a test-set label.
"""

import json
import re
from pathlib import Path
from typing import List, Set

import pytest

from app.services.bugsigdb_analyzer.constants import ESSENTIAL_FIELDS, EXTRACTION_PROMPT

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GROUND_TRUTH_FILES = (
    _REPO_ROOT / "pmids.ground_truth.json",
    _REPO_ROOT
    / "benchmark_results"
    / "testset-fresh-20261113"
    / "pmids.ground_truth.json",
)

# Token-level synonyms/abbreviations, so "type 2 diabetes" matches
# "type ii diabetes mellitus" and "IBD" matches "inflammatory bowel disease".
_TOKEN_MAP = {
    "ii": "2",
    "i": "1",
    "carcinoma": "cancer",
    "carcinomas": "cancer",
    "neoplasm": "cancer",
    "neoplasms": "cancer",
    "tumor": "cancer",
    "tumour": "cancer",
    "tumors": "cancer",
    "tumours": "cancer",
    "mellitus": "",
    "coeliac": "celiac",
    "ibd": "inflammatory bowel disease",
    "uc": "ulcerative colitis",
    "crc": "colorectal cancer",
    "t2d": "type 2 diabetes",
    "t2dm": "type 2 diabetes",
    "t1d": "type 1 diabetes",
    "nafld": "non alcoholic fatty liver disease",
    "copd": "chronic obstructive pulmonary disease",
    "hiv": "human immunodeficiency virus",
    "hpv": "human papilloma virus",
    "ckd": "chronic kidney disease",
    "pcos": "polycystic ovary syndrome",
    "ptsd": "post traumatic stress disorder",
}
# Severity/stage/activity qualifiers: "severe periodontitis" is a near-variant
# of "chronic periodontitis".
_QUALIFIERS = {
    "chronic",
    "acute",
    "severe",
    "mild",
    "moderate",
    "refractory",
    "active",
    "early",
    "late",
    "onset",
    "stage",
    "advanced",
    "persistent",
    "recurrent",
}
# Words that are curated labels but also unavoidable plain-English nouns in
# prose (never used as an example term). Quoted examples are still checked
# against these.
_PROSE_ALLOWLIST = {"population", "phenotype"}


def _normalize(text: str, *, drop_qualifiers: bool = True) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    out: List[str] = []
    for tok in text.split():
        tok = _TOKEN_MAP.get(tok, tok)
        for sub in tok.split():
            if drop_qualifiers and sub in _QUALIFIERS:
                continue
            out.append(sub)
    return " ".join(out)


def _contains_phrase(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def _load_test_labels() -> Set[str]:
    labels: Set[str] = set()
    for path in _GROUND_TRUTH_FILES:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.values():
            for label in entry.get("condition_labels") or []:
                if label and str(label).strip():
                    labels.add(str(label).strip().lower())
    return labels


@pytest.fixture(scope="module")
def test_labels() -> Set[str]:
    labels = _load_test_labels()
    if not labels:
        pytest.skip("benchmark ground-truth files not present in this checkout")
    return labels


def _prompt_texts() -> List[str]:
    return [EXTRACTION_PROMPT, *ESSENTIAL_FIELDS.values()]


def _quoted_examples() -> List[str]:
    found: List[str] = []
    for text in _prompt_texts():
        found += re.findall(r'"([^"\n]+)"', text)
        # Single-quoted examples; the lookarounds skip apostrophes ("Crohn's").
        found += re.findall(r"(?<![A-Za-z])'([^'\n]+)'(?![A-Za-z])", text)
    return found


def _leaks(example: str, labels: Set[str]) -> List[str]:
    ex = _normalize(example)
    if not ex:
        return []
    hits = []
    for label in labels:
        lab = _normalize(label)
        if not lab:
            continue
        if ex == lab or _contains_phrase(ex, lab) or _contains_phrase(lab, ex):
            hits.append(label)
    return hits


def test_normalizer_catches_known_near_variants():
    """The near-variant matching itself must work, or the guard is hollow."""
    labels = {
        "type ii diabetes mellitus",
        "colorectal carcinoma",
        "chronic periodontitis",
    }
    assert _leaks("type 2 diabetes", labels)
    assert _leaks("T2D", labels)
    assert _leaks("colorectal cancer", labels)
    assert _leaks("severe periodontitis", labels)
    assert _leaks("cancer", labels)  # broader parent of a label
    assert not _leaks("celiac disease", labels)


def test_quoted_prompt_examples_are_not_test_set_labels(test_labels):
    leaks = {
        example: hits
        for example in _quoted_examples()
        if (hits := _leaks(example, test_labels))
    }
    assert not leaks, f"prompt examples leak benchmark Condition labels: {leaks}"


def test_prompt_prose_does_not_name_test_set_labels(test_labels):
    """Catches unquoted examples too (e.g. "such as diet, exposure, ...")."""
    prose = " ".join(_normalize(t, drop_qualifiers=False) for t in _prompt_texts())
    leaks = sorted(
        label
        for label in test_labels
        if label not in _PROSE_ALLOWLIST
        and _contains_phrase(prose, _normalize(label, drop_qualifiers=False))
    )
    assert not leaks, f"prompt text names benchmark Condition labels: {leaks}"
