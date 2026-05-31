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
                "fields": {
                    "host_species": {
                        "value": "Homo sapiens",
                        "status": "PRESENT",
                        "ontology_id": "NCBITaxon:9606",
                    },
                    "body_site": {
                        "value": "feces",
                        "status": "PRESENT",
                        "ontology_id": "UBERON:0001988",
                    },
                    "condition": {
                        "value": "Parkinson disease",
                        "status": "PRESENT",
                        "ontology_id": "EFO:0002508",
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
    assert row["has_differential_abundance"] == "TRUE"
    assert row["differential_abundance_confidence"] == "0.92"
    assert row["in_bugsigdb"] == "TRUE"
    assert "taxa_level" not in row
