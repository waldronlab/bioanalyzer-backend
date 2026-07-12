#!/usr/bin/env python3
"""Output rendering for the BioAnalyzer CLI (table/csv/detailed_csv/xml/json).

Split out of scripts/cli.py: this module is pure formatting logic over
already-computed analysis/retrieval results, with no argument parsing or
network/service calls of its own.

`--format csv` (and its long-form alias `curator_desk_csv`) is THE canonical,
curator-facing CSV shape - the one that matches curator_table_r/curator_table
exactly (see docs/CURATOR_DESK_CSV_FORMAT.md). `--format detailed_csv` is a
separate, older, Status-inclusive shape over all 5 ANALYSIS_FIELDS kept only
for internal validation tooling (scripts/eval/confusion_matrix_analysis.py) -
it is deliberately NOT what `--format csv` produces, precisely to avoid the
two being confused.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Dict, List

ANALYSIS_FIELDS: Dict[str, str] = {
    "host_species": "Host Species",
    "body_site": "Body Site",
    "condition": "Condition",
    "sequencing_type": "Sequencing Type",
    "sample_size": "Sample Size",
}

STATUS_ICONS = {"PRESENT": "✅", "PARTIALLY_PRESENT": "⚠️", "ABSENT": "❌"}


def _field_val(fields: dict, key: str, attr: str = "value") -> str:
    return str(fields.get(key, {}).get(attr, "") or "")


def _field_ontology_id(fields: dict, key: str) -> str:
    return str(fields.get(key, {}).get("ontology_id", "") or "")


def _field_ontology_candidates(fields: dict, key: str) -> str:
    """Compact 'label|ontology_id; label|ontology_id' string of alternate
    candidates, populated only when the field's mapping wasn't auto-applied
    (see app.normalization.grounding). Consumed by curator_table_r's mapping
    picker, not shown as a visible table column."""
    field_data = fields.get(key, {})
    if field_data.get("mapping_tier") == "auto":
        return ""
    candidates = field_data.get("mapping_candidates") or []
    return "; ".join(
        f"{c.get('label', '')}|{c.get('ontology_id', '')}" for c in candidates if c.get("ontology_id")
    )


def _bool_yes_no(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def _extract_year(publication_date: Any) -> str:
    s = str(publication_date or "").strip()
    m = re.search(r"\b(19|20)\d{2}\b", s)
    return m.group(0) if m else ""


def render_results(
    results: List[Dict[str, Any]], fmt: str, *, include_header: bool = True
) -> str:
    if fmt == "json":
        return json.dumps(results, indent=2, ensure_ascii=False)
    # "csv" and "curator_desk_csv" are the same output - the curator-facing
    # schema matching curator_table_r/curator_table (see module docstring).
    if fmt in ("csv", "curator_desk_csv"):
        return _render_curator_desk_csv(results, include_header=include_header)
    if fmt == "detailed_csv":
        return _render_detailed_csv(results)
    if fmt == "xml":
        return _render_xml(results)
    return _render_table(results)


def _render_table(results: List[Dict[str, Any]]) -> str:
    lines = [
        "\n" + "=" * 80,
        "🧬 BIOANALYZER - CURATABLE SIGNATURE ANALYSIS RESULTS",
        "=" * 80,
    ]
    for r in results:
        lines += [
            f"\n📄 PMID: {r.get('pmid', 'N/A')}",
            f"📝 Title: {r.get('title', 'N/A')}",
            f"📰 Journal: {r.get('journal', 'N/A')}",
            "-" * 60,
        ]
        for key, label in ANALYSIS_FIELDS.items():
            fd = r.get("fields", {}).get(key, {})
            icon = STATUS_ICONS.get(fd.get("status", ""), "❓")
            lines.append(
                f"{icon} {label:20} | {fd.get('status', 'UNKNOWN'):20} | "
                f"{str(fd.get('value', 'N/A')):30} | {fd.get('confidence', 0.0):.2f}"
            )
        lines += [
            "-" * 60,
            f"📋 Summary: {r.get('curation_summary ', 'N/A')}",
            f"⏱️  Time: {r.get('processing_time', 0):.2f}s",
            "",
        ]
    return "\n".join(lines)


def _render_detailed_csv(results: List[Dict[str, Any]]) -> str:
    """Older, Status-inclusive CSV over all 5 ANALYSIS_FIELDS - only for
    internal validation tooling, see module docstring."""
    out = io.StringIO()
    w = csv.writer(out)
    headers = ["PMID", "Title", "Journal"]
    for label in ANALYSIS_FIELDS.values():
        headers += [label, f"{label} Status"]
    headers += ["Summary", "Processing Time"]
    w.writerow(headers)
    for r in results:
        fields = r.get("fields", {})
        row = [r.get("pmid", ""), r.get("title", ""), r.get("journal", "")]
        for key in ANALYSIS_FIELDS:
            row += [_field_val(fields, key), _field_val(fields, key, "status")]
        row += [r.get("curation_summary", ""), r.get("processing_time", 0)]
        w.writerow(row)
    return out.getvalue()


def _render_curator_desk_csv(
    results: List[Dict[str, Any]], *, include_header: bool = True
) -> str:
    # Simplified curator-desk schema (per Levi Waldron review): plain value +
    # ontology ID per mapped field, no Status/Mapping-Confidence/Priority
    # columns. The *_Ontology_Candidates columns are curator-picker metadata,
    # not meant to be read as a visible table column (curator_table_r hides
    # them from DISPLAY_COLUMNS but uses them to populate a mapping picker).
    columns = [
        "PMID",
        "Year",
        "Title",
        "Journal",
        "Host Species",
        "Host Species Ontology ID",
        "Host Species Ontology Candidates",
        "Body Site",
        "Body Site Ontology ID",
        "Body Site Ontology Candidates",
        "Condition",
        "Condition Ontology ID",
        "Condition Ontology Candidates",
        "Sample Size",
        "Sequencing Type",
        "Differential Abundance",
        "In bsgdb",
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    if include_header:
        w.writeheader()
    seen: set = set()
    for r in results:
        pmid = str(r.get("pmid", "") or "").strip()
        if pmid in seen:
            continue
        seen.add(pmid)
        fields = r.get("fields", {}) or {}
        w.writerow(
            {
                "PMID": pmid,
                "Year": _extract_year(r.get("year") or r.get("publication_date", "")),
                "Title": r.get("title", ""),
                "Journal": r.get("journal", ""),
                "Host Species": _field_val(fields, "host_species"),
                "Host Species Ontology ID": _field_ontology_id(fields, "host_species"),
                "Host Species Ontology Candidates": _field_ontology_candidates(
                    fields, "host_species"
                ),
                "Body Site": _field_val(fields, "body_site"),
                "Body Site Ontology ID": _field_ontology_id(fields, "body_site"),
                "Body Site Ontology Candidates": _field_ontology_candidates(
                    fields, "body_site"
                ),
                "Condition": _field_val(fields, "condition"),
                "Condition Ontology ID": _field_ontology_id(fields, "condition"),
                "Condition Ontology Candidates": _field_ontology_candidates(
                    fields, "condition"
                ),
                "Sample Size": _field_val(fields, "sample_size"),
                "Sequencing Type": _field_val(fields, "sequencing_type"),
                "Differential Abundance": _bool_yes_no(
                    r.get("has_differential_abundance")
                ),
                "In bsgdb": _bool_yes_no(r.get("in_bugsigdb")),
            }
        )
    return out.getvalue()


def _render_xml(results: List[Dict[str, Any]]) -> str:
    if not results:
        return '<?xml version="1.0" encoding="UTF-8"?>\n<BioAnalyzerResults></BioAnalyzerResults>'
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<BioAnalyzerResults>"]
    xml_field_names = {
        "host_species": "HostSpecies",
        "body_site": "BodySite",
        "condition": "Condition",
        "sequencing_type": "SequencingType",
        "sample_size": "SampleSize",
    }
    for r in results:
        fields = r.get("fields", {})
        lines += [
            "  <Analysis>",
            f"    <PMID>{r.get('pmid', 'N/A')}</PMID>",
            f"    <Title>{r.get('title', 'N/A')}</Title>",
            f"    <Journal>{r.get('journal', 'N/A')}</Journal>",
            f"    <ProcessingTime>{r.get('processing_time', 0)}</ProcessingTime>",
            "    <Fields>",
        ]
        for key, tag in xml_field_names.items():
            fd = fields.get(key, {})
            lines += [
                f"      <{tag}>",
                f"        <Status>{fd.get('status', 'UNKNOWN')}</Status>",
                f"        <Value><![CDATA[{fd.get('value', 'N/A')}]]></Value>",
                f"        <Confidence>{fd.get('confidence', 0.0):.2f}</Confidence>",
                f"      </{tag}>",
            ]
        lines += [
            "    </Fields>",
            f"    <Summary><![CDATA[{r.get('curation_summary', '')}]]></Summary>",
            "  </Analysis>",
        ]
    lines.append("</BioAnalyzerResults>")
    return "\n".join(lines)


def render_retrieval(results: List[Dict[str, Any]], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(results, indent=2, ensure_ascii=False)
    if fmt == "csv":
        return _render_retrieval_csv(results)
    return _render_retrieval_table(results)


def _render_retrieval_table(results: List[Dict[str, Any]]) -> str:
    lines = [
        "\n" + "=" * 80,
        "📥 BIOANALYZER - PUBMED PAPER RETRIEVAL RESULTS",
        "=" * 80,
    ]
    for r in results:
        if "error" in r:
            lines += [f"\n❌ PMID: {r.get('pmid', 'N/A')}", f"Error: {r['error']}"]
            continue
        authors = r.get("authors", [])
        author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        lines += [
            f"\n📄 PMID: {r.get('pmid', 'N/A')}",
            f"📝 Title: {r.get('title', 'N/A')}",
            f"📰 Journal: {r.get('journal', 'N/A')}",
            f"👥 Authors: {author_str}",
            f"📅 Publication Date: {r.get('publication_date', 'N/A')}",
            f"📖 Full Text: {'✅ Available' if r.get('has_full_text') else '❌ Not available'}",
        ]
        abstract = r.get("abstract", "")
        if abstract:
            lines.append(
                f"📋 Abstract: {abstract[:200]}{'...' if len(abstract) > 200 else ''}"
            )
        lines.append("-" * 60)
    return "\n".join(lines)


def _render_retrieval_csv(results: List[Dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(
        [
            "PMID",
            "Title",
            "Journal",
            "Authors",
            "Publication Date",
            "Has Full Text",
            "Abstract Length",
            "Full Text Length",
            "Error",
        ]
    )
    for r in results:
        w.writerow(
            [
                r.get("pmid", ""),
                r.get("title", ""),
                r.get("journal", ""),
                "; ".join(r.get("authors", [])),
                r.get("publication_date", ""),
                "Yes" if r.get("has_full_text") else "No",
                len(r.get("abstract", "")),
                len(r.get("full_text", "")),
                r.get("error", ""),
            ]
        )
    return out.getvalue()
