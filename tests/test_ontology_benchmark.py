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
    try:
        real_home = pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        # Running as a UID with no /etc/passwd entry (e.g. a container
        # started with --user "$(id -u):$(id -g)", which docker-compose.yml
        # and run_tests.sh both do to avoid leaving root-owned files in the
        # bind-mounted repo) - getpwuid() has nothing to look up. Whatever
        # HOME the environment already provides is the best available
        # fallback; the corrupted-HOME scenario this test guards against
        # only matters when a passwd entry (a "real" answer to bypass to)
        # exists in the first place.
        real_home = os.environ.get("HOME", "/tmp")
    env = {**os.environ, "HOME": real_home}

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/eval/ontology_benchmark.py")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
