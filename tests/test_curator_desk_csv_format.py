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
                    },
                    "body_site": {
                        "value": "feces",
                        "status": "PRESENT",
                        "ontology_id": "UBERON:0001988",
                        "mapping_confidence": 1.0,
                    },
                    "condition": {
                        "value": "Parkinson disease",
                        "status": "PRESENT",
                        "ontology_id": "EFO:0002508",
                        "mapping_confidence": 1.0,
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
    assert row["Title"] == "Test title"
    assert row["Journal"] == "Test journal"
    assert row["Year"] == "2021"
    assert row["Host Species"] == "Homo sapiens"
    assert row["Host Species ID"] == "NCBITaxon:9606"
    assert row["Host Species Status"] == "PRESENT"
    assert row["Host Species Mapping Confidence"] == "1.00"
    assert row["Body Site"] == "feces"
    assert row["Body Site ID"] == "UBERON:0001988"
    assert row["Body Site Status"] == "PRESENT"
    assert row["Condition"] == "Parkinson disease"
    assert row["Condition ID"] == "EFO:0002508"
    assert row["Condition Status"] == "PRESENT"
    assert row["Sequencing Type"] == "16S"
    assert row["Sequencing Type Status"] == "PRESENT"
    assert row["Sample Size"] == "98"
    assert row["Sample Size Status"] == "PRESENT"
    assert row["Summary"] == "Condition: Parkinson disease. Host: Homo sapiens."
    assert row["Processing Time"] == "1.25"
    assert row["has_differential_abundance"] == "TRUE"
    assert row["differential_abundance_confidence"] == "0.92"
    assert row["in_bugsigdb"] == "TRUE"
    # Spec §6.2: five prediction fields in curator-desk CSV (taxa_level is API-only)
    assert "Taxa Level" not in row
    assert "Taxa Level Status" not in row
    # "16S" came directly from the normalizer with no distinct raw text here.
    assert row["Sequencing Type Raw"] == ""


def test_curator_desk_csv_sequencing_type_raw_shown_only_when_it_differs():
    cli = BioAnalyzerCLI()
    csv_text = cli.get_curator_desk_csv_content(
        [
            {
                "pmid": "1",
                "title": "T1",
                "journal": "J1",
                "fields": {
                    "sequencing_type": {
                        "value": "other",
                        "status": "PRESENT",
                        "raw": "novel long-read chemistry",
                    },
                },
            },
            {
                "pmid": "2",
                "title": "T2",
                "journal": "J2",
                "fields": {
                    "sequencing_type": {
                        "value": "16S",
                        "status": "PRESENT",
                        "raw": "16S",
                    },
                },
            },
        ]
    )

    rows = {r["PMID"]: r for r in csv.DictReader(io.StringIO(csv_text.strip()))}
    assert rows["1"]["Sequencing Type"] == "other"
    assert rows["1"]["Sequencing Type Raw"] == "novel long-read chemistry"
    assert rows["2"]["Sequencing Type"] == "16S"
    assert rows["2"]["Sequencing Type Raw"] == ""
