import csv
import io

from scripts.cli import BioAnalyzerCLI


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
                    "taxa_level": {"value": "genus", "status": "PRESENT"},
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

    # Simplified curator-desk schema: no Status/Mapping-Confidence/Priority/
    # Summary/Processing Time/Sequencing Type Raw, and Taxa Level stays API-only.
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
        "Taxa Level",
        "Taxa Level Status",
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
