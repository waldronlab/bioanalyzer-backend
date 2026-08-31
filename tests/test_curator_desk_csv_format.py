import csv
import io

from scripts.cli import BioAnalyzerCLI
from scripts.cli_rendering import render_results


def test_curator_desk_csv_header_and_core_fields():
    cli = BioAnalyzerCLI()
    csv_text = cli.get_curator_desk_csv_content(
        [
            {
                "pmid": "123",
                "title": "Test title",
                "journal": "Test journal",
                "publication_date": "2021-05-02",
                "has_differential_abundance": True,
                "differential_abundance_confidence": 0.92,
                "in_bugsigdb": True,
                "curation_summary": "Condition: Parkinson disease. Host: Homo sapiens.",
                "processing_time": 1.25,
                "fields": {
                    "host_species": {
                        "value": "Homo sapiens",
                        "status": "PRESENT",
                        "ontology_id": "NCBITaxon:9606",
                        "mapping_confidence": 1.0,
                        "mapping_tier": "auto",
                        "mapping_candidates": [],
                    },
                    "body_site": {
                        "value": "feces",
                        "status": "PRESENT",
                        "ontology_id": "UBERON:0001988",
                        "mapping_confidence": 1.0,
                        "mapping_tier": "auto",
                        "mapping_candidates": [],
                    },
                    "condition": {
                        "value": "Parkinson disease",
                        "status": "PRESENT",
                        "ontology_id": "EFO:0002508",
                        "mapping_confidence": 1.0,
                        "mapping_tier": "auto",
                        "mapping_candidates": [],
                    },
                    "sequencing_type": {"value": "16S", "status": "PRESENT"},
                    "sample_size": {"value": "98", "status": "PRESENT"},
                },
            }
        ]
    )

    rows = list(csv.DictReader(io.StringIO(csv_text.strip())))
    assert len(rows) == 1
    row = rows[0]

    assert row["PMID"] == "123"
    assert row["Year"] == "2021"
    assert row["Title"] == "Test title"
    assert row["Journal"] == "Test journal"
    assert row["Host Species"] == "Homo sapiens"
    assert row["Host Species Ontology ID"] == "NCBITaxon:9606"
    assert row["Host Species Ontology Candidates"] == ""
    assert row["Body Site"] == "feces"
    assert row["Body Site Ontology ID"] == "UBERON:0001988"
    assert row["Condition"] == "Parkinson disease"
    assert row["Condition Ontology ID"] == "EFO:0002508"
    assert row["Sample Size"] == "98"
    assert row["Sequencing Type"] == "16S"
    assert row["Differential Abundance"] == "Yes"
    assert row["In bsgdb"] == "Yes"
    assert row["Host Species Mapping Tier"] == "auto"
    assert row["Body Site Mapping Tier"] == "auto"
    assert row["Condition Mapping Tier"] == "auto"

    # Simplified curator-desk schema: no Status/Mapping-Confidence/Priority/
    # Summary/Processing Time/Sequencing Type Raw.
    for absent_col in (
        "Host Species Status",
        "Host Species Mapping Confidence",
        "Body Site Status",
        "Condition Status",
        "Sequencing Type Status",
        "Sequencing Type Raw",
        "Sample Size Status",
        "Priority",
        "Summary",
        "Processing Time",
    ):
        assert absent_col not in row


def test_curator_desk_csv_ontology_candidates_only_shown_when_not_auto():
    cli = BioAnalyzerCLI()
    csv_text = cli.get_curator_desk_csv_content(
        [
            {
                "pmid": "1",
                "title": "T1",
                "journal": "J1",
                "fields": {
                    "host_species": {
                        "value": "Mus musculus",
                        "status": "PARTIALLY_PRESENT",
                        "ontology_id": "NCBITaxon:10090",
                        "mapping_confidence": 0.9,
                        "mapping_tier": "review",
                        "mapping_candidates": [
                            {
                                "label": "Rattus norvegicus",
                                "ontology_id": "NCBITaxon:10116",
                            }
                        ],
                    },
                },
            },
            {
                "pmid": "2",
                "title": "T2",
                "journal": "J2",
                "fields": {
                    "host_species": {
                        "value": "Homo sapiens",
                        "status": "PRESENT",
                        "ontology_id": "NCBITaxon:9606",
                        "mapping_confidence": 1.0,
                        "mapping_tier": "auto",
                        "mapping_candidates": [],
                    },
                },
            },
        ]
    )

    rows = {r["PMID"]: r for r in csv.DictReader(io.StringIO(csv_text.strip()))}
    assert (
        rows["1"]["Host Species Ontology Candidates"]
        == "Rattus norvegicus|NCBITaxon:10116"
    )
    assert rows["2"]["Host Species Ontology Candidates"] == ""


def test_format_csv_is_an_alias_for_curator_desk_csv():
    """`--format csv` must be THE curator-facing schema, not a different,
    older format - this is the exact confusion (predictions.csv not matching
    curator_table_r's columns) that motivated collapsing the two names."""
    results = [
        {
            "pmid": "42",
            "title": "T",
            "journal": "J",
            "fields": {
                "host_species": {
                    "value": "Homo sapiens",
                    "status": "PRESENT",
                    "ontology_id": "NCBITaxon:9606",
                    "mapping_confidence": 1.0,
                    "mapping_tier": "auto",
                    "mapping_candidates": [],
                },
            },
        }
    ]
    assert render_results(results, "csv") == render_results(results, "curator_desk_csv")
    csv_cols = next(csv.DictReader(io.StringIO(render_results(results, "csv")))).keys()
    assert "Host Species Ontology ID" in csv_cols
    assert "Host Species Status" not in csv_cols


def test_curator_desk_csv_flags_ungrounded_condition_as_none_not_blank():
    """A condition label the LLM produced but nothing could ground to a real
    EFO/MONDO term (mapping_tier "none") must be visibly distinct from a
    field with no extraction attempt at all, not just an empty cell next to
    an empty Ontology ID column."""
    results = [
        {
            "pmid": "99",
            "title": "T",
            "journal": "J",
            "fields": {
                "condition": {
                    "value": "some rare unlisted disease",
                    "status": "PARTIALLY_PRESENT",
                    "ontology_id": "",
                    "mapping_confidence": 0.5,
                    "mapping_tier": "none",
                    "mapping_candidates": [],
                },
            },
        }
    ]
    row = next(csv.DictReader(io.StringIO(render_results(results, "csv"))))
    assert row["Condition"] == "some rare unlisted disease"
    assert row["Condition Ontology ID"] == ""
    assert row["Condition Mapping Tier"] == "none"
    # Fields with no mapping_tier key at all (sequencing_type/sample_size
    # never set one) still default to explicit "none", never a blank cell.
    assert row["Host Species Mapping Tier"] == "none"
    assert row["Body Site Mapping Tier"] == "none"


def test_render_table_shows_ungrounded_warning_only_for_ontology_fields():
    results = [
        {
            "pmid": "99",
            "title": "T",
            "journal": "J",
            "fields": {
                "condition": {
                    "value": "some rare unlisted disease",
                    "status": "PARTIALLY_PRESENT",
                    "ontology_id": "",
                    "mapping_tier": "none",
                },
                "host_species": {
                    "value": "Homo sapiens",
                    "status": "PRESENT",
                    "ontology_id": "NCBITaxon:9606",
                    "mapping_tier": "auto",
                },
                "sequencing_type": {"value": "16S", "status": "PRESENT"},
            },
        }
    ]
    table = render_results(results, "table")
    assert table.count("UNGROUNDED") == 1


def test_render_xml_includes_ontology_id_and_mapping_tier_for_ontology_fields_only():
    results = [
        {
            "pmid": "99",
            "title": "T",
            "journal": "J",
            "fields": {
                "condition": {
                    "value": "some rare unlisted disease",
                    "status": "PARTIALLY_PRESENT",
                    "ontology_id": "",
                    "mapping_tier": "none",
                },
                "sequencing_type": {"value": "16S", "status": "PRESENT"},
            },
        }
    ]
    xml = render_results(results, "xml")
    assert "<MappingTier>none</MappingTier>" in xml
    assert "<OntologyId>" in xml
    # sequencing_type has no ontology concept - no OntologyId/MappingTier
    # inside its own <SequencingType> block.
    seq_block = xml.split("<SequencingType>")[1].split("</SequencingType>")[0]
    assert "OntologyId" not in seq_block
    assert "MappingTier" not in seq_block


def test_format_detailed_csv_is_the_separate_status_inclusive_export():
    """--format detailed_csv is the older, distinct format kept only for
    scripts/eval/confusion_matrix_analysis.py - it must NOT match --format csv."""
    results = [
        {
            "pmid": "42",
            "title": "T",
            "journal": "J",
            "fields": {
                "host_species": {"value": "Homo sapiens", "status": "PRESENT"},
                "sequencing_type": {"value": "16S", "status": "PRESENT"},
            },
        }
    ]
    detailed = render_results(results, "detailed_csv")
    row = next(csv.DictReader(io.StringIO(detailed)))
    assert row["Host Species Status"] == "PRESENT"
    assert row["Sequencing Type"] == "16S"
    assert detailed != render_results(results, "csv")
