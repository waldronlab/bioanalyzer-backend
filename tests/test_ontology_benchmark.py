import os
import pwd
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ontology_benchmark_meets_target():
    # app.services.agent_orchestrator overwrites os.environ["HOME"] at import
    # time (to sandbox PaperQA's directory resolution) and never restores it.
    # If any test collected earlier in this session imported that module,
    # HOME is left pointing at a temp dir for the rest of the process —
    # which breaks this subprocess's ability to find packages installed
    # under the real user site-packages (e.g. pydantic). Look up the real
    # home directory via the user database directly, bypassing whatever
    # os.environ["HOME"] currently holds, so this test doesn't depend on
    # import order elsewhere in the suite.
    real_home = pwd.getpwuid(os.getuid()).pw_dir
    env = {**os.environ, "HOME": real_home}

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/eval/ontology_benchmark.py")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
