#!/usr/bin/env python3
"""
BioAnalyzer CLI - User-Friendly Command Line Interface
=====================================================

Usage:
    BioAnalyzer help
    BioAnalyzer build / start / stop / restart / status
    BioAnalyzer run table
    BioAnalyzer analyze <pmid> | <pmid1,pmid2> | --file FILE [--format FMT] [-o OUT]
    BioAnalyzer analyze-url <url> | --file FILE
    BioAnalyzer retrieve <pmid> [--save]
    BioAnalyzer qa [question | --interactive]
    BioAnalyzer fields
    BioAnalyzer settings view|save|load|preset|migrate
"""

from __future__ import annotations

import asyncio, csv, io, json, logging, os, re, subprocess, sys, time
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

COMPOSE_PROJECT_NAME = "bioanalyzer-package"

# ---------------------------------------------------------------------------
# Shared field definitions (single source of truth)
# ---------------------------------------------------------------------------
ANALYSIS_FIELDS: Dict[str, str] = {
    "host_species": "Host Species",
    "body_site": "Body Site",
    "condition": "Condition",
    "sequencing_type": "Sequencing Type",
    "taxa_level": "Taxa Level",
    "sample_size": "Sample Size",
}

STATUS_ICONS = {"PRESENT": "✅", "PARTIALLY_PRESENT": "⚠️", "ABSENT": "❌"}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _field_val(fields: dict, key: str, attr: str = "value") -> str:
    return str(fields.get(key, {}).get(attr, "") or "")


def _field_ontology_id(fields: dict, key: str) -> str:
    return str(fields.get(key, {}).get("ontology_id", "") or "")


def _status_normalise(value: Any) -> str:
    s = str(value).strip().upper() if value else ""
    return s if s in {"PRESENT", "PARTIALLY_PRESENT", "ABSENT"} else "ABSENT"


def _bool_upper(value: Any) -> str:
    return "TRUE" if bool(value) else "FALSE"


def _extract_year(publication_date: Any) -> str:
    s = str(publication_date or "").strip()
    m = re.search(r"\b(19|20)\d{2}\b", s)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# Unified result serialiser
# ---------------------------------------------------------------------------


def render_results(results: List[Dict[str, Any]], fmt: str) -> str:
    """Convert analysis results to any supported format string."""
    if fmt == "json":
        return json.dumps(results, indent=2, ensure_ascii=False)
    if fmt == "csv":
        return _render_csv(results)
    if fmt == "curator_desk_csv":
        return _render_curator_desk_csv(results)
    if fmt == "xml":
        return _render_xml(results)
    return _render_table(results)


def _render_table(results: List[Dict[str, Any]]) -> str:
    lines = [
        "\n" + "=" * 80,
        "🧬 BIOANALYZER - CURATABLE SIGNATURE ANALYSIS RESULTS",
        "=" * 80,
    ]
    for r in results:
        lines += [
            f"\n📄 PMID: {r.get('pmid','N/A')}",
            f"📝 Title: {r.get('title','N/A')}",
            f"📰 Journal: {r.get('journal','N/A')}",
            "-" * 60,
        ]
        for key, label in ANALYSIS_FIELDS.items():
            fd = r.get("fields", {}).get(key, {})
            icon = STATUS_ICONS.get(fd.get("status", ""), "❓")
            lines.append(
                f"{icon} {label:20} | {fd.get('status','UNKNOWN'):20} | "
                f"{str(fd.get('value','N/A')):30} | {fd.get('confidence', 0.0):.2f}"
            )
        lines += [
            "-" * 60,
            f"📋 Summary: {r.get('curation_summary','N/A')}",
            f"⏱️  Time: {r.get('processing_time', 0):.2f}s",
            "",
        ]
    return "\n".join(lines)


def _render_csv(results: List[Dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    headers = ["PMID", "Title", "Journal"]
    for label in ANALYSIS_FIELDS.values():
        headers += [label, f"{label} Status"]
    headers += ["Summary", "Processing Time"]
    w.writerow(headers)
    for r in results:
        fields = r.get("fields", {})
        row = [r.get("pmid", ""), r.get("title", ""), r.get("journal", "")]
        for key in ANALYSIS_FIELDS:
            row += [_field_val(fields, key), _field_val(fields, key, "status")]
        row += [r.get("curation_summary", ""), r.get("processing_time", 0)]
        w.writerow(row)
    return out.getvalue()


def _render_curator_desk_csv(results: List[Dict[str, Any]]) -> str:
    columns = [
        "PMID",
        "Title",
        "Journal",
        "Year",
        "Host Species",
        "Host Species ID",
        "Host Species Status",
        "Body Site",
        "Body Site ID",
        "Body Site Status",
        "Condition",
        "Condition ID",
        "Condition Status",
        "Sequencing Type",
        "Sequencing Type Status",
        "Sample Size",
        "Sample Size Status",
        "has_differential_abundance",
        "differential_abundance_confidence",
        "in_bugsigdb",
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    seen: set = set()
    for r in results:
        pmid = str(r.get("pmid", "") or "").strip()
        if pmid in seen:
            continue
        seen.add(pmid)
        fields = r.get("fields", {}) or {}
        try:
            conf = f"{float(r.get('differential_abundance_confidence', 0.0)):.2f}"
        except (TypeError, ValueError):
            conf = "0.00"
        w.writerow(
            {
                "PMID": pmid,
                "Title": r.get("title", ""),
                "Journal": r.get("journal", ""),
                "Year": _extract_year(r.get("year") or r.get("publication_date", "")),
                "Host Species": _field_val(fields, "host_species"),
                "Host Species ID": _field_ontology_id(fields, "host_species"),
                "Host Species Status": _status_normalise(
                    _field_val(fields, "host_species", "status")
                ),
                "Body Site": _field_val(fields, "body_site"),
                "Body Site ID": _field_ontology_id(fields, "body_site"),
                "Body Site Status": _status_normalise(
                    _field_val(fields, "body_site", "status")
                ),
                "Condition": _field_val(fields, "condition"),
                "Condition ID": _field_ontology_id(fields, "condition"),
                "Condition Status": _status_normalise(
                    _field_val(fields, "condition", "status")
                ),
                "Sequencing Type": _field_val(fields, "sequencing_type"),
                "Sequencing Type Status": _status_normalise(
                    _field_val(fields, "sequencing_type", "status")
                ),
                "Sample Size": _field_val(fields, "sample_size"),
                "Sample Size Status": _status_normalise(
                    _field_val(fields, "sample_size", "status")
                ),
                "has_differential_abundance": _bool_upper(
                    r.get("has_differential_abundance")
                ),
                "differential_abundance_confidence": conf,
                "in_bugsigdb": _bool_upper(r.get("in_bugsigdb")),
            }
        )
    return out.getvalue()


def _render_xml(results: List[Dict[str, Any]]) -> str:
    if not results:
        return '<?xml version="1.0" encoding="UTF-8"?>\n<BioAnalyzerResults></BioAnalyzerResults>'
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<BioAnalyzerResults>"]
    xml_field_names = {
        "host_species": "HostSpecies",
        "body_site": "BodySite",
        "condition": "Condition",
        "sequencing_type": "SequencingType",
        "taxa_level": "TaxaLevel",
        "sample_size": "SampleSize",
    }
    for r in results:
        fields = r.get("fields", {})
        lines += [
            "  <Analysis>",
            f"    <PMID>{r.get('pmid','')}</PMID>",
            f"    <Title>{r.get('title','')}</Title>",
            f"    <Journal>{r.get('journal','')}</Journal>",
            f"    <ProcessingTime>{r.get('processing_time',0)}</ProcessingTime>",
            "    <Fields>",
        ]
        for key, tag in xml_field_names.items():
            fd = fields.get(key, {})
            lines += [
                f"      <{tag}>",
                f"        <Status>{fd.get('status','UNKNOWN')}</Status>",
                f"        <Value><![CDATA[{fd.get('value','N/A')}]]></Value>",
                f"        <Confidence>{fd.get('confidence',0.0):.2f}</Confidence>",
                f"      </{tag}>",
            ]
        lines += [
            "    </Fields>",
            f"    <Summary><![CDATA[{r.get('curation_summary','')}]]></Summary>",
            "  </Analysis>",
        ]
    lines.append("</BioAnalyzerResults>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unified retrieval serialiser
# ---------------------------------------------------------------------------


def render_retrieval(results: List[Dict[str, Any]], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(results, indent=2, ensure_ascii=False)
    if fmt == "csv":
        return _render_retrieval_csv(results)
    return _render_retrieval_table(results)


def _render_retrieval_table(results: List[Dict[str, Any]]) -> str:
    lines = [
        "\n" + "=" * 80,
        "📥 BIOANALYZER - PUBMED PAPER RETRIEVAL RESULTS",
        "=" * 80,
    ]
    for r in results:
        if "error" in r:
            lines += [f"\n❌ PMID: {r.get('pmid','N/A')}", f"Error: {r['error']}"]
            continue
        authors = r.get("authors", [])
        author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        lines += [
            f"\n📄 PMID: {r.get('pmid','N/A')}",
            f"📝 Title: {r.get('title','N/A')}",
            f"📰 Journal: {r.get('journal','N/A')}",
            f"👥 Authors: {author_str}",
            f"📅 Publication Date: {r.get('publication_date','N/A')}",
            f"📖 Full Text: {'✅ Available' if r.get('has_full_text') else '❌ Not available'}",
        ]
        abstract = r.get("abstract", "")
        if abstract:
            lines.append(
                f"📋 Abstract: {abstract[:200]}{'...' if len(abstract) > 200 else ''}"
            )
        lines.append("-" * 60)
    return "\n".join(lines)


def _render_retrieval_csv(results: List[Dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(
        [
            "PMID",
            "Title",
            "Journal",
            "Authors",
            "Publication Date",
            "Has Full Text",
            "Abstract Length",
            "Full Text Length",
            "Error",
        ]
    )
    for r in results:
        w.writerow(
            [
                r.get("pmid", ""),
                r.get("title", ""),
                r.get("journal", ""),
                "; ".join(r.get("authors", [])),
                r.get("publication_date", ""),
                "Yes" if r.get("has_full_text") else "No",
                len(r.get("abstract", "")),
                len(r.get("full_text", "")),
                r.get("error", ""),
            ]
        )
    return out.getvalue()


# ---------------------------------------------------------------------------
# Main CLI class
# ---------------------------------------------------------------------------


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

    def __init__(self):
        self.container_name = "bioanalyzer-package"
        self.image_name = "bioanalyzer-package"
        self.network_name = "bioanalyzer-network"
        self.verbose = False
        self.api_base_url = os.getenv(
            "BIOANALYZER_API_URL", "http://localhost:8000/api/v1"
        )

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    def _env_file_path(self) -> Optional[str]:
        p = project_root / ".env"
        return str(p.resolve()) if p.exists() else None

    def _env_file_values(self) -> Dict[str, str]:
        env_file = self._env_file_path()
        if not env_file or dotenv_values is None:
            return {}
        return {k: v for k, v in (dotenv_values(env_file) or {}).items() if v}

    def _collect_env_flags(self) -> List[str]:
        flags: List[str] = []
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

    # ------------------------------------------------------------------
    # Docker helpers
    # ------------------------------------------------------------------

    def _run(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
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

    def _compose_cmd(self) -> List[str]:
        if self._run(["which", "docker-compose"]).stdout.strip():
            return ["docker-compose"]
        return ["docker", "compose"]

    def _is_container_running(self) -> bool:
        for name in [self.container_name, "bioanalyzer-package"]:
            if self._run(
                ["docker", "ps", "--filter", f"name={name}", "-q"]
            ).stdout.strip():
                return True
        return False

    def _ensure_volume_directories(self) -> bool:
        for name in ["cache", "logs", "results"]:
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
                requests.get("http://localhost:8000/health", timeout=5).status_code
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

        import pwd, grp

        env = os.environ.copy()
        try:
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
        else:
            print("⚠️  Container started but health check timed out after 60s")

        print("\n🎉 BioAnalyzer backend is running!")
        print("🔧 API: http://localhost:8000  |  📖 Docs: http://localhost:8000/docs")
        return True

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
        if not self._is_container_running():
            print("✅ BioAnalyzer application stopped")
            return True
        for name in [self.container_name, "bioanalyzer-package", "bioanalyzer-redis"]:
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

    def get_system_status(self):
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

    def load_pmids_from_file(self, file_path: str) -> List[str]:
        ext = Path(file_path).suffix.lower()
        if ext in [".xls", ".xlsx"]:
            return self._read_excel_via_docker(file_path)
        if ext == ".csv":
            with open(file_path, encoding="utf-8") as f:
                return [
                    row[0].strip() for row in csv.reader(f) if row and row[0].strip()
                ]
        # Plain text
        pmids: List[str] = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    pmids.extend(p.strip() for p in line.split(",") if p.strip())
        return pmids

    def _read_excel_via_docker(self, file_path: str) -> List[str]:
        file_path_obj = Path(file_path).resolve()
        if not self.check_docker() or not self.check_image():
            raise Exception(
                "Docker image required to read Excel files. Run 'BioAnalyzer build'."
            )
        script = (
            r"""
import pandas as pd, sys, json, re

def normalize(v):
    if pd.isna(v): return None
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else None
    raw = str(v).strip()
    if re.fullmatch(r'\d+\.0+', raw): return raw.split('.')[0]
    return raw if re.fullmatch(r'\d+', raw) else None

df = pd.read_excel('/workspace/"""
            + file_path_obj.name
            + r"""')
best, best_score = [], -1
for col in df.columns:
    pmids = [p for p in (normalize(v) for v in df[col]) if p and len(p) >= 6]
    score = len(pmids) + (100000 if 'pmid' in str(col).lower() else 0)
    if score > best_score: best_score, best = score, pmids
if not best: raise ValueError('No valid PMIDs found.')
seen, out = set(), []
for p in best:
    if p not in seen: seen.add(p); out.append(p)
print(json.dumps(out))
"""
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
            check=True,
        )
        return json.loads(result.stdout.strip())

    def get_curator_desk_csv_content(self, results: List[Dict[str, Any]]) -> str:
        """Serialize analysis results to curator-desk CSV (includes ontology ID columns)."""
        return render_results(results, "curator_desk_csv")

    # ------------------------------------------------------------------
    # PubMed discovery search
    # ------------------------------------------------------------------

    def search_pubmed(
        self,
        query: Optional[str] = None,
        preset: str = "discovery",
        max_results: int = 100,
        fmt: str = "txt",
        output_file: Optional[str] = None,
    ) -> List[str]:
        """Run a PubMed esearch and return PMIDs (spec discovery query by default)."""
        from app.services.data_retrieval import PubMedRetriever
        from app.pubmed_queries import RECOMMENDED_DISCOVERY_QUERY, SEARCH_PRESETS

        if query:
            term = query.strip()
        else:
            term = SEARCH_PRESETS.get(preset, RECOMMENDED_DISCOVERY_QUERY)

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

        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
            print(f"💾 PMIDs saved to: {output_file}")
        else:
            print(content)
        return pmids

    # ------------------------------------------------------------------
    # Analysis commands
    # ------------------------------------------------------------------

    async def analyze_papers(
        self,
        pmids: List[str],
        fmt: str = "table",
        output_file: Optional[str] = None,
        refresh: bool = False,
    ):
        request_timeout = int(os.getenv("BIOANALYZER_ANALYZE_TIMEOUT", "180"))
        results, total = [], len(pmids)
        print(f"🔬 Analysing {total} paper(s)...")
        for i, pmid in enumerate(pmids, 1):
            print(f"[{i}/{total}] PMID: {pmid}")
            try:
                r = requests.get(
                    f"http://localhost:8000/api/v1/analyze/{pmid}",
                    params={"refresh": "true"} if refresh else None,
                    timeout=request_timeout,
                )
                if r.status_code == 200:
                    results.append(r.json())
                    print(f"✅ Done")
                else:
                    print(f"❌ {r.json().get('detail','Unknown error')}")
            except Exception as e:
                print(f"❌ {e}")

        if not results:
            print("❌ No results obtained.")
            return
        content = render_results(results, fmt)
        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
            print(f"💾 Results saved to: {output_file}")
        else:
            print(content)

    # ------------------------------------------------------------------
    # URL analysis
    # ------------------------------------------------------------------

    def handle_url_analysis(
        self,
        urls: List[str],
        file_path: Optional[str],
        embedding_model: str,
        llm_model: str,
        fmt: str,
        output_file: Optional[str],
        poll_interval: int,
        timeout: int,
    ):
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
        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
            print(f"💾 Saved to: {output_file}")
        else:
            print(content)

    def _collect_urls(self, inline: List[str], file_path: Optional[str]) -> List[str]:
        urls: List[str] = []
        for v in inline or []:
            urls.extend(v.split(",") if "," in v else [v])
        if file_path:
            try:
                urls.extend(
                    line.strip()
                    for line in open(file_path, encoding="utf-8")
                    if line.strip()
                )
            except Exception as e:
                print(f"❌ Error reading URL file: {e}")
        seen: set = set()
        return [u.strip() for u in urls if u.strip() and u.strip() not in seen and not seen.add(u.strip())]  # type: ignore

    def _start_url_job(self, url: str, emb: str, llm: str) -> Optional[str]:
        try:
            r = requests.post(
                self._build_api_url("/analyze-url"),
                json={"url": url, "embedding_model": emb, "llm_model": llm},
                timeout=30,
            )
            if r.status_code == 200:
                job_id = r.json().get("job_id")
                print(f"🆔 Job ID: {job_id}")
                return job_id
            print(f"❌ {r.json().get('detail', r.text)}")
        except requests.RequestException as e:
            print(f"❌ Network error: {e}")
        return None

    def _poll_url_job(self, job_id: str, interval: int, timeout: int) -> Optional[Dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = requests.get(
                    self._build_api_url(f"/analysis-status/{job_id}"), timeout=15
                ).json()
                print(f"   ⏳ {status.get('status')} ({status.get('progress','')})")
                if status.get("status") == "completed":
                    r = requests.get(
                        self._build_api_url(f"/analysis-result/{job_id}"), timeout=30
                    )
                    return r.json() if r.status_code == 200 else None
                if status.get("status") == "failed":
                    print(f"❌ Failed: {status.get('error','')}")
                    return None
                time.sleep(max(1, interval))
            except Exception as e:
                print(f"❌ Poll error: {e}")
                time.sleep(max(1, interval))
        print(f"⚠️  Job {job_id} timed out.")
        return None

    def _render_url_results(self, results: List[Dict], fmt: str) -> str:
        if fmt == "json":
            return json.dumps(results, indent=2, ensure_ascii=False)
        lines = [
            "\n" + "=" * 80,
            "🌐 BIOANALYZER - URL STUDY ANALYSIS RESULTS",
            "=" * 80,
        ]
        for r in results:
            lines += [
                f"\n🔗 {r.get('source_url','N/A')}",
                f"🆔 Job: {r.get('job_id','N/A')}",
                f"🧪 Experiments: {len(r.get('experiments',[]))}",
                f"✅ Curation Ready: {'Yes' if r.get('curation_ready') else 'No'}",
                f"⚠️  Missing: {', '.join(r.get('missing_fields',[])) or 'None'}",
                "-" * 60,
            ]
            for exp in r.get("experiments", []):
                m = exp.get("metadata", {})
                lines += [
                    f"   • {exp.get('title','Untitled')}",
                    f"     Species: {m.get('host_species','N/A')}  Site: {m.get('body_site','N/A')}",
                    f"     Condition: {m.get('condition','N/A')}  Seq: {m.get('sequencing_type','N/A')}",
                    f"     Taxa: {m.get('taxa_level','N/A')}  N: {m.get('sample_size','N/A')}",
                    f"     Signatures: {len(exp['signatures']) if exp.get('signatures') else 'None'}",
                    "",
                ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve_papers(
        self,
        pmids: List[str],
        fmt: str = "table",
        output_file: Optional[str] = None,
        save: bool = False,
    ):
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
        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
            print(f"💾 Saved to: {output_file}")
        else:
            print(content)

    def _get_retriever(self):
        try:
            from app.services.standalone_pubmed_retriever import (
                StandalonePubMedRetriever,
            )

            return StandalonePubMedRetriever()
        except ImportError:
            return self._fallback_retriever()

    def _fallback_retriever(self):
        class _R:
            def get_full_paper_data(self, pmid: str) -> Dict:
                try:
                    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                    r = requests.get(
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

    def _save_paper(self, data: Dict) -> str:
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

    async def ask_question(self, question: str) -> Optional[str]:
        if not self.check_backend_health():
            print("⚠️  API not running. Start with: BioAnalyzer start")
            return None
        try:
            print("🤔 Thinking...")
            r = requests.post(
                "http://localhost:8000/api/v1/qa",
                json={"question": question},
                timeout=60,
            )
            if r.status_code == 200:
                answer = r.json().get("answer") or r.json().get("text", "")
                conf = r.json().get("confidence", 0.8)
                if answer:
                    print(
                        f"\n💡 Answer (confidence: {conf:.2f}):\n{'-'*60}\n{answer}\n{'-'*60}"
                    )
                    return answer
            elif r.status_code == 404:
                print("⚠️  Q&A endpoint not available yet.")
            else:
                print(f"❌ API error: {r.json().get('detail','Unknown')}")
        except Exception as e:
            print(f"❌ {e}")
        return None

    def interactive_qa(self):
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
                    asyncio.run(self.ask_question(q))
            except KeyboardInterrupt:
                break
        print("👋 Goodbye!")

    # ------------------------------------------------------------------
    # Fields info
    # ------------------------------------------------------------------

    def show_fields_info(self):
        print("\n🧬 BioAnalyzer - BugSigDB Essential Fields\n" + "=" * 42)
        descriptions = {
            "host_species": "Host organism (e.g. Human, Mouse, Rat)",
            "body_site": "Sample location (e.g. Gut, Oral, Skin)",
            "condition": "Disease, treatment, or exposure studied",
            "sequencing_type": "Molecular method (e.g. 16S, metagenomics)",
            "taxa_level": "Taxonomic level (e.g. phylum, genus, species)",
            "sample_size": "Number of samples / participants",
        }
        for key, label in ANALYSIS_FIELDS.items():
            print(f"  🔹 {label}: {descriptions[key]}")
        print("\n✅ PRESENT  ⚠️ PARTIALLY_PRESENT  ❌ ABSENT\n")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def handle_settings_command(self, args):
        try:
            from app.core.settings import SettingsManager, BioAnalyzerSettings
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

    def _format_settings_table(self, settings: "BioAnalyzerSettings") -> str:
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

    def print_banner(self):
        print("\n🧬 ============================================= 🧬")
        print("   BioAnalyzer - Curatable Signature Analysis Tool")
        print("🧬 ============================================= 🧬\n")

    def print_help(self):
        self.print_banner()
        print(
            """📋 COMMANDS
  build / start / stop / restart / status
  run table [--port N]
  search [--preset discovery|broad|precision] [-n N] [-o FILE] [--query Q]
  analyze <pmid|pmids>  [--file F] [--format table|json|csv|curator_desk_csv|xml] [-o FILE]
  analyze-url <url>     [--file F] [--format table|json] [-o FILE]
  retrieve <pmid|pmids> [--file F] [--format table|json|csv] [-o FILE] [--save]
  qa [question]         [--interactive]
  fields
  settings view|save|load|preset|migrate

📖 Examples
  BioAnalyzer search --preset discovery -n 50 -o pmids.txt
  BioAnalyzer analyze --file pmids.txt --format curator_desk_csv -o predictions.csv
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

    # search (PubMed discovery)
    sr = sub.add_parser(
        "search", help="PubMed esearch using spec discovery query presets"
    )
    sr.add_argument("--query", "-q", help="Custom PubMed query (overrides --preset)")
    sr.add_argument(
        "--preset",
        choices=["discovery", "broad", "precision"],
        default="discovery",
        help="Query preset from curator-desk spec (default: discovery)",
    )
    sr.add_argument("--max-results", "-n", type=int, default=100)
    sr.add_argument("--format", choices=["txt", "json", "csv"], default="txt")
    sr.add_argument("--output", "-o")

    # analyze
    an = sub.add_parser("analyze")
    an.add_argument("pmids", nargs="*")
    an.add_argument("--file", "-f")
    an.add_argument(
        "--format",
        choices=["table", "json", "csv", "curator_desk_csv", "xml"],
        default="table",
    )
    an.add_argument("--output", "-o")
    an.add_argument(
        "--refresh", action="store_true", help="Bypass cache and recompute analysis"
    )
    an.add_argument("--verbose", "-v", action="store_true")

    # analyze-url
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

    # retrieve
    ret = sub.add_parser("retrieve")
    ret.add_argument("pmids", nargs="*")
    ret.add_argument("--file", "-f")
    ret.add_argument("--format", choices=["table", "json", "csv"], default="table")
    ret.add_argument("--output", "-o")
    ret.add_argument("--save", "-s", action="store_true")
    ret.add_argument("--verbose", "-v", action="store_true")

    # qa
    qa = sub.add_parser("qa")
    qa.add_argument("question", nargs="?")
    qa.add_argument("--interactive", "-i", action="store_true")

    # settings
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


def _dedup(pmids: List[str]) -> List[str]:
    seen: set = set()
    return [p for p in pmids if p not in seen and not seen.add(p)]  # type: ignore


def _expand_pmids(raw: List[str]) -> List[str]:
    out: List[str] = []
    for p in raw or []:
        out.extend(x.strip() for x in p.split(",") if x.strip())
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = _build_parser()
    args = parser.parse_args()
    cli = BioAnalyzerCLI()
    cli.verbose = getattr(args, "verbose", False)
    cmd = args.command

    if not cmd or cmd == "help":
        cli.print_help()
    elif cmd == "build":
        cli.build_containers()
    elif cmd == "start":
        cli.start_application()
        if getattr(args, "interactive", False):
            asyncio.run(cli.ask_question(""))  # placeholder hook
    elif cmd == "stop":
        cli.stop_application()
    elif cmd == "restart":
        cli.restart_application()
    elif cmd == "status":
        cli.get_system_status()
    elif cmd == "fields":
        cli.show_fields_info()
    elif cmd == "run":
        if getattr(args, "run_command", None) == "table":
            cli.run_table(port=getattr(args, "port", 8501))
        else:
            print("Usage: BioAnalyzer run table")
    elif cmd == "qa":
        if args.interactive or not args.question:
            cli.interactive_qa()
        else:
            asyncio.run(cli.ask_question(args.question))
    elif cmd == "search":
        cli.search_pubmed(
            query=getattr(args, "query", None),
            preset=getattr(args, "preset", "discovery"),
            max_results=getattr(args, "max_results", 100),
            fmt=getattr(args, "format", "txt"),
            output_file=getattr(args, "output", None),
        )
    elif cmd == "analyze":
        pmids = _dedup(_expand_pmids(args.pmids))
        if args.file:
            try:
                loaded = cli.load_pmids_from_file(args.file)
                print(f"📁 Loaded {len(loaded)} PMID(s) from {args.file}")
                pmids = _dedup(pmids + loaded)
            except Exception as e:
                print(f"❌ {e}")
                return
        if not pmids:
            print(
                "❌ No PMIDs provided. Use: BioAnalyzer analyze <pmid> or --file <file>"
            )
            return
        asyncio.run(cli.analyze_papers(pmids, args.format, args.output, args.refresh))
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
        pmids = _dedup(_expand_pmids(args.pmids))
        if args.file:
            try:
                pmids = _dedup(pmids + cli.load_pmids_from_file(args.file))
            except Exception as e:
                print(f"❌ {e}")
                return
        if not pmids:
            print("❌ No PMIDs provided.")
            return
        asyncio.run(cli.retrieve_papers(pmids, args.format, args.output, args.save))
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
