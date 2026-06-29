"""
PMC XML section parsing and text-preparation helpers for the BugSigDB
analyzer.
"""

import re
from typing import Dict, List, Tuple

from defusedxml import ElementTree
from xml.etree.ElementTree import Element as ETElement

# ---------------------------------------------------------------------------
# PMC XML section parser
# ---------------------------------------------------------------------------

_SECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("ABSTRACT", re.compile(r"abstract", re.I)),
    ("INTRODUCTION", re.compile(r"intro(?:duction)?|background", re.I)),
    ("METHODS", re.compile(r"method|material|patient|protocol|statistical", re.I)),
    ("RESULTS", re.compile(r"result|finding", re.I)),
    ("DISCUSSION", re.compile(r"discussion|conclusion|summary", re.I)),
    ("SUPPLEMENTARY", re.compile(r"supplement|appendix", re.I)),
]


def _classify_section_title(title: str) -> str:
    if not title:
        return "OTHER"
    title_upper = title.strip().upper()
    for canonical, pattern in _SECTION_PATTERNS:
        if pattern.search(title_upper):
            return canonical
    return "OTHER"


def _local_tag(tag: str) -> str:
    """Strip the XML namespace prefix from an ElementTree tag (e.g. '{ns}sec' -> 'sec')."""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_pmc_sections(xml_text: str) -> Dict[str, str]:
    if not xml_text or not xml_text.strip():
        return {}
    if not xml_text.lstrip().startswith("<"):
        return {"FULL_TEXT": xml_text}
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        start = xml_text.find("<")
        if start > 0:
            try:
                root = ElementTree.fromstring(xml_text[start:])
            except ElementTree.ParseError:
                return {"FULL_TEXT": xml_text}
        else:
            return {"FULL_TEXT": xml_text}

    sections: Dict[str, List[str]] = {}

    def _walk(node: ETElement, inherited_label: str = "OTHER") -> None:
        tag = _local_tag(node.tag)
        if tag == "sec":
            ns_prefix = (node.tag.split("}")[0] + "}") if "}" in node.tag else ""
            title_el = node.find(f".//{ns_prefix}title") or node.find(
                f"{ns_prefix}title"
            )
            raw_title = ""
            if title_el is not None:
                raw_title = (title_el.text or "").strip() or "".join(
                    title_el.itertext()
                ).strip()
            label = _classify_section_title(raw_title) if raw_title else inherited_label

            para_texts: List[str] = []
            for child in node:
                child_tag = _local_tag(child.tag)
                if child_tag == "p":
                    text = "".join(child.itertext()).strip()
                    if text:
                        para_texts.append(text)
                elif child_tag not in ("sec", "title"):
                    inline = "".join(child.itertext()).strip()
                    if inline:
                        para_texts.append(inline)
            if para_texts:
                sections.setdefault(label, []).extend(para_texts)
            for child in node:
                child_tag = _local_tag(child.tag)
                if child_tag == "sec":
                    _walk(child, label)
        else:
            for child in node:
                _walk(child, inherited_label)

    _walk(root)
    return {k: "\n\n".join(v) for k, v in sections.items() if v}


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

_CONTEXT_CHAR_LIMIT = 8_000

_SECTION_BUDGETS: Dict[str, int] = {
    "ABSTRACT": 1_200,
    "METHODS": 3_000,
    "RESULTS": 2_000,
    "INTRODUCTION": 800,
    "DISCUSSION": 600,
    "OTHER": 400,
}


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = " [truncated]"
    if max_chars <= len(suffix):
        return text[:max_chars]
    limit = max_chars - len(suffix)
    cut = text[:limit]
    last_period = cut.rfind(".")
    if last_period > limit * 0.7:
        cut = cut[: last_period + 1]
    return cut + suffix


def prepare_analysis_context(
    abstract: str,
    full_text: str,
    *,
    char_limit: int = _CONTEXT_CHAR_LIMIT,
) -> str:
    abstract = (abstract or "").strip()
    full_text = (full_text or "").strip()
    if not full_text:
        if not abstract:
            return ""
        return f"ABSTRACT:\n{_truncate(abstract, char_limit)}"

    sections = _parse_pmc_sections(full_text)
    if not sections:
        sections = {"FULL_TEXT": full_text}
    if abstract:
        sections["ABSTRACT"] = abstract

    ordered_keys = ["ABSTRACT", "METHODS", "RESULTS", "INTRODUCTION", "DISCUSSION"]
    remaining_keys = [k for k in sections if k not in ordered_keys]
    key_order = ordered_keys + remaining_keys

    parts: List[str] = []
    total_chars = 0

    for key in key_order:
        if key not in sections or not sections[key].strip():
            continue
        budget = _SECTION_BUDGETS.get(key, _SECTION_BUDGETS["OTHER"])
        remaining_budget = char_limit - total_chars
        if remaining_budget <= 15:
            break
        separator = "\n\n" if parts else ""
        header = f"{key}:\n"
        overhead = len(separator) + len(header)
        effective_budget = max(0, min(budget, remaining_budget - overhead))
        if effective_budget <= 0:
            break
        section_text = _truncate(sections[key], effective_budget)
        parts.append(f"{separator}{header}{section_text}")
        total_chars += overhead + len(section_text)

    return "".join(parts)
