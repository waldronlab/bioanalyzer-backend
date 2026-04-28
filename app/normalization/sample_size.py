"""Sample size normalization utilities."""

from __future__ import annotations

import re
from typing import Any, Tuple

try:
    from word2number import w2n
except Exception:  # pragma: no cover - optional dependency at runtime
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


def normalize_sample_size(raw_value: Any) -> Tuple[str, str]:
    """Return sample size as integer string and extraction status."""
    if raw_value is None or str(raw_value).strip() in ("", "null", "None"):
        return "", "ABSENT"

    value = str(raw_value).strip()
    try:
        parsed = int(value.replace(",", ""))
        return str(parsed), "PRESENT"
    except ValueError:
        pass

    if w2n is not None:
        try:
            parsed = w2n.word_to_num(value)
            return str(int(parsed)), "PRESENT"
        except Exception:
            pass
    else:
        parsed = _simple_word_to_num(value)
        if parsed is not None:
            return str(parsed), "PRESENT"

    match = re.search(r"\b(\d[\d,]*)\b", value)
    if match:
        return str(int(match.group(1).replace(",", ""))), "PRESENT"

    return value, "PARTIALLY_PRESENT"
