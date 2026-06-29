#!/usr/bin/env python3
"""Output rendering for the BioAnalyzer CLI (table/csv/curator_desk_csv/xml/json).

Split out of scripts/cli.py: this module is pure formatting logic over
already-computed analysis/retrieval results, with no argument parsing or
network/service calls of its own.
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
    "taxa_level": "Taxa Level",
    "sample_size": "Sample Size",
}

STATUS_ICONS = {"PRESENT": "✅", "PARTIALLY_PRESENT": "⚠️", "ABSENT": "❌"}


def _field_val(fields: dict, key: str, attr: str = "value") -> str:
    return str(fields.get(key, {}).get(attr, "") or "")


def _field_ontology_id(fields: dict, key: str) -> str:
    return str(fields.get(key, {}).get("ontology_id", "") or "")


def _field_mapping_confidence(fields: dict, key: str) -> str:
    try:
        return f"{float(fields.get(key, {}).get('mapping_confidence', 0.0)):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _sequencing_type_raw(fields: dict) -> str:
    """Original pre-normalization text, shown only when it differs from
    the normalized "Sequencing Type" value (e.g. the "other" fallback)."""
    raw = str(fields.get("sequencing_type", {}).get("raw", "") or "")
    normalized = _field_val(fields, "sequencing_type")
    return raw if raw and raw != normalized else ""


def _status_normalise(value: Any) -> str:
    s = str(value).strip().upper() if value else ""
    return s if s in {"PRESENT", "PARTIALLY_PRESENT", "ABSENT"} else "ABSENT"


def _bool_upper(value: Any) -> str:
    return "TRUE" if bool(value) else "FALSE"


def _extract_year(publication_date: Any) -> str:
    s = str(publication_date or "").strip()
    m = re.search(r"\b(19|20)\d{2}\b", s)
    return m.group(0) if m else ""


def _priority_score(fields: dict) -> float:
    """
    Calculate curation priority score (0-5 range).

    Weights each field by its extraction confidence:
    - PRESENT: weight = 1.0
    - PARTIALLY_PRESENT: weight = 0.5
    - ABSENT: weight = 0.0

    Score = sum(weight × mapping_confidence) for each of 5 fields.
    Higher scores = more promising candidates for curation.
    """
    field_keys = [
        "host_species",
        "body_site",
        "condition",
        "sequencing_type",
        "sample_size",
    ]
    weights = {"PRESENT": 1.0, "PARTIALLY_PRESENT": 0.5, "ABSENT": 0.0}
    score = 0.0

    for key in field_keys:
        field_data = fields.get(key, {})
        status = str(field_data.get("status", "ABSENT")).strip().upper()
        base_weight = weights.get(status, 0.0)

        if base_weight == 0.0:
            continue

        # Get mapping confidence (default to 1.0 if not available)
        try:
            mapping_conf = float(field_data.get("mapping_confidence", 1.0))
            mapping_conf = max(0.0, min(1.0, mapping_conf))  # Clamp to [0, 1]
        except (TypeError, ValueError):
            mapping_conf = 1.0

        score += base_weight * mapping_conf

    return round(score, 2)


def render_results(
    results: List[Dict[str, Any]], fmt: str, *, include_header: bool = True
) -> str:
    if fmt == "json":
        return json.dumps(results, indent=2, ensure_ascii=False)
    if fmt == "csv":
        return _render_csv(results)
    if fmt == "curator_desk_csv":
        return _render_curator_desk_csv(results, include_header=include_header)
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


def _render_csv(results: List[Dict[str, Any]]) -> str:
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
    # Curator Desk spec §3.1 / §6.2: five prediction fields + ontology IDs + triage flags + priority.
    columns = [
        "PMID",
        "Title",
        "Journal",
        "Year",
        "Host Species",
        "Host Species ID",
        "Host Species Status",
        "Host Species Mapping Confidence",
        "Body Site",
        "Body Site ID",
        "Body Site Status",
        "Body Site Mapping Confidence",
        "Condition",
        "Condition ID",
        "Condition Status",
        "Condition Mapping Confidence",
        "Sequencing Type",
        "Sequencing Type Status",
        "Sequencing Type Raw",
        "Sample Size",
        "Sample Size Status",
        "has_differential_abundance",
        "differential_abundance_confidence",
        "in_bugsigdb",
        "Priority",
        "Summary",
        "Processing Time",
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
        try:
            conf = f"{float(r.get('differential_abundance_confidence', 0.0)):.2f}"
        except (TypeError, ValueError):
            conf = "0.00"
        try:
            proc_time = f"{float(r.get('processing_time', 0.0)):.2f}"
        except (TypeError, ValueError):
            proc_time = "0.00"
        w.writerow(
            {
                "PMID": pmid,
                "Title": r.get("title", ""),
                "Journal": r.get("journal", ""),
                "Year": _extract_year(r.get("year") or r.get("publication_date", "")),
                "Host Species": _field_val(fields, "host_species"),
                "Host Species ID": _field_ontology_id(fields, "host_species"),
                "Host Species Status": _status_normalise(
                    _field_val(fields, "host_species", "status")
                ),
                "Host Species Mapping Confidence": _field_mapping_confidence(
                    fields, "host_species"
                ),
                "Body Site": _field_val(fields, "body_site"),
                "Body Site ID": _field_ontology_id(fields, "body_site"),
                "Body Site Status": _status_normalise(
                    _field_val(fields, "body_site", "status")
                ),
                "Body Site Mapping Confidence": _field_mapping_confidence(
                    fields, "body_site"
                ),
                "Condition": _field_val(fields, "condition"),
                "Condition ID": _field_ontology_id(fields, "condition"),
                "Condition Status": _status_normalise(
                    _field_val(fields, "condition", "status")
                ),
                "Condition Mapping Confidence": _field_mapping_confidence(
                    fields, "condition"
                ),
                "Sequencing Type": _field_val(fields, "sequencing_type"),
                "Sequencing Type Status": _status_normalise(
                    _field_val(fields, "sequencing_type", "status")
                ),
                "Sequencing Type Raw": _sequencing_type_raw(fields),
                "Sample Size": _field_val(fields, "sample_size"),
                "Sample Size Status": _status_normalise(
                    _field_val(fields, "sample_size", "status")
                ),
                "has_differential_abundance": _bool_upper(
                    r.get("has_differential_abundance")
                ),
                "differential_abundance_confidence": conf,
                "in_bugsigdb": _bool_upper(r.get("in_bugsigdb")),
                "Priority": _priority_score(fields),
                "Summary": r.get("curation_summary", ""),
                "Processing Time": proc_time,
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
        "taxa_level": "TaxaLevel",
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
