"""Tests for scripts/eval/bugsigdb_ground_truth_benchmark.py's Jaccard/IoU
scoring (added alongside the existing exact-match comparison to give
multi-value BugSigDB ground truth partial credit - see forensic_table.csv
classification "G" for the real-world pattern this targets).

Loaded via importlib.util.spec_from_file_location rather than a normal
package import: scripts/eval/ has no __init__.py (unlike scripts/ itself),
matching the fallback-loading pattern tests/conftest.py's
import_with_fallback() already uses elsewhere in this suite.
"""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "eval" / "bugsigdb_ground_truth_benchmark.py"

_spec = importlib.util.spec_from_file_location(
    "bugsigdb_ground_truth_benchmark", MODULE_PATH
)
gtb = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gtb
_spec.loader.exec_module(gtb)


class TestJaccard:
    def test_exact_match_is_full_credit(self):
        assert gtb._jaccard({"ibs"}, {"ibs"}) == 1.0

    def test_no_overlap_is_zero(self):
        assert gtb._jaccard({"ibs"}, {"copd"}) == 0.0

    def test_member_of_larger_ground_truth_set_is_partial_credit(self):
        # Single BioAnalyzer prediction correct, but BugSigDB curated 3
        # distinct condition values for this PMID (multi-experiment case).
        assert gtb._jaccard({"ibs"}, {"ibs", "copd", "asthma"}) == pytest.approx(1 / 3)

    def test_empty_union_is_zero_not_a_division_error(self):
        assert gtb._jaccard(set(), set()) == 0.0


class TestIoUTally:
    def test_mean_is_none_when_nothing_recorded(self):
        t = gtb.IoUTally("x")
        assert t.mean is None

    def test_mean_averages_recorded_scores(self):
        t = gtb.IoUTally("x")
        t.record(1.0)
        t.record(0.0)
        t.record(0.5)
        assert t.mean == pytest.approx(0.5)


class TestCompareFieldRecordsIoU:
    def test_label_and_id_branches_both_recorded(self):
        tallies = {}
        iou_tallies = {}
        discrepancies = []

        gtb._compare_field(
            "condition",
            tallies,
            iou_tallies,
            discrepancies,
            pmid="123",
            predicted_label="irritable bowel syndrome",
            ground_truth_labels={"irritable bowel syndrome", "ibs"},
            predicted_id="MONDO:0005052",
            ground_truth_ids={"MONDO:0005052"},
        )

        assert tallies["condition_label"].n_agree == 1
        assert iou_tallies["condition_label"].mean == pytest.approx(0.5)  # 1/2
        assert tallies["condition_ontology_id"].n_agree == 1
        assert iou_tallies["condition_ontology_id"].mean == pytest.approx(1.0)
        assert discrepancies == []

    def test_disagreement_still_records_zero_iou_not_skipped(self):
        tallies = {}
        iou_tallies = {}
        discrepancies = []

        gtb._compare_field(
            "condition",
            tallies,
            iou_tallies,
            discrepancies,
            pmid="123",
            predicted_label="asthma",
            ground_truth_labels={"irritable bowel syndrome"},
        )

        assert tallies["condition_label"].n_agree == 0
        assert iou_tallies["condition_label"].n_compared == 1
        assert iou_tallies["condition_label"].mean == pytest.approx(0.0)
        assert len(discrepancies) == 1

    def test_empty_ground_truth_skips_both_tallies(self):
        # Matches the existing exact-match gating: no comparison at all
        # when either side has nothing to compare.
        tallies = {}
        iou_tallies = {}
        discrepancies = []

        gtb._compare_field(
            "condition",
            tallies,
            iou_tallies,
            discrepancies,
            pmid="123",
            predicted_label="asthma",
            ground_truth_labels=set(),
        )

        assert tallies == {}
        assert iou_tallies == {}
        assert discrepancies == []


class TestCmdCompareWritesMeanIoU:
    def test_summary_csv_has_mean_iou_column_with_correct_values(self, tmp_path):
        predictions_csv = tmp_path / "predictions.csv"
        with open(predictions_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "PMID",
                    "Host Species",
                    "Body Site",
                    "Body Site Ontology ID",
                    "Condition",
                    "Condition Ontology ID",
                    "Sequencing Type",
                    "Sample Size",
                ],
            )
            w.writeheader()
            w.writerow(
                {
                    "PMID": "1",
                    "Host Species": "Homo sapiens",
                    "Body Site": "feces",
                    "Body Site Ontology ID": "UBERON:0001988",
                    "Condition": "irritable bowel syndrome",
                    "Condition Ontology ID": "MONDO:0005052",
                    "Sequencing Type": "16S",
                    "Sample Size": "40",
                }
            )

        ground_truth_json = tmp_path / "gt.json"
        ground_truth_json.write_text(
            json.dumps(
                {
                    "1": {
                        "host_species": ["homo sapiens"],
                        "body_site_labels": ["feces"],
                        "body_site_ids": ["UBERON:0001988"],
                        # Multi-experiment PMID: 3 distinct curated
                        # conditions, BioAnalyzer's single prediction
                        # matches one of them -> IoU should be 1/3.
                        "condition_labels": [
                            "irritable bowel syndrome",
                            "anxiety",
                            "depression",
                        ],
                        "condition_ids": ["MONDO:0005052"],
                        "sequencing_type": ["16s"],
                        "sample_size": [40],
                    }
                }
            )
        )

        outdir = tmp_path / "out"
        args = type(
            "Args",
            (),
            {
                "predictions": str(predictions_csv),
                "ground_truth": str(ground_truth_json),
                "output": str(outdir),
            },
        )()

        rc = gtb.cmd_compare(args)
        assert rc == 0

        with open(outdir / "summary.csv", encoding="utf-8") as f:
            rows = {row["field"]: row for row in csv.DictReader(f)}

        assert "mean_iou" in rows["condition_label"]
        # summary.csv rounds mean_iou to 3 decimals.
        assert float(rows["condition_label"]["mean_iou"]) == pytest.approx(
            1 / 3, abs=0.001
        )
        # condition_ontology_id: single ground-truth ID, exact match -> IoU 1.0
        assert float(rows["condition_ontology_id"]["mean_iou"]) == pytest.approx(1.0)

        summary_md = (outdir / "summary.md").read_text()
        assert "Jaccard / IoU" in summary_md
