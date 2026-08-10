#!/usr/bin/env python3
"""
BioAnalyzer CLI - User-Friendly Command Line Interface
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

if TYPE_CHECKING:
    from app.core.settings import BioAnalyzerSettings

import requests

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None  # type: ignore

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.cli_rendering import (  # noqa: E402
    ANALYSIS_FIELDS,
    render_results,
    render_retrieval,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Single source of truth: the compose project, the image, and the container
# all currently share this name. Kept as one constant instead of three
# independently-typed literals so they can't silently drift apart.
APP_NAME = "bioanalyzer-package"
COMPOSE_PROJECT_NAME = APP_NAME


def _read_existing_pmids(path: Path) -> set[str]:
    """Return the set of PMIDs already present in a curator-desk CSV file
    (--format csv / curator_desk_csv).

    The output file IS the de-duplication manifest: there's no separate
    persisted state to drift out of sync with it. Deleting the file simply
    starts a clean slate on the next run.
    """
    if not path.exists():
        return set()
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return {
                (row.get("PMID") or "").strip()
                for row in csv.DictReader(f)
                if (row.get("PMID") or "").strip()
            }
    except Exception:
        return set()


class BioAnalyzerCLI:
    """User-friendly Command Line Interface for BioAnalyzer."""

    REQUIRED_ENV = ["GEMINI_API_KEY", "NCBI_API_KEY", "EMAIL"]
    OPTIONAL_ENV = [
        "API_TIMEOUT",
        "NCBI_RATE_LIMIT_DELAY",
        "USE_FULLTEXT",
        "LOG_LEVEL",
        "UVICORN_RELOAD",
    ]

    def __init__(self) -> None:
        self.container_name = APP_NAME
        self.image_name = APP_NAME
        self.verbose = False
        self.api_base_url = os.getenv(
            "BIOANALYZER_API_URL", "http://localhost:8000/api/v1"
        )
        # Reused across every HTTP call this instance makes so repeated
        # requests to the same host (health checks, per-PMID analysis
        # fetches, polling) get connection keep-alive instead of a fresh
        # TCP/TLS handshake each time.
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    def _env_file_path(self) -> str | None:
        p = project_root / ".env"
        return str(p.resolve()) if p.exists() else None

    def _env_file_values(self) -> dict[str, str]:
        env_file = self._env_file_path()
        if not env_file or dotenv_values is None:
            return {}
        return {k: v for k, v in (dotenv_values(env_file) or {}).items() if v}

    def _collect_env_flags(self) -> list[str]:
        flags: list[str] = []
        env_file = self._env_file_path()
        if env_file:
            flags += ["--env-file", env_file]
        for key in self.REQUIRED_ENV + self.OPTIONAL_ENV:
            val = os.environ.get(key)
            if val:
                flags += ["-e", f"{key}={val}"]
        return flags

    def _validate_environment(self) -> None:
        file_vals = self._env_file_values()
        missing = [
            k
            for k in self.REQUIRED_ENV
            if not os.environ.get(k) and not file_vals.get(k)
        ]
        if missing:
            print("⚠️  Missing critical environment variables:")
            for k in missing:
                print(f"   - {k}")

    def _build_api_url(self, path: str) -> str:
        return f"{self.api_base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _emit(content: str, output_file: str | None, label: str = "Saved to") -> None:
        """Write `content` to `output_file` if given, else print it."""
        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
            print(f"💾 {label}: {output_file}")
        else:
            print(content)

    # ------------------------------------------------------------------
    # Docker helpers
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, capture_output=True, text=True, check=False, **kwargs
        )

    def check_docker(self) -> bool:
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Docker is not installed or not available.")
            return False

    def check_image(self) -> bool:
        return (
            self._run(["docker", "image", "inspect", self.image_name]).returncode == 0
        )

    def _compose_cmd(self) -> list[str]:
        if self._run(["which", "docker-compose"]).stdout.strip():
            return ["docker-compose"]
        return ["docker", "compose"]

    def _is_container_running(self) -> bool:
        return bool(
            self._run(
                ["docker", "ps", "--filter", f"name={self.container_name}", "-q"]
            ).stdout.strip()
        )

    def _ensure_volume_directories(self) -> bool:
        # Must match docker-compose.yml's bind-mounted host directories
        # exactly. Any left off this list that don't already exist get
        # auto-created by the Docker daemon on first `docker compose up` -
        # as root, regardless of the "${UID:-1000}:${GID:-1000}" the
        # container itself runs as - which then makes that same directory
        # permission-denied for this (non-root) container from then on.
        # Pre-creating them here, owned by whoever runs this CLI, avoids
        # that entirely.
        for name in ["cache", "logs", "results", "models", "ontology_store"]:
            path = project_root / name
            try:
                path.mkdir(parents=True, exist_ok=True)
                test = path / ".write_test"
                test.write_text("")
                test.unlink()
            except OSError as e:
                print(f"❌ Directory issue ({path}): {e}")
                return False
        return True

    def check_backend_health(self) -> bool:
        try:
            return (
                self._session.get("http://localhost:8000/health", timeout=5).status_code
                == 200
            )
        except Exception:
            return False

    def _wait_for_health(self, timeout: int = 60, interval: float = 2) -> bool:
        deadline = time.time() + timeout
        print(f"⏳ Waiting for API health (timeout: {timeout}s)...")
        while time.time() < deadline:
            if self.check_backend_health():
                return True
            time.sleep(max(0.5, interval))
        return False

    # ------------------------------------------------------------------
    # Lifecycle commands
    # ------------------------------------------------------------------

    def build_containers(self) -> bool:
        print("🔨 Building BioAnalyzer containers...")
        if not self.check_docker():
            return False
        try:
            subprocess.run(
                ["docker", "build", "-t", self.image_name, "."],
                cwd=project_root,
                check=True,
            )
            print("✅ All containers built successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error building containers: {e}")
            return False

    def start_application(self) -> bool:
        print("🚀 Starting BioAnalyzer application...")
        if not self.check_docker():
            return False
        if not self.check_image():
            print("❌ Docker image not found. Building first...")
            if not self.build_containers():
                return False
        self._validate_environment()
        if not (project_root / "docker-compose.yml").exists():
            print("❌ docker-compose.yml not found.")
            return False
        if not self._ensure_volume_directories():
            return False
        if self.check_backend_health():
            print("✅ API already running at http://localhost:8000")
            return True

        compose = self._compose_cmd()
        containers_up = bool(
            self._run(
                compose + ["-p", COMPOSE_PROJECT_NAME, "ps", "-q"],
                cwd=str(project_root),
            ).stdout.strip()
        )
        if containers_up and not self.check_backend_health():
            subprocess.run(
                compose + ["-p", COMPOSE_PROJECT_NAME, "down", "--remove-orphans"],
                cwd=str(project_root),
                capture_output=True,
            )

        env = os.environ.copy()
        try:
            # grp/pwd are POSIX-only; imported here (not at module level) so
            # that merely loading this file doesn't fail on platforms that
            # lack them - only this UID/GID mapping feature is affected.
            import grp
            import pwd

            env["UID"] = str(pwd.getpwuid(os.getuid()).pw_uid)
            env["GID"] = str(grp.getgrgid(os.getgid()).gr_gid)
        except Exception:
            env["UID"] = str(os.getuid())
            env["GID"] = str(os.getgid())

        up_cmd = compose + ["-p", COMPOSE_PROJECT_NAME, "up", "-d", "--remove-orphans"]
        if containers_up:
            up_cmd.append("--force-recreate")
        subprocess.run(up_cmd, cwd=str(project_root), env=env, check=False)

        if self._wait_for_health(60):
            print("✅ API running at http://localhost:8000")
            print("\n🎉 BioAnalyzer backend is running!")
            print(
                "🔧 API: http://localhost:8000  |  📖 Docs: http://localhost:8000/docs"
            )
            return True
        else:
            print("\n⚠️  Container started but health check timed out after 60s.")
            print("📋 Last 40 lines of container logs:")
            subprocess.run(
                ["docker", "logs", "--tail", "40", self.container_name],
                cwd=str(project_root),
            )
            print("\n❌ BioAnalyzer failed to start. Fix the errors above and retry.")
            return False

    def stop_application(self) -> bool:
        print("🛑 Stopping BioAnalyzer application...")
        compose = self._compose_cmd()
        if (project_root / "docker-compose.yml").exists():
            subprocess.run(
                compose + ["-p", COMPOSE_PROJECT_NAME, "down", "--remove-orphans"],
                cwd=str(project_root),
                capture_output=True,
            )
            if self._is_container_running():
                subprocess.run(
                    compose + ["-p", project_root.name, "down", "--remove-orphans"],
                    cwd=str(project_root),
                    capture_output=True,
                )
        if self._is_container_running():
            for name in (self.container_name, "bioanalyzer-redis"):
                self._run(["docker", "rm", "-f", name])
        print("✅ BioAnalyzer application stopped")
        return True

    def restart_application(self) -> bool:
        print("🔄 Restarting BioAnalyzer application...")
        self.stop_application()
        time.sleep(2)
        return self.start_application()

    def run_table(self, port: int = 8501) -> bool:
        app_path = project_root / "curator_table" / "app.py"
        if not app_path.exists():
            print(f"❌ Curator table app not found: {app_path}")
            return False
        if not self.check_docker() or not self.check_image():
            return False
        print(f"📋 Starting Curator Table → http://localhost:{port}  (Ctrl+C to stop)")
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{project_root}:/app",
            "-w",
            "/app",
            "-p",
            f"{port}:8501",
            *self._collect_env_flags(),
            self.image_name,
            "streamlit",
            "run",
            "curator_table/app.py",
            "--server.port=8501",
            "--server.address=0.0.0.0",
        ]
        return subprocess.run(cmd, cwd=project_root).returncode == 0

    def get_system_status(self) -> None:
        print("📊 BioAnalyzer System Status\n" + "=" * 40)
        ok = self.check_docker()
        print(f"Docker:          {'✅ Available' if ok else '❌ Not Available'}")
        if not ok:
            return
        print(
            f"Package Image:   {'✅ Built' if self.check_image() else '❌ Not Built'}"
        )
        running = self._is_container_running()
        print(f"Container:       {'✅ Running' if running else '❌ Stopped'}")
        healthy = self.check_backend_health()
        print(f"API Health:      {'✅ Healthy' if healthy else '❌ Not Responding'}")
        if healthy:
            print("🔧 http://localhost:8000  |  📖 http://localhost:8000/docs")
        elif not running:
            print("\n💡 Run: BioAnalyzer start")

    # ------------------------------------------------------------------
    # PMID file loader
    # ------------------------------------------------------------------

    def load_pmids_from_file(self, file_path: str) -> list[str]:
        ext = Path(file_path).suffix.lower()
        if ext in [".xls", ".xlsx"]:
            return self._read_excel_via_docker(file_path)
        if ext == ".csv":
            with open(file_path, encoding="utf-8") as f:
                return [
                    row[0].strip() for row in csv.reader(f) if row and row[0].strip()
                ]
        pmids: list[str] = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    pmids.extend(p.strip() for p in line.split(",") if p.strip())
        return pmids

    def _read_excel_via_docker(self, file_path: str) -> list[str]:
        file_path_obj = Path(file_path).resolve()
        if not self.check_docker() or not self.check_image():
            raise Exception(
                "Docker image required to read Excel files. Run 'BioAnalyzer build'."
            )
        # The filename is attacker-controllable in principle (it's whatever
        # the --file argument's basename is) and gets embedded in a Python
        # source string passed to `python -c` below - use json.dumps() to
        # produce a properly quote-escaped Python string literal instead of
        # raw concatenation, which would let a filename containing a quote
        # break out of the literal and inject arbitrary code.
        safe_filename_literal = json.dumps(file_path_obj.name)
        script = (
            "import pandas as pd, sys, json, re\n"
            "def normalize(v):\n"
            "    if pd.isna(v): return None\n"
            "    if isinstance(v, (int, float)):\n"
            "        return str(int(v)) if float(v).is_integer() else None\n"
            "    raw = str(v).strip()\n"
            "    if re.fullmatch(r'\\d+\\.0+', raw): return raw.split('.')[0]\n"
            "    return raw if re.fullmatch(r'\\d+', raw) else None\n"
            "df = pd.read_excel('/workspace/' + " + safe_filename_literal + ")\n"
            "best, best_score = [], -1\n"
            "for col in df.columns:\n"
            "    pmids = [p for p in (normalize(v) for v in df[col]) if p and len(p) >= 6]\n"
            "    score = len(pmids) + (100000 if 'pmid' in str(col).lower() else 0)\n"
            "    if score > best_score: best_score, best = score, pmids\n"
            "if not best: raise ValueError('No valid PMIDs found.')\n"
            "seen, out = set(), []\n"
            "for p in best:\n"
            "    if p not in seen: seen.add(p); out.append(p)\n"
            "print(json.dumps(out))\n"
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{file_path_obj.parent}:/workspace",
                "-w",
                "/workspace",
                self.image_name,
                "python",
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # subprocess.CalledProcessError's default str() omits stderr, which
            # hides the actual pandas/Python error - raise with it included.
            raise RuntimeError(
                f"Failed to read Excel file in container: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return json.loads(result.stdout.strip())

    def get_curator_desk_csv_content(self, results: list[dict[str, Any]]) -> str:
        return render_results(results, "curator_desk_csv")

    # ------------------------------------------------------------------
    # PubMed discovery search
    # ------------------------------------------------------------------

    def search_pubmed(
        self,
        query: str | None = None,
        preset: str = "discovery",
        max_results: int = 100,
        fmt: str = "txt",
        output_file: str | None = None,
    ) -> list[str]:
        from app.services.pubmed_queries import (
            RECOMMENDED_DISCOVERY_QUERY,
            SEARCH_PRESETS,
        )
        from app.services.data_retrieval import PubMedRetriever

        term = (
            query.strip()
            if query
            else SEARCH_PRESETS.get(preset, RECOMMENDED_DISCOVERY_QUERY)
        )
        api_key = os.environ.get("NCBI_API_KEY") or self._env_file_values().get(
            "NCBI_API_KEY", ""
        )
        retriever = PubMedRetriever(api_key=api_key or None)
        print(f"🔍 PubMed search (preset={preset}, max={max_results})...")
        pmids = retriever.search(term, max_results=max_results)
        if not pmids:
            print("❌ No PMIDs returned.")
            return []
        print(f"✅ Found {len(pmids)} PMID(s)")
        if fmt == "json":
            content = json.dumps(
                {"query": term, "preset": preset, "pmids": pmids}, indent=2
            )
        elif fmt == "csv":
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["PMID"])
            for p in pmids:
                w.writerow([p])
            content = out.getvalue()
        else:
            content = "\n".join(pmids) + "\n"
        self._emit(content, output_file, "PMIDs saved to")
        return pmids

    # ------------------------------------------------------------------
    # Analysis commands
    # ------------------------------------------------------------------

    def _fetch_analysis(
        self,
        pmid: str,
        refresh: bool,
        request_timeout: int,
        *,
        retry_wait: float = 5.0,
    ):
        """GET /api/v1/analyze/{pmid}, waiting out the API's own 60-req/min
        rate limiter (app/api/middleware/rate_limit.py) instead of treating
        a 429 as a permanent failure. Retries on 429 are unbounded by design
        (a batch of any size - even far more than 60 PMIDs - should always
        run to completion, just pausing whenever it hits the cap) since 429
        is a distinct, reliable signal here: it can no longer be confused
        with a genuine server error now that the rate-limit middleware
        returns it directly instead of via `raise HTTPException` (which used
        to get silently flattened into a 500 by the app's catch-all handler,
        see app/api/middleware/rate_limit.py). Any other error status still
        fails immediately, same as before.

        Returns (result_dict, None) on success, or (None, error_message).
        """
        attempt = 0
        while True:
            try:
                r = self._session.get(
                    self._build_api_url(f"/analyze/{pmid}"),
                    params={"refresh": "true"} if refresh else None,
                    timeout=request_timeout,
                )
            except Exception as e:
                return None, str(e)
            if r.status_code == 200:
                return r.json(), None
            if r.status_code == 429:
                attempt += 1
                print(
                    f"   ⏳ Rate limited, waiting {retry_wait:.0f}s before retry ({attempt})..."
                )
                time.sleep(retry_wait)
                continue
            try:
                detail = r.json().get("detail", "Unknown error")
            except Exception:
                detail = f"HTTP {r.status_code}"
            return None, detail

    def analyze_papers(
        self,
        pmids: list[str],
        fmt: str = "table",
        output_file: str | None = None,
        refresh: bool = False,
    ) -> None:
        request_timeout = int(os.getenv("BIOANALYZER_ANALYZE_TIMEOUT", "180"))

        # Cumulative output: when re-running against the same curator-desk CSV
        # file (--format csv or its curator_desk_csv alias), skip both
        # re-analysis and re-emission for PMIDs it already contains. The file
        # itself is the de-duplication manifest — there is no separate state
        # to drift out of sync with it, so deleting the file simply starts a
        # clean slate on the next run. --refresh bypasses this (and
        # overwrites, like before) for an intentional full redo.
        append_mode = False
        out_path = Path(output_file) if output_file else None
        if fmt in ("csv", "curator_desk_csv") and out_path is not None and not refresh:
            already_emitted = _read_existing_pmids(out_path)
            if already_emitted:
                skipped = [p for p in pmids if p in already_emitted]
                pmids = [p for p in pmids if p not in already_emitted]
                if skipped:
                    print(
                        f"⏭️  Skipping {len(skipped)} PMID(s) already in "
                        f"{out_path} (use --refresh to redo)"
                    )
                append_mode = True

        if append_mode and not pmids:
            print("✅ Nothing new to add — all PMIDs already present.")
            return

        results, total = [], len(pmids)
        print(f"🔬 Analysing {total} paper(s)...")
        for i, pmid in enumerate(pmids, 1):
            print(f"[{i}/{total}] PMID: {pmid}")
            data, err = self._fetch_analysis(pmid, refresh, request_timeout)
            if data is not None:
                results.append(data)
                print("✅ Done")
            else:
                print(f"❌ {err}")
        if not results:
            print("❌ No results obtained.")
            return
        content = render_results(results, fmt, include_header=not append_mode)
        if output_file:
            if append_mode:
                with open(output_file, "a", encoding="utf-8", newline="") as f:
                    f.write(content)
            else:
                Path(output_file).write_text(content, encoding="utf-8")
            print(f"💾 Results saved to: {output_file}")
        else:
            print(content)

    # ------------------------------------------------------------------
    # URL analysis
    # ------------------------------------------------------------------

    def handle_url_analysis(
        self,
        urls: list[str],
        file_path: str | None,
        embedding_model: str,
        llm_model: str,
        fmt: str,
        output_file: str | None,
        poll_interval: int,
        timeout: int,
    ) -> None:
        all_urls = self._collect_urls(urls, file_path)
        if not all_urls:
            print("❌ No URLs provided.")
            return
        results = []
        for i, url in enumerate(all_urls, 1):
            print(f"\n[{i}/{len(all_urls)}] {url}")
            job_id = self._start_url_job(url, embedding_model, llm_model)
            if job_id:
                result = self._poll_url_job(job_id, poll_interval, timeout)
                if result:
                    result["job_id"] = job_id
                    results.append(result)
        if not results:
            print("❌ No URL analyses completed.")
            return
        content = self._render_url_results(results, fmt)
        self._emit(content, output_file)

    def _collect_urls(self, inline: list[str], file_path: str | None) -> list[str]:
        urls: list[str] = []
        for v in inline or []:
            urls.extend(v.split(",") if "," in v else [v])
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as f:
                    urls.extend(line.strip() for line in f if line.strip())
            except Exception as e:
                print(f"❌ Error reading URL file: {e}")
        stripped = [u.strip() for u in urls if u.strip()]
        return _dedup(stripped)

    def _start_url_job(self, url: str, emb: str, llm: str) -> str | None:
        try:
            r = self._session.post(
                self._build_api_url("/analyze-url"),
                json={"url": url, "embedding_model": emb, "llm_model": llm},
                timeout=30,
            )
            if r.status_code == 200:
                job_id = r.json().get("job_id")
                print(f"🆔 Job ID: {job_id}")
                return job_id
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            print(f"❌ {detail}")
        except requests.RequestException as e:
            print(f"❌ Network error: {e}")
        return None

    def _poll_url_job(self, job_id: str, interval: int, timeout: int) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = self._session.get(
                    self._build_api_url(f"/analysis-status/{job_id}"), timeout=15
                ).json()
                state = status.get("status")
                print(f"   ⏳ {state} ({status.get('progress', '')})")
                if state == "completed":
                    r = self._session.get(
                        self._build_api_url(f"/analysis-result/{job_id}"), timeout=30
                    )
                    return r.json() if r.status_code == 200 else None
                if state == "failed":
                    print(f"❌ Failed: {status.get('error', '')}")
                    return None
                time.sleep(max(1, interval))
            except Exception as e:
                print(f"❌ Poll error: {e}")
                time.sleep(max(1, interval))
        print(f"⚠️  Job {job_id} timed out.")
        return None

    def _render_url_results(self, results: list[dict], fmt: str) -> str:
        if fmt == "json":
            return json.dumps(results, indent=2, ensure_ascii=False)
        lines = [
            "\n" + "=" * 80,
            "🌐 BIOANALYZER - URL STUDY ANALYSIS RESULTS",
            "=" * 80,
        ]
        for r in results:
            lines += [
                f"\n🔗 {r.get('source_url', 'N/A')}",
                f"🆔 Job: {r.get('job_id', 'N/A')}",
                f"🧪 Experiments: {len(r.get('experiments', []))}",
                f"✅ Curation Ready: {'Yes' if r.get('curation_ready') else 'No'}",
                f"⚠️  Missing: {', '.join(r.get('missing_fields', [])) or 'None'}",
                "-" * 60,
            ]
            for exp in r.get("experiments", []):
                m = exp.get("metadata", {})
                lines += [
                    f"   • {exp.get('title', 'Untitled')}",
                    f"     Species: {m.get('host_species', 'N/A')}  Site: {m.get('body_site', 'N/A')}",
                    f"     Condition: {m.get('condition', 'N/A')}  Seq: {m.get('sequencing_type', 'N/A')}",
                    f"     N: {m.get('sample_size', 'N/A')}",
                    f"     Signatures: {len(exp['signatures']) if exp.get('signatures') else 'None'}",
                    "",
                ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve_papers(
        self,
        pmids: list[str],
        fmt: str = "table",
        output_file: str | None = None,
        save: bool = False,
    ) -> None:
        retriever = self._get_retriever()
        total = len(pmids)
        print(f"📥 Retrieving {total} paper(s)...")
        results = []
        for i, pmid in enumerate(pmids, 1):
            try:
                data = retriever.get_full_paper_data(pmid)
            except Exception as e:
                data = {
                    "pmid": pmid,
                    "error": str(e),
                    "retrieval_timestamp": time.time(),
                }
            print(f"[{i}/{total}] PMID {pmid}: {'✅' if 'error' not in data else '❌'}")
            if save and "error" not in data:
                self._save_paper(data)
            results.append(data)
        content = render_retrieval(results, fmt)
        self._emit(content, output_file)

    def _get_retriever(self):
        try:
            from app.services.standalone_pubmed_retriever import (
                StandalonePubMedRetriever,
            )

            return StandalonePubMedRetriever()
        except ImportError:
            return self._fallback_retriever()

    def _fallback_retriever(self):
        session = self._session

        class _R:
            def get_full_paper_data(self, pmid: str) -> dict:
                try:
                    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                    r = session.get(
                        url,
                        params={
                            "db": "pubmed",
                            "id": pmid,
                            "retmode": "xml",
                            "email": "bioanalyzer@example.com",
                            "tool": "BioAnalyzer",
                        },
                        timeout=10,
                    )
                    r.raise_for_status()
                    root = ElementTree.fromstring(r.text)
                    art = root.find(".//PubmedArticle/MedlineCitation/Article")
                    if art is None:
                        return {"pmid": pmid, "error": "No article found"}
                    return {
                        "pmid": pmid,
                        "title": art.findtext("ArticleTitle", "N/A"),
                        "abstract": "",
                        "journal": art.findtext("Journal/Title", "N/A"),
                        "authors": [],
                        "publication_date": "",
                        "full_text": "",
                        "has_full_text": False,
                        "retrieval_timestamp": time.time(),
                    }
                except Exception as e:
                    return {
                        "pmid": pmid,
                        "error": str(e),
                        "retrieval_timestamp": time.time(),
                    }

        return _R()

    def _save_paper(self, data: dict) -> str:
        try:
            pmid = data.get("pmid", "unknown")
            fp = (
                project_root
                / "results"
                / f"paper_{pmid}_{time.strftime('%Y%m%d_%H%M%S')}.json"
            )
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"   💾 {fp}")
            return str(fp)
        except Exception as e:
            print(f"   ❌ Save error: {e}")
            return ""

    # ------------------------------------------------------------------
    # Q&A
    # ------------------------------------------------------------------

    def ask_question(self, question: str) -> str | None:
        if not self.check_backend_health():
            print("⚠️  API not running. Start with: BioAnalyzer start")
            return None
        try:
            print("🤔 Thinking...")
            r = self._session.post(
                self._build_api_url("/qa"),
                json={"question": question},
                timeout=60,
            )
            if r.status_code == 200:
                payload = r.json()
                answer = payload.get("answer") or payload.get("text", "")
                conf = payload.get("confidence", 0.8)
                if answer:
                    print(
                        f"\n💡 Answer (confidence: {conf:.2f}):\n{'-'*60}\n{answer}\n{'-'*60}"
                    )
                    return answer
            elif r.status_code == 404:
                print("⚠️  Q&A endpoint not available yet.")
            else:
                try:
                    detail = r.json().get("detail", "Unknown")
                except ValueError:
                    detail = "Unknown"
                print(f"❌ API error: {detail}")
        except Exception as e:
            print(f"❌ {e}")
        return None

    def interactive_qa(self) -> None:
        self.print_banner()
        if not self.check_backend_health():
            print("⚠️  Start BioAnalyzer first: BioAnalyzer start")
            return
        print("💬 Interactive Q&A  (type 'quit' to exit)\n")
        while True:
            try:
                q = input("Q> ").strip()
                if q.lower() in ("quit", "exit", "q"):
                    break
                if q:
                    self.ask_question(q)
            except KeyboardInterrupt:
                break
        print("👋 Goodbye!")

    # ------------------------------------------------------------------
    # Fields info
    # ------------------------------------------------------------------

    def show_fields_info(self) -> None:
        print("\n🧬 BioAnalyzer - BugSigDB Essential Fields\n" + "=" * 42)
        descriptions = {
            "host_species": "Host organism (e.g. Human, Mouse, Rat)",
            "body_site": "Sample location (e.g. Gut, Oral, Skin)",
            "condition": "Disease, treatment, or exposure studied",
            "sequencing_type": "Molecular method (e.g. 16S, metagenomics)",
            "sample_size": "Number of samples / participants",
        }
        for key, label in ANALYSIS_FIELDS.items():
            print(f"  🔹 {label}: {descriptions[key]}")
        print("\n✅ PRESENT  ⚠️ PARTIALLY_PRESENT  ❌ ABSENT\n")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def handle_settings_command(self, args: argparse.Namespace) -> None:
        try:
            from app.core.settings import BioAnalyzerSettings, SettingsManager
        except ImportError as e:
            print(f"❌ Failed to import settings module: {e}")
            return
        manager = SettingsManager()
        cmd = args.settings_command
        if cmd == "view":
            settings = manager.load()
            out = (
                settings.model_dump_json(indent=2)
                if args.format == "json"
                else self._format_settings_table(settings)
            )
            if args.output:
                Path(args.output).write_text(out)
                print(f"✅ Written to {args.output}")
            else:
                print(out)
        elif cmd == "save":
            settings = (
                BioAnalyzerSettings.from_preset(args.preset)
                if args.preset
                else manager.load()
            )
            fp = Path(args.file) if args.file else manager.DEFAULT_SETTINGS_FILE
            manager.save(settings, fp, args.format)
            print(f"✅ Saved to {fp}")
        elif cmd == "load":
            fp = Path(args.file)
            if not fp.exists():
                print(f"❌ File not found: {fp}")
                return
            settings = BioAnalyzerSettings.from_file(fp)
            print(f"✅ Loaded from {fp}")
            if args.apply:
                settings.apply_to_environment()
                print("✅ Applied to environment")
        elif cmd == "preset":
            settings = BioAnalyzerSettings.from_preset(args.name)
            if args.save:
                manager.save(settings)
                print(f"✅ Preset '{args.name}' saved")
            else:
                print(self._format_settings_table(settings))
        elif cmd == "migrate":
            old = Path(args.file)
            if not old.exists():
                print(f"❌ Not found: {old}")
                return
            out = (
                Path(args.output)
                if args.output
                else old.with_suffix(".new" + old.suffix)
            )
            manager.migrate_settings(old, out)
            print(f"✅ Migrated → {out}")

    def _format_settings_table(self, settings: BioAnalyzerSettings) -> str:
        s = settings
        lines = [
            "=" * 60,
            "BioAnalyzer Settings",
            "=" * 60,
            f"Version: {s.version}  |  Env: {s.environment.value}",
            f"\n🔌 API  timeout={s.api.timeout}s  analysis={s.api.analysis_timeout}s  "
            f"gemini={s.api.gemini_timeout}s  max_req={s.api.max_concurrent_requests}",
            f"🤖 LLM  provider={s.llm.provider or 'auto'}  model={s.llm.model or 'default'}",
            f"📚 RAG  enabled={s.rag.enabled}  top_k={s.rag.top_k_chunks}  "
            f"rerank={s.rag.rerank_method.value}  cache={s.rag.use_cache}",
            f"💾 Cache  enabled={s.cache.enabled}  ttl={s.cache.validity_hours}h  "
            f"max={s.cache.max_size}  dir={s.cache.directory}",
            f"📝 Log  level={s.logging.level.value}  dir={s.logging.directory}",
            "=" * 60,
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Banner / help
    # ------------------------------------------------------------------

    def print_banner(self) -> None:
        print("\n🧬 ============================================= 🧬")
        print("   BioAnalyzer - Curatable Signature Analysis Tool")
        print("🧬 ============================================= 🧬\n")

    def print_help(self) -> None:
        self.print_banner()
        print(
            """📋 COMMANDS
  build / start / stop / restart / status
  run table [--port N]
  search [--preset discovery|broad|precision] [-n N] [-o FILE] [--query Q]
  analyze <pmid|pmids>  [--file F] [--format table|json|csv|detailed_csv|xml] [-o FILE]
  analyze-url <url>     [--file F] [--format table|json] [-o FILE]
  retrieve <pmid|pmids> [--file F] [--format table|json|csv] [-o FILE] [--save]
  qa [question]         [--interactive]
  fields
  settings view|save|load|preset|migrate

  --format csv is the curator-facing CSV matching curator_table_r/
  curator_table exactly (curator_desk_csv is an accepted alias for the same
  thing). --format detailed_csv is a separate, older format with a full
  PRESENT/PARTIALLY_PRESENT/ABSENT status per field, for validation tooling
  only (see scripts/eval/confusion_matrix_analysis.py) - not what you want
  for the curator table.

📖 Examples
  BioAnalyzer search --preset discovery -n 50 -o pmids.txt
  BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv
  BioAnalyzer analyze 12345678
  BioAnalyzer analyze --file PMID.xls --format csv -o results.csv
  BioAnalyzer analyze-url https://example.com/study
  BioAnalyzer retrieve 12345678,87654321 --save
  BioAnalyzer qa "What is 16S sequencing?"
  BioAnalyzer settings preset balanced --save

🔧 API: http://localhost:8000  |  Docs: http://localhost:8000/docs
"""
        )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="BioAnalyzer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")
    sub.add_parser("help")
    sub.add_parser("build")
    start = sub.add_parser("start")
    start.add_argument("--interactive", "-i", action="store_true")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    sub.add_parser("fields")
    run = sub.add_parser("run")
    run_sub = run.add_subparsers(dest="run_command")
    rt = run_sub.add_parser("table")
    rt.add_argument("--port", "-p", type=int, default=8501)
    sr = sub.add_parser(
        "search", help="PubMed esearch using spec discovery query presets"
    )
    sr.add_argument("--query", "-q", help="Custom PubMed query (overrides --preset)")
    sr.add_argument(
        "--preset", choices=["discovery", "broad", "precision"], default="discovery"
    )
    sr.add_argument("--max-results", "-n", type=int, default=100)
    sr.add_argument("--format", choices=["txt", "json", "csv"], default="txt")
    sr.add_argument("--output", "-o")
    an = sub.add_parser("analyze")
    an.add_argument("pmids", nargs="*")
    an.add_argument("--file", "-f")
    an.add_argument(
        "--format",
        choices=["table", "json", "csv", "curator_desk_csv", "detailed_csv", "xml"],
        default="table",
    )
    an.add_argument("--output", "-o")
    an.add_argument(
        "--refresh", action="store_true", help="Bypass cache and recompute analysis"
    )
    an.add_argument("--verbose", "-v", action="store_true")
    au = sub.add_parser("analyze-url")
    au.add_argument("urls", nargs="*")
    au.add_argument("--file", "-f")
    au.add_argument("--embedding-model", default="gemini/text-embedding-004")
    au.add_argument("--llm-model", default="gemini/gemini-2.0-flash")
    au.add_argument("--format", choices=["table", "json"], default="table")
    au.add_argument("--output", "-o")
    au.add_argument("--poll-interval", type=int, default=5)
    au.add_argument("--timeout", type=int, default=300)
    au.add_argument("--verbose", "-v", action="store_true")
    ret = sub.add_parser("retrieve")
    ret.add_argument("pmids", nargs="*")
    ret.add_argument("--file", "-f")
    ret.add_argument("--format", choices=["table", "json", "csv"], default="table")
    ret.add_argument("--output", "-o")
    ret.add_argument("--save", "-s", action="store_true")
    ret.add_argument("--verbose", "-v", action="store_true")
    qa = sub.add_parser("qa")
    qa.add_argument("question", nargs="?")
    qa.add_argument("--interactive", "-i", action="store_true")
    st = sub.add_parser("settings")
    st_sub = st.add_subparsers(dest="settings_command")
    sv = st_sub.add_parser("view")
    sv.add_argument("--format", choices=["json", "yaml", "table"], default="table")
    sv.add_argument("--output", "-o")
    ss = st_sub.add_parser("save")
    ss.add_argument("--file", "-f")
    ss.add_argument("--format", choices=["json", "yaml"], default="json")
    ss.add_argument(
        "--preset",
        choices=["fast", "balanced", "high_quality", "development", "production"],
    )
    sl = st_sub.add_parser("load")
    sl.add_argument("--file", "-f", required=True)
    sl.add_argument("--apply", action="store_true")
    sp = st_sub.add_parser("preset")
    sp.add_argument(
        "name",
        choices=["fast", "balanced", "high_quality", "development", "production"],
    )
    sp.add_argument("--save", "-s", action="store_true")
    sm = st_sub.add_parser("migrate")
    sm.add_argument("--file", "-f", required=True)
    sm.add_argument("--output", "-o")
    return p


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if x not in seen and not seen.add(x)]  # type: ignore


def _expand_pmids(raw: list[str]) -> list[str]:
    out: list[str] = []
    for p in raw or []:
        out.extend(x.strip() for x in p.split(",") if x.strip())
    return out


def _resolve_pmids(
    cli: BioAnalyzerCLI, args: argparse.Namespace, announce_load: bool = False
) -> list[str] | None:
    """Merge inline PMIDs with any --file PMIDs, deduped. None on load failure."""
    pmids = _dedup(_expand_pmids(args.pmids))
    if args.file:
        try:
            loaded = cli.load_pmids_from_file(args.file)
        except Exception as e:
            print(f"❌ {e}")
            return None
        if announce_load:
            print(f"📁 Loaded {len(loaded)} PMID(s) from {args.file}")
        pmids = _dedup(pmids + loaded)
    return pmids


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    cli = BioAnalyzerCLI()
    cli.verbose = getattr(args, "verbose", False)
    cmd = args.command
    if not cmd or cmd == "help":
        cli.print_help()
    elif cmd == "build":
        if not cli.build_containers():
            sys.exit(1)
    elif cmd == "start":
        if not cli.start_application():
            sys.exit(1)
        if getattr(args, "interactive", False):
            cli.ask_question("")
    elif cmd == "stop":
        if not cli.stop_application():
            sys.exit(1)
    elif cmd == "restart":
        if not cli.restart_application():
            sys.exit(1)
    elif cmd == "status":
        cli.get_system_status()
    elif cmd == "fields":
        cli.show_fields_info()
    elif cmd == "run":
        if getattr(args, "run_command", None) == "table":
            if not cli.run_table(port=getattr(args, "port", 8501)):
                sys.exit(1)
        else:
            print("Usage: BioAnalyzer run table")
    elif cmd == "qa":
        if args.interactive or not args.question:
            cli.interactive_qa()
        else:
            cli.ask_question(args.question)
    elif cmd == "search":
        cli.search_pubmed(
            query=getattr(args, "query", None),
            preset=getattr(args, "preset", "discovery"),
            max_results=getattr(args, "max_results", 100),
            fmt=getattr(args, "format", "txt"),
            output_file=getattr(args, "output", None),
        )
    elif cmd == "analyze":
        pmids = _resolve_pmids(cli, args, announce_load=True)
        if pmids is None:
            return
        if not pmids:
            print(
                "❌ No PMIDs provided. Use: BioAnalyzer analyze <pmid> or --file <file>"
            )
            return
        cli.analyze_papers(pmids, args.format, args.output, args.refresh)
    elif cmd == "analyze-url":
        cli.handle_url_analysis(
            args.urls,
            args.file,
            args.embedding_model,
            args.llm_model,
            args.format,
            args.output,
            args.poll_interval,
            args.timeout,
        )
    elif cmd == "retrieve":
        pmids = _resolve_pmids(cli, args)
        if pmids is None:
            return
        if not pmids:
            print("❌ No PMIDs provided.")
            return
        cli.retrieve_papers(pmids, args.format, args.output, args.save)
    elif cmd == "settings":
        cli.handle_settings_command(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
