"""Sample size normalization utilities."""

from __future__ import annotations

import re
from typing import Any

from app.normalization.types import NormalizedTerm

try:
    from word2number import w2n
except ImportError:  # pragma: no cover - optional dependency at runtime
    w2n = None


def _simple_word_to_num(text: str) -> int | None:
    ones = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
    }
    tens = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
    }
    scales = {"hundred": 100, "thousand": 1000}

    tokens = re.findall(r"[a-z]+", text.lower())
    if not tokens:
        return None
    total = 0
    current = 0
    consumed = False
    for token in tokens:
        if token in ones:
            current += ones[token]
            consumed = True
        elif token in tens:
            current += tens[token]
            consumed = True
        elif token == "and":
            continue
        elif token in scales:
            consumed = True
            if current == 0:
                current = 1
            current *= scales[token]
            if token == "thousand":
                total += current
                current = 0
        else:
            if consumed:
                break
    if not consumed:
        return None
    return total + current


# Nouns that indicate a nearby number is a participant/sample count rather
# than a year, percentage, p-value, or other incidental figure.
_SAMPLE_NOUN = (
    r"participants?|subjects?|patients?|volunteers?|controls?|cases?|"
    r"individuals?|samples?|specimens?|donors?|women|men|infants?|neonates?|"
    r"children|mice|rats|enrolled|recruited"
)

_TOTAL_OF_RE = re.compile(
    r"\btotal(?:\s+(?:sample\s+size|number))?\s+of\s+(\d[\d,]*)\b", re.IGNORECASE
)
_ANCHORED_NUMBER_RE = re.compile(
    r"\b(\d[\d,]*)\s+(?:" + _SAMPLE_NOUN + r")\b", re.IGNORECASE
)
# A bare 4-digit number in this range is more likely a publication year than
# a sample size when nothing anchors it to a sample-related noun.
_LIKELY_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _resolve_ambiguous_count(value: str) -> NormalizedTerm | None:
    """Resolve a free-text sentence that may mention more than one number.

    Resolution order (documented contract — see test_normalization.py):
      1. An explicit "total of N" / "total sample size of N" wins outright
         (e.g. "98 cases and 45 controls, for a total of 143 participants"
         -> 143), since the abstract is telling us which number is the
         overall size.
      2. Otherwise, take the FIRST number immediately followed by a
         sample-related noun, in reading order (e.g. "98 cases and 45
         controls" -> 98; "In 2019, 65 volunteers were enrolled" -> 65,
         correctly skipping the year).
      3. Otherwise, fall back to the first number in the text at all,
         unless it looks like a bare year (1900-2099) or a percentage —
         those are excluded as likely false positives.
    """
    total_match = _TOTAL_OF_RE.search(value)
    if total_match:
        return NormalizedTerm(
            str(int(total_match.group(1).replace(",", ""))), "", "PRESENT", 0.9
        )

    anchored_match = _ANCHORED_NUMBER_RE.search(value)
    if anchored_match:
        return NormalizedTerm(
            str(int(anchored_match.group(1).replace(",", ""))), "", "PRESENT", 0.9
        )

    for match in re.finditer(r"\b(\d[\d,]*)\b", value):
        digits = match.group(1).replace(",", "")
        if _LIKELY_YEAR_RE.match(digits):
            continue
        tail = value[match.end() : match.end() + 12].lstrip()
        if tail.startswith("%") or tail.lower().startswith("percent"):
            continue
        return NormalizedTerm(str(int(digits)), "", "PRESENT", 0.7)

    return None


def normalize_sample_size(raw_value: Any) -> NormalizedTerm:
    """Return sample size as integer string (no ontology ID).

    See _resolve_ambiguous_count() for the rule used when free text
    mentions more than one number (multiple cohorts, a year, a percentage).
    """
    if raw_value is None or str(raw_value).strip() in ("", "null", "None"):
        return NormalizedTerm.absent()

    value = str(raw_value).strip()
    try:
        parsed = int(value.replace(",", ""))
        return NormalizedTerm(str(parsed), "", "PRESENT", 1.0)
    except ValueError:
        pass

    if w2n is not None:
        try:
            parsed = w2n.word_to_num(value)
            return NormalizedTerm(str(int(parsed)), "", "PRESENT", 1.0)
        except ValueError:
            pass
    else:
        parsed = _simple_word_to_num(value)
        if parsed is not None:
            return NormalizedTerm(str(parsed), "", "PRESENT", 1.0)

    resolved = _resolve_ambiguous_count(value)
    if resolved is not None:
        return resolved

    return NormalizedTerm(value, "", "PARTIALLY_PRESENT", 0.5)
