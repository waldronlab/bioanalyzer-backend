"""Headless checks of the Streamlit curator table (curator_table/app.py),
driving the real app through Streamlit's AppTest rather than re-testing a
copy of its logic."""

import ast
import csv
from pathlib import Path

import pytest

from app.normalization.sequencing_type import BUGSIGDB_SEQ_VOCAB

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = str(Path(__file__).resolve().parents[1] / "curator_table" / "app.py")

ROW = {
    "PMID": "123",
    "Year": "2021",
    "Title": "Test paper",
    "Journal": "Test journal",
    "Host Species": "Homo sapiens",
    "Host Species Ontology ID": "NCBITaxon:9606",
    "Body Site": "feces",
    "Body Site Ontology ID": "UBERON:0001988",
    "Condition": "Parkinson disease",
    "Condition Ontology ID": "MONDO:0005180",
    "Sample Size": "98",
    "Sequencing Type": "16S; WMS",
    "Differential Abundance": "Yes",
    "In bsgdb": "No",
}


def _load_app(tmp_path, monkeypatch, rows):
    monkeypatch.setenv("FEEDBACK_DIR", str(tmp_path / "feedback"))
    data = tmp_path / "predictions.csv"
    with open(data, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ROW))
        w.writeheader()
        w.writerows(rows)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Use file path").run()
    at.sidebar.text_input[0].input(str(data)).run()
    assert not at.exception, at.exception
    return at


def test_dataset_with_a_single_year_loads(tmp_path, monkeypatch):
    # st.slider raises when min == max, which used to crash the whole page
    # for any dataset whose papers all share one year (e.g. a daily batch).
    at = _load_app(tmp_path, monkeypatch, [ROW, {**ROW, "PMID": "456"}])
    assert not [s for s in at.sidebar.slider if s.label == "Year range"]


def test_sequencing_type_correction_is_a_bugsigdb_picklist(tmp_path, monkeypatch):
    at = _load_app(tmp_path, monkeypatch, [ROW])
    [pmid] = [s for s in at.selectbox if s.label.startswith("Select a PMID")]
    pmid.set_value("123").run()

    free_text = [t.label for t in at.text_input]
    assert "Curator value for Sequencing Type" not in free_text
    assert "Curator value for Host Species" in free_text
    [seq] = [
        m for m in at.multiselect if m.label == "Curator value for Sequencing Type"
    ]
    assert seq.options == ["16S", "18S", "WMS", "ITS / ITS2", "PCR"]

    # Picked out of vocabulary order: saved in it, as BioAnalyzer predicts.
    seq.set_value(["WMS", "16S"]).run()
    [curator] = [t for t in at.text_input if t.label == "Curator ID / initials"]
    curator.input("RO").run()
    [save] = [b for b in at.button if b.label == "Save feedback"]
    save.click().run()
    assert not at.exception, at.exception

    feedback = tmp_path / "feedback" / "curator_feedback.csv"
    rows = list(csv.DictReader(open(feedback, encoding="utf-8")))
    assert rows[-1]["true__Sequencing_Type"] == "16S; WMS"


def test_curator_table_sequencing_type_options_match_bugsigdb_vocab():
    # curator_table/app.py keeps its own copy of the list (it runs
    # standalone under Streamlit); parse it rather than import it, since
    # importing needs Streamlit and creates the feedback directory.
    for node in ast.parse(Path(APP).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "SEQUENCING_TYPE_VALUES" for t in node.targets
        ):
            assert ast.literal_eval(node.value) == BUGSIGDB_SEQ_VOCAB
            return
    pytest.fail("SEQUENCING_TYPE_VALUES not found in curator_table/app.py")
