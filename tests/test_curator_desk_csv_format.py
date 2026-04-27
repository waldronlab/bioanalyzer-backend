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
                "fields": {
                    "host_species": {"value": "Homo sapiens", "status": "PRESENT"},
                    "body_site": {"value": "feces", "status": "PRESENT"},
                    "condition": {"value": "Parkinson disease", "status": "PRESENT"},
                    "sequencing_type": {"value": "16S", "status": "PRESENT"},
                    "sample_size": {"value": "98", "status": "PRESENT"},
                    # extra fields should be ignored in curator_desk_csv
                    "taxa_level": {"value": "genus", "status": "PRESENT"},
                },
            }
        ]
    )

    lines = [line for line in csv_text.strip().splitlines() if line.strip()]
    assert len(lines) == 2

    header = lines[0].split(",")
    assert header[:16] == [
        "PMID",
        "Title",
        "Journal",
        "Year",
        "Host Species",
        "Host Species Status",
        "Body Site",
        "Body Site Status",
        "Condition",
        "Condition Status",
        "Sequencing Type",
        "Sequencing Type Status",
        "Sample Size",
        "Sample Size Status",
        "has_differential_abundance",
        "differential_abundance_confidence",
    ]

    row = lines[1].split(",")
    assert row[0] == "123"
    assert row[1] == "Test title"
    assert row[2] == "Test journal"
    assert row[3] == "2021"
    assert row[4] == "Homo sapiens"
    assert row[5] == "PRESENT"
    assert row[6] == "feces"
    assert row[7] == "PRESENT"
    assert row[8] == "Parkinson disease"
    assert row[9] == "PRESENT"
    assert row[10] == "16S"
    assert row[11] == "PRESENT"
    assert row[12] == "98"
    assert row[13] == "PRESENT"
    assert row[14] == "True"
