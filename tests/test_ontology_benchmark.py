import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ontology_benchmark_meets_target():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/eval/ontology_benchmark.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
