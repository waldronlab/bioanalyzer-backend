#!/usr/bin/env python3
"""
BioAnalyzer CLI - User-Friendly Command Line Interface
=====================================================

This CLI provides a simple, user-friendly interface for BioAnalyzer.
All commands are designed to be intuitive and easy to use.

Usage:
    BioAnalyzer help                    # Show help
    BioAnalyzer build                   # Build Docker containers
    BioAnalyzer start                   # Start the application
    BioAnalyzer run table               # Run curator table (Streamlit)
    BioAnalyzer analyze <pmid>          # Analyze a single paper
    BioAnalyzer analyze <pmid1,pmid2>   # Analyze multiple papers
    BioAnalyzer status                  # Check system status
    BioAnalyzer stop                    # Stop the application
"""

from __future__ import annotations

import asyncio
import json
import sys
import argparse
import os
import subprocess
import time
import csv
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from app.core.settings import BioAnalyzerSettings

import requests

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - safety net for bare installs
    dotenv_values = None  # type: ignore

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Compose project name: ensures network is always "bioanalyzer-package_bioanalyzer-net"
COMPOSE_PROJECT_NAME = "bioanalyzer-package"


class BioAnalyzerCLI:
    """User-friendly Command Line Interface for BioAnalyzer."""

    def __init__(self):
        self.container_name = "bioanalyzer-package"
        self.image_name = "bioanalyzer-package"
        self.network_name = "bioanalyzer-network"
        self.verbose = False
        self.api_base_url = os.getenv(
            "BIOANALYZER_API_URL", "http://localhost:8000/api/v1"
        )
        self.required_env_vars = [
            "GEMINI_API_KEY",
            "NCBI_API_KEY",
            "EMAIL",
        ]
        self.optional_env_vars = [
            "API_TIMEOUT",
            "NCBI_RATE_LIMIT_DELAY",
            "USE_FULLTEXT",
            "LOG_LEVEL",
            "UVICORN_RELOAD",
        ]

    def _get_env_file_path(self) -> Optional[str]:
        """Get the absolute path to .env file if it exists."""
        env_path = project_root / ".env"
        if env_path.exists():
            return str(env_path.resolve())
        return None

    def _get_env_file_values(self) -> Dict[str, str]:
        """Return key/value pairs from .env if present."""
        env_file = self._get_env_file_path()
        if not env_file:
            return {}
        try:
            if dotenv_values is None:
                return {}
            values = dotenv_values(env_file)
            return {k: v for k, v in (values or {}).items() if v}
        except Exception:
            return {}

    def _collect_env_flags(self) -> List[str]:
        """Collect docker -e flags for known env vars if present in the host environment."""
        flags = []
        env_file = self._get_env_file_path()
        if env_file:
            flags.extend(["--env-file", env_file])
        for key in self.required_env_vars + self.optional_env_vars:
            val = os.environ.get(key)
            if val is not None and str(val) != "":
                flags.extend(["-e", f"{key}={val}"])
        return flags

    def _build_api_url(self, path: str) -> str:
        """Construct a BioAnalyzer API URL relative to the configured base."""
        base = self.api_base_url.rstrip("/")
        suffix = path.lstrip("/")
        return f"{base}/{suffix}" if suffix else base

    def _validate_environment(self) -> None:
        """Warn about missing critical env vars before starting containers."""
        env_file = self._get_env_file_path()
        env_file_values = self._get_env_file_values()

        missing_from_env = []
        missing_from_everywhere = []

        for key in self.required_env_vars:
            host_value = os.environ.get(key)
            file_value = env_file_values.get(key)
            if not host_value and not file_value:
                missing_from_everywhere.append(key)
            elif not host_value and file_value:
                missing_from_env.append(key)

        if not missing_from_env and not missing_from_everywhere:
            return

        if missing_from_env:
            print("⚠️  Environment variables will be loaded from .env only:")
            for key in missing_from_env:
                print(f"   - {key} (present in .env but not current shell)")
            print(
                "   This is fine, but export them if you need them on the host as well."
            )

        if missing_from_everywhere:
            print("⚠️  Missing critical environment variables:")
            for key in missing_from_everywhere:
                print(f"   - {key}")
            if env_file:
                print(
                    f"   Note: .env file found at {env_file}. Update it to include the keys above."
                )
            else:
                print(
                    "   Create a .env file in the project root or export them before running."
                )
                print("   Example:")
                print(
                    "     export GEMINI_API_KEY=your_key; export NCBI_API_KEY=your_key; export EMAIL=you@example.com"
                )

    def print_banner(self):
        """Print the BioAnalyzer banner."""
        print(
            """
🧬 =============================================== 🧬
   BioAnalyzer - Curatable Signature Analysis Tool
🧬 =============================================== 🧬
        """
        )

    def print_help(self):
        """Print comprehensive help information."""
        self.print_banner()
        print(
            """
📋 AVAILABLE COMMANDS:
=====================

🔧 Setup Commands:
   BioAnalyzer build                    Build Docker containers
   BioAnalyzer start                    Start the application
   BioAnalyzer run table                Run curator table (Streamlit)
   BioAnalyzer stop                     Stop the application
   BioAnalyzer restart                  Restart the application
   BioAnalyzer status                   Check system status

🔬 Analysis Commands:
   BioAnalyzer analyze <pmid>           Analyze a single paper
   BioAnalyzer analyze <pmid1,pmid2>    Analyze multiple papers
   BioAnalyzer analyze --file <file>    Analyze papers from file
   BioAnalyzer analyze-url <url>        Analyze study from URL
   BioAnalyzer analyze-url --file <file> Analyze studies from file
   BioAnalyzer fields                   Show field information

📥 Retrieval Commands:
   BioAnalyzer retrieve <pmid>          Retrieve full paper text and metadata
   BioAnalyzer retrieve <pmid1,pmid2>   Retrieve multiple papers
   BioAnalyzer retrieve --file <file>  Retrieve papers from file

💬 Q&A Commands:
   BioAnalyzer qa <question>             Ask a question and get an answer
   BioAnalyzer qa --interactive          Start interactive Q&A mode
   BioAnalyzer qa                        Start interactive Q&A mode (default)

⚙️  Settings Commands:
   BioAnalyzer settings view             View current settings
   BioAnalyzer settings save             Save current settings to file
   BioAnalyzer settings load --file <f>  Load settings from file
   BioAnalyzer settings preset <name>    Apply preset configuration
   BioAnalyzer settings migrate --file <f> Migrate old settings format

📊 Output Options:
   --format json|csv|table             Output format (default: table)
   --output <file>                     Save results to file
   --verbose                           Verbose output

📖 Examples:
   BioAnalyzer build
   BioAnalyzer start
   BioAnalyzer run table                # Curator table at http://localhost:8501
   BioAnalyzer analyze 12345678
   BioAnalyzer analyze 12345678,87654321
   BioAnalyzer analyze --file pmids.txt --format json
   BioAnalyzer analyze-url https://example.com/study
   BioAnalyzer analyze-url --file urls.txt --format json
   BioAnalyzer retrieve 12345678
   BioAnalyzer retrieve 12345678,87654321 --save
   BioAnalyzer retrieve --file pmids.txt --format json
   BioAnalyzer fields
   BioAnalyzer qa "What is the microbiome?"
   BioAnalyzer qa --interactive
   BioAnalyzer settings view
   BioAnalyzer settings preset balanced --save
   BioAnalyzer status
   BioAnalyzer stop

🔧 API:
   Once started: http://localhost:8000
   API Documentation: http://localhost:8000/docs

❓ Need Help?
   BioAnalyzer help                    Show this help
   BioAnalyzer <command> --help        Show command-specific help
        """
        )

    def check_docker(self):
        """Check if Docker is available."""
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(" Error: Docker is not installed or not available.")
            print("Please install Docker to use BioAnalyzer.")
            return False

    def check_image(self):
        """Check if the Docker image exists."""
        try:
            subprocess.run(
                ["docker", "image", "inspect", self.image_name],
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def load_pmids_from_file(self, file_path: str) -> List[str]:
        """Load PMIDs from a file, supporting txt, csv, xls, and xlsx formats.
        
        For Excel files, uses Docker to read them since pandas is only available in Docker.
        """
        file_path_obj = Path(file_path)
        file_ext = file_path_obj.suffix.lower()
        
        pmids = []
        
        try:
            if file_ext in ['.xls', '.xlsx']:
                # Use Docker to read Excel files since pandas is only available in Docker
                pmids = self._read_excel_via_docker(file_path)
            elif file_ext == '.csv':
                # Read CSV using standard library (no pandas needed)
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and row[0].strip():
                            pmids.append(row[0].strip())
            else:
                # Default to text file (one PMID per line)
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            # Handle comma-separated PMIDs in text files
                            if "," in line:
                                pmids.extend([p.strip() for p in line.split(",") if p.strip()])
                            else:
                                pmids.append(line)
            
            return pmids
        except Exception as e:
            raise Exception(f"Error reading file '{file_path}': {e}")

    def _read_excel_via_docker(self, file_path: str) -> List[str]:
        """Read Excel file using Docker container where pandas is available."""
        file_path_obj = Path(file_path).resolve()
        file_dir = file_path_obj.parent
        file_name = file_path_obj.name
        
        # Check if Docker is available
        if not self.check_docker():
            raise Exception("Docker is required to read Excel files but Docker is not available")
        
        # Check if Docker image exists
        if not self.check_image():
            raise Exception(
                f"Docker image '{self.image_name}' not found. "
                "Please run 'BioAnalyzer build' first."
            )
        
        # Create a Python script to read the Excel file
        script = f"""
import pandas as pd
import sys
import json

try:
    # Read Excel file - PMIDs should be in the first column
    df = pd.read_excel('/workspace/{file_name}')
    # Get the first column
    first_col = df.iloc[:, 0]
    # Extract PMIDs (convert to string and strip whitespace)
    pmids = [str(val).strip() for val in first_col if pd.notna(val) and str(val).strip()]
    # Output as JSON for easy parsing
    print(json.dumps(pmids))
except Exception as e:
    print('ERROR: ' + str(e), file=sys.stderr)
    sys.exit(1)
"""
        
        try:
            # Run the script in Docker
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-v", f"{file_dir}:/workspace",
                    "-w", "/workspace",
                    self.image_name,
                    "python", "-c", script
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=file_dir
            )
            
            # Parse the JSON output
            pmids = json.loads(result.stdout.strip())
            return pmids
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else "Unknown error"
            raise Exception(f"Failed to read Excel file via Docker: {error_msg}")
        except json.JSONDecodeError:
            raise Exception(f"Failed to parse Docker output: {result.stdout}")

    def build_containers(self):
        """Build Docker containers."""
        print("🔨 Building BioAnalyzer containers...")

        if not self.check_docker():
            return False

        try:
            # Build the package image
            print("📦 Building package image...")
            result = subprocess.run(
                ["docker", "build", "-t", self.image_name, "."],
                cwd=project_root,
                check=True,
            )

            print("✅ Package image built successfully!")
            print("✅ All containers built successfully!")
            return True

        except subprocess.CalledProcessError as e:
            print(f" Error building containers: {e}")
            return False

    def _ensure_network(self):
        """Ensure Docker network exists for container communication."""
        check_result = subprocess.run(
            [
                "docker",
                "network",
                "ls",
                "--filter",
                f"name={self.network_name}",
                "--format",
                "{{.Name}}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if not check_result.stdout.strip():
            subprocess.run(
                ["docker", "network", "create", self.network_name],
                capture_output=True,
                check=False,
            )

    def _check_docker_permissions(self):
        """Check if user has proper Docker permissions and provide helpful guidance (non-blocking)."""
        test_result = subprocess.run(
            ["docker", "ps"], capture_output=True, text=True, check=False
        )

        if test_result.returncode == 0:
            return True
        if (
            "permission denied" in test_result.stderr.lower()
            or "Got permission denied" in test_result.stderr
        ):
            print("\n⚠️  Docker permission issue detected (non-blocking warning).")
            print("   To fix this permanently, run:")
            print("   sudo usermod -aG docker $USER")
            print("   Then log out and log back in (or run: newgrp docker)")
            print("   Continuing anyway...")
            return True

        return True

    def _ensure_volume_directories(self) -> bool:
        """Ensure cache, logs, results exist and are writable by the container user."""
        dirs = ["cache", "logs", "results"]
        for name in dirs:
            path = project_root / name
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                print(f"❌ Cannot create directory {path}: {e}")
                return False
            test_file = path / ".write_test"
            try:
                test_file.write_text("")
                test_file.unlink()
            except OSError:
                print(f"❌ Directory not writable by current user: {path}")
                print("   The package container needs to write here (e.g. performance.log).")
                print("   Fix with:")
                print(f"   sudo chown -R $USER:$USER {path}")
                return False
        return True

    def start_application(self):
        """Start the BioAnalyzer application."""
        print("🚀 Starting BioAnalyzer application...")

        if not self.check_docker():
            return False

        if not self.check_image():
            print("❌ Docker image not found. Building containers first...")
            if not self.build_containers():
                return False

        try:
            self._validate_environment()
            compose_file = project_root / "docker-compose.yml"
            if not compose_file.exists():
                print("❌ docker-compose.yml not found. Cannot start containers.")
                return False
            if not self._ensure_volume_directories():
                return False
            if self.check_backend_health():
                print("✅ API is already available at http://localhost:8000")
                return True
            compose_cmd = ["docker-compose"]
            check_compose = subprocess.run(
                ["which", "docker-compose"], capture_output=True, text=True, check=False
            )
            if not check_compose.stdout.strip():
                compose_cmd = ["docker", "compose"]
            ps_result = subprocess.run(
                compose_cmd + ["-p", COMPOSE_PROJECT_NAME, "ps", "-q"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=False,
            )
            containers_running = bool(ps_result.stdout.strip())
            self._check_docker_permissions()
            if containers_running and not self.check_backend_health():
                print("🧹 Cleaning up existing containers...")
                cleanup_result = subprocess.run(
                    compose_cmd + ["-p", COMPOSE_PROJECT_NAME, "down", "--remove-orphans"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if cleanup_result.returncode != 0:
                    subprocess.run(
                        [
                            "docker",
                            "rm",
                            "-f",
                            "bioanalyzer-redis",
                            "bioanalyzer-package",
                        ],
                        capture_output=True,
                        check=False,
                    )
            print("🔧 Starting API...")
            import os
            import pwd
            import grp

            env = os.environ.copy()
            try:
                current_user = pwd.getpwuid(os.getuid())
                current_group = grp.getgrgid(os.getgid())
                env["UID"] = str(current_user.pw_uid)
                env["GID"] = str(current_group.gr_gid)
            except (KeyError, AttributeError):
                env["UID"] = str(os.getuid())
                env["GID"] = str(os.getgid())
            up_cmd = compose_cmd + ["-p", COMPOSE_PROJECT_NAME, "up", "-d", "--force-recreate", "--remove-orphans"]

            result = subprocess.run(
                up_cmd,
                cwd=str(project_root),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                if "permission denied" in result.stderr.lower():
                    self._check_docker_permissions()
                print(f"❌ Error starting containers: {result.stderr}")
                if result.stdout:
                    print(f"\n📋 Output: {result.stdout}")
                return False
            if self._wait_for_backend_health(timeout=60, interval=2):
                print("✅ API is running at http://localhost:8000")
            else:
                print(
                    "⚠️  Package container started but /health did not report healthy within 60s"
                )

            print("\n🎉 BioAnalyzer backend is now running!")
            print("🔧 API: http://localhost:8000")
            print("📖 API Documentation: http://localhost:8000/docs")
            print("💡 Use 'BioAnalyzer status' to check system status")

            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ Error starting application: {e}")
            return False

    def stop_application(self):
        """Stop the BioAnalyzer application."""
        print("🛑 Stopping BioAnalyzer application...")

        try:
            self._check_docker_permissions()
            compose_file = project_root / "docker-compose.yml"
            if compose_file.exists():
                compose_cmd = ["docker-compose"]
                check_compose = subprocess.run(
                    ["which", "docker-compose"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if not check_compose.stdout.strip():
                    compose_cmd = ["docker", "compose"]

                result = subprocess.run(
                    compose_cmd + ["-p", COMPOSE_PROJECT_NAME, "down", "--remove-orphans"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode == 0:
                    print("✅ BioAnalyzer application stopped")
                    return True
            containers = [
                self.container_name,
                "bioanalyzer-package",
                "bioanalyzer-redis",
            ]
            stopped_any = False

            for container in containers:
                try:
                    stop_result = subprocess.run(
                        ["docker", "stop", container],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if stop_result.returncode == 0:
                        subprocess.run(
                            ["docker", "rm", container],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        print(f"✅ Stopped {container}")
                        stopped_any = True
                    else:
                        rm_result = subprocess.run(
                            ["docker", "rm", "-f", container],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if rm_result.returncode == 0:
                            print(f"✅ Removed {container}")
                            stopped_any = True
                except Exception:
                    pass

            if stopped_any:
                print("✅ BioAnalyzer application stopped")
            else:
                print("✅ No containers were running")
            return True

        except Exception as e:
            print(f"❌ Error stopping application: {e}")
            return False

    def restart_application(self):
        """Restart the BioAnalyzer application."""
        print("🔄 Restarting BioAnalyzer application...")
        self.stop_application()
        time.sleep(2)
        return self.start_application()

    def run_table(self, port: int = 8501) -> bool:
        """Run the curator table (Streamlit) in Docker for sortable/searchable predictions."""
        app_path = project_root / "curator_table" / "app.py"
        if not app_path.exists():
            print(f"❌ Curator table app not found: {app_path}")
            return False
        if not self.check_docker():
            return False
        if not self.check_image():
            print("❌ Docker image not found. Run 'BioAnalyzer build' first.")
            return False
        print("📋 Starting BioAnalyzer Curator Table (Docker)...")
        print(f"   Open http://localhost:{port} in your browser.")
        print("   Press Ctrl+C to stop.")
        env_flags = self._collect_env_flags()
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
            *env_flags,
            self.image_name,
            "streamlit",
            "run",
            "curator_table/app.py",
            "--server.port=8501",
            "--server.address=0.0.0.0",
        ]
        result = subprocess.run(cmd, cwd=project_root)
        return result.returncode == 0

    def check_backend_health(self):
        """Check if the API is healthy."""
        try:
            import requests

            response = requests.get("http://localhost:8000/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _wait_for_backend_health(self, timeout: int = 60, interval: float = 2) -> bool:
        """Poll the API /health endpoint until it reports healthy or we time out."""
        deadline = time.time() + timeout
        print(f"⏳ Waiting for API health (timeout: {timeout}s)...")
        while time.time() < deadline:
            if self.check_backend_health():
                return True
            time.sleep(max(0.5, interval))
        return False

    def get_system_status(self):
        """Get system status information."""
        print("📊 BioAnalyzer System Status")
        print("=" * 40)
        docker_available = self.check_docker()
        print(f"Docker: {'✅ Available' if docker_available else '❌ Not Available'}")

        if not docker_available:
            return
        image_exists = self.check_image()
        print(f"Package Image: {'✅ Built' if image_exists else '❌ Not Built'}")
        backend_running = False
        backend_status = ""
        for container_name in [self.container_name, "bioanalyzer-package"]:
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "ps",
                        "--filter",
                        f"name={container_name}",
                        "--format",
                        "{{.Status}}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                if result.stdout.strip():
                    backend_running = True
                    backend_status = result.stdout.strip()
                    break
            except:
                continue

        if backend_running:
            print(f"Package Container: ✅ {backend_status}")
        else:
            print("Package Container: ❌ Not Running")
        if self.check_backend_health():
            print("API Health: ✅ Healthy")
            print("🔧 API: http://localhost:8000")
            print("📖 API Documentation: http://localhost:8000/docs")
        else:
            print("API Health: ❌ Not Responding")
            if not backend_running:
                print("")
                print("💡 To get healthy: run  BioAnalyzer start")
                print("   If the package exits with permission errors, fix volume dirs:")
                print("   sudo chown -R $USER:$USER cache logs results")

    def handle_settings_command(self, args):
        """Handle settings commands."""
        try:
            from app.core.settings import SettingsManager, BioAnalyzerSettings
        except ImportError as e:
            print(f"❌ Error: Failed to import settings module: {e}")
            print("   Make sure you're running from the project root directory.")
            return

        manager = SettingsManager()

        if args.settings_command == "view":
            # Load current settings
            settings = manager.load()

            # Format output
            if args.format == "json":
                output = settings.model_dump_json(indent=2)
            elif args.format == "yaml":
                import yaml

                output = yaml.dump(
                    settings.model_dump(), default_flow_style=False, sort_keys=False
                )
            else:  # table format
                output = self._format_settings_table(settings)

            # Output
            if args.output:
                with open(args.output, "w") as f:
                    f.write(output)
                print(f"✅ Settings written to {args.output}")
            else:
                print(output)

        elif args.settings_command == "save":
            # Determine settings to save
            if args.preset:
                settings = BioAnalyzerSettings.from_preset(args.preset)
            else:
                settings = manager.load()

            # Save to file
            file_path = Path(args.file) if args.file else manager.DEFAULT_SETTINGS_FILE
            manager.save(settings, file_path, args.format)
            print(f"✅ Settings saved to {file_path}")
            if args.preset:
                print(f"   Preset: {args.preset}")

        elif args.settings_command == "load":
            # Load from file
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"❌ Error: Settings file not found: {file_path}")
                return

            settings = BioAnalyzerSettings.from_file(file_path)
            print(f"✅ Settings loaded from {file_path}")

            if args.apply:
                settings.apply_to_environment()
                print("✅ Settings applied to environment variables")

        elif args.settings_command == "preset":
            # Apply preset
            settings = BioAnalyzerSettings.from_preset(args.name)
            print(f"✅ Preset '{args.name}' loaded")

            if args.save:
                manager.save(settings)
                print(f"✅ Preset saved to {manager.DEFAULT_SETTINGS_FILE}")
            else:
                # Show what would be applied
                print("\n📋 Preset configuration:")
                print(self._format_settings_table(settings))
                print("\n💡 Tip: Use --save to save this preset to your settings file")

        elif args.settings_command == "migrate":
            # Migrate old settings
            old_file = Path(args.file)
            if not old_file.exists():
                print(f"❌ Error: Settings file not found: {old_file}")
                return

            output_file = (
                Path(args.output)
                if args.output
                else old_file.with_suffix(".new" + old_file.suffix)
            )
            migrated = manager.migrate_settings(old_file, output_file)
            print(f"✅ Settings migrated from {old_file} to {output_file}")

        else:
            print("❌ Error: Unknown settings command")
            print("   Available commands: view, save, load, preset, migrate")

    def _format_settings_table(self, settings: "BioAnalyzerSettings") -> str:
        """Format settings as a readable table."""
        lines = []
        lines.append("=" * 60)
        lines.append("BioAnalyzer Settings")
        lines.append("=" * 60)

        # Version and preset
        if settings.preset:
            lines.append(f"\n📦 Preset: {settings.preset}")
        lines.append(f"📌 Version: {settings.version}")
        lines.append(f"🌍 Environment: {settings.environment.value}")

        # API Settings
        lines.append("\n🔌 API Configuration:")
        lines.append(f"  Timeout: {settings.api.timeout}s")
        lines.append(f"  Analysis Timeout: {settings.api.analysis_timeout}s")
        lines.append(f"  Gemini Timeout: {settings.api.gemini_timeout}s")
        lines.append(
            f"  Max Concurrent Requests: {settings.api.max_concurrent_requests}"
        )
        lines.append(f"  NCBI Rate Limit Delay: {settings.api.ncbi_rate_limit_delay}s")

        # LLM Settings
        lines.append("\n🤖 LLM Configuration:")
        lines.append(f"  Provider: {settings.llm.provider or 'Auto-detect'}")
        lines.append(f"  Model: {settings.llm.model or 'Provider default'}")

        # RAG Settings
        lines.append("\n📚 RAG Configuration:")
        lines.append(f"  Enabled: {settings.rag.enabled}")
        lines.append(f"  Top K Chunks: {settings.rag.top_k_chunks}")
        lines.append(f"  Re-rank Method: {settings.rag.rerank_method.value}")
        lines.append(f"  Summary Length: {settings.rag.summary_length.value}")
        lines.append(f"  Summary Quality: {settings.rag.summary_quality.value}")
        lines.append(f"  Use Cache: {settings.rag.use_cache}")
        lines.append(f"  Max Key Points: {settings.rag.max_summary_key_points}")

        # Cache Settings
        lines.append("\n💾 Cache Configuration:")
        lines.append(f"  Enabled: {settings.cache.enabled}")
        lines.append(f"  Validity Hours: {settings.cache.validity_hours}")
        lines.append(f"  Max Size: {settings.cache.max_size}")
        lines.append(f"  Directory: {settings.cache.directory}")

        # Rate Limiting
        lines.append("\n⏱️  Rate Limiting:")
        lines.append(f"  Enabled: {settings.rate_limit.enabled}")
        lines.append(f"  Requests/Minute: {settings.rate_limit.requests_per_minute}")

        # Logging
        lines.append("\n📝 Logging Configuration:")
        lines.append(f"  Level: {settings.logging.level.value}")
        lines.append(f"  Directory: {settings.logging.directory}")
        lines.append(
            f"  Max File Size: {settings.logging.max_file_size / (1024*1024):.1f} MB"
        )
        lines.append(f"  Max Files: {settings.logging.max_files}")

        # Retrieval
        lines.append("\n🔍 Retrieval Configuration:")
        lines.append(f"  Use Fulltext: {settings.retrieval.use_fulltext}")
        lines.append(f"  NCBI API URL: {settings.retrieval.ncbi_api_url}")

        # Security
        lines.append("\n🔒 Security Configuration:")
        lines.append(f"  CORS Origins: {', '.join(settings.security.cors_origins)}")
        lines.append(f"  Request ID: {settings.security.enable_request_id}")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)

    def interactive_analysis(self):
        """Start interactive analysis mode."""
        self.print_banner()
        print("🔬 Interactive Analysis Mode")
        print("=" * 40)
        print("Enter PMIDs to analyze (one per line, or comma-separated)")
        print("Type 'help' for commands, 'quit' to exit")
        print()

        while True:
            try:
                user_input = input("BioAnalyzer> ").strip()

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("👋 Goodbye!")
                    break
                elif user_input.lower() == "help":
                    print(
                        """
📋 Available commands:
   <pmid>                    Analyze a single paper
   <pmid1,pmid2,pmid3>      Analyze multiple papers
   help                      Show this help
   quit                      Exit interactive mode
                    """
                    )
                    continue
                elif not user_input:
                    continue

                # Parse PMIDs
                pmids = []
                if "," in user_input:
                    pmids = [p.strip() for p in user_input.split(",") if p.strip()]
                else:
                    pmids = [user_input]

                if pmids:
                    print(f"🔬 Analyzing {len(pmids)} paper(s)...")
                    asyncio.run(self.analyze_papers_interactive(pmids))

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

    async def analyze_papers_interactive(self, pmids: List[str]):
        """Analyze papers in interactive mode."""
        try:
            import requests

            for i, pmid in enumerate(pmids, 1):
                print(f"\n[{i}/{len(pmids)}] Analyzing PMID: {pmid}")

                try:
                    # Use API instead of direct import
                    response = requests.get(
                        f"http://localhost:8000/api/v1/analyze/{pmid}", timeout=60
                    )

                    if response.status_code == 200:
                        result = response.json()
                        print(f"✅ Analysis completed for PMID {pmid}")

                        # Show quick summary
                        fields = result.get("fields", {})
                        present_count = sum(
                            1 for f in fields.values() if f.get("status") == "PRESENT"
                        )
                        print(f"   📊 Fields present: {present_count}/6")

                        # Show field status
                        field_names = {
                            "host_species": "Host Species",
                            "body_site": "Body Site",
                            "condition": "Condition",
                            "sequencing_type": "Sequencing Type",
                            "taxa_level": "Taxa Level",
                            "sample_size": "Sample Size",
                        }

                        for field_key, field_name in field_names.items():
                            field_data = fields.get(field_key, {})
                            status = field_data.get("status", "UNKNOWN")
                            status_icons = {
                                "PRESENT": "✅",
                                "PARTIALLY_PRESENT": "⚠️",
                                "ABSENT": "❌",
                            }
                            icon = status_icons.get(status, "❓")
                            print(f"   {icon} {field_name}: {status}")
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        print(f"❌ Analysis failed for PMID {pmid}: {error_detail}")

                except requests.exceptions.RequestException as e:
                    print(f"❌ Error connecting to API for PMID {pmid}: {e}")
                except Exception as e:
                    print(f"❌ Error analyzing PMID {pmid}: {e}")

        except ImportError:
            print(
                "❌ Error: requests module not available. Please install it: pip install requests"
            )
        except Exception as e:
            print(f"❌ Error: {e}")

    async def analyze_papers(
        self,
        pmids: List[str],
        output_format: str = "table",
        output_file: Optional[str] = None,
    ):
        """Analyze papers and return results."""
        try:
            import requests

            results = []
            total = len(pmids)

            print(f"🔬 Analyzing {total} paper(s)...")

            for i, pmid in enumerate(pmids, 1):
                print(f"[{i}/{total}] Analyzing PMID: {pmid}")

                try:
                    # Use API instead of direct import
                    response = requests.get(
                        f"http://localhost:8000/api/v1/analyze/{pmid}", timeout=60
                    )

                    if response.status_code == 200:
                        result = response.json()
                        results.append(result)
                        print(f"✅ Analysis completed for PMID {pmid}")
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        print(f"❌ Analysis failed for PMID {pmid}: {error_detail}")

                except requests.exceptions.RequestException as e:
                    print(f"❌ Error connecting to API for PMID {pmid}: {e}")
                except Exception as e:
                    print(f"❌ Error analyzing PMID {pmid}: {e}")

            if results:
                if output_file:
                    self.save_results(results, output_file, output_format)
                    print(
                        f"✅ Successfully analyzed {len(results)} out of {total} paper(s)"
                    )
                    if len(results) < total:
                        print(
                            f"⚠️  {total - len(results)} paper(s) failed or were skipped"
                        )
                else:
                    self.display_results(results, output_format)
            else:
                print("❌ No results obtained.")
                if output_file:
                    print(f"⚠️  No results to save to {output_file}")

        except ImportError:
            print(
                "❌ Error: requests module not available. Please install it: pip install requests"
            )
        except Exception as e:
            print(f"❌ Error: {e}")

    def display_results(self, results: List[Dict[str, Any]], output_format: str):
        """Display results in the specified format."""
        if output_format == "json":
            print(json.dumps(results, indent=2, ensure_ascii=False))
        elif output_format == "csv":
            self.display_csv_results(results)
        elif output_format == "xml":
            self.display_xml_results(results)
        else:
            self.display_table_results(results)

    def display_table_results(self, results: List[Dict[str, Any]]):
        """Display results in table format."""
        if not results:
            print("No results to display.")
            return

        print("\n" + "=" * 80)
        print("🧬 BIOANALYZER - CURATABLE SIGNATURE ANALYSIS RESULTS")
        print("=" * 80)

        for result in results:
            print(f"\n📄 PMID: {result.get('pmid', 'N/A')}")
            print(f"📝 Title: {result.get('title', 'N/A')}")
            print(f"📰 Journal: {result.get('journal', 'N/A')}")
            print("-" * 60)

            fields = result.get("fields", {})
            field_names = {
                "host_species": "Host Species",
                "body_site": "Body Site",
                "condition": "Condition",
                "sequencing_type": "Sequencing Type",
                "taxa_level": "Taxa Level",
                "sample_size": "Sample Size",
            }

            for field_key, field_name in field_names.items():
                field_data = fields.get(field_key, {})
                status = field_data.get("status", "UNKNOWN")
                value = field_data.get("value", "N/A")
                confidence = field_data.get("confidence", 0.0)

                status_icons = {
                    "PRESENT": "✅",
                    "PARTIALLY_PRESENT": "⚠️",
                    "ABSENT": "❌",
                }
                icon = status_icons.get(status, "❓")

                print(
                    f"{icon} {field_name:20} | {status:20} | {str(value):30} | {confidence:.2f}"
                )

            print("-" * 60)
            print(f"📋 Summary: {result.get('curation_summary', 'N/A')}")
            print(f"⏱️  Time: {result.get('processing_time', 0):.2f}s")
            print()

    def display_csv_results(self, results: List[Dict[str, Any]]):
        """Display results in CSV format."""
        if not results:
            print("No results to display.")
            return
        print(self.get_csv_content(results))

    def display_xml_results(self, results: List[Dict[str, Any]]):
        """Display results in XML format."""
        if not results:
            print("No results to display.")
            return
        print(self.get_xml_content(results))

    def _collect_urls(
        self, inline_urls: List[str], file_path: Optional[str]
    ) -> List[str]:
        """Collect URLs from CLI arguments and optional file."""
        urls = []

        for value in inline_urls or []:
            if "," in value:
                urls.extend([item.strip() for item in value.split(",") if item.strip()])
            else:
                urls.append(value.strip())

        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    urls.extend(line.strip() for line in handle if line.strip())
            except Exception as exc:
                print(f"❌ Error reading URL file: {exc}")

        # Remove duplicates while preserving order
        cleaned_urls = []
        seen = set()
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                cleaned_urls.append(url)
        return cleaned_urls

    def handle_url_analysis(
        self,
        urls: List[str],
        file_path: Optional[str],
        embedding_model: str,
        llm_model: str,
        output_format: str,
        output_file: Optional[str],
        poll_interval: int,
        timeout: int,
    ):
        """Entry point for the analyze-url command."""
        all_urls = self._collect_urls(urls, file_path)
        if not all_urls:
            print("❌ Error: No URLs provided.")
            print("Usage: BioAnalyzer analyze-url <url1> [url2]")
            print("   or: BioAnalyzer analyze-url --file urls.txt")
            return

        results = []
        for index, url in enumerate(all_urls, 1):
            print(f"\n[{index}/{len(all_urls)}] Starting analysis for URL: {url}")
            job_id = self._start_url_analysis_job(url, embedding_model, llm_model)
            if not job_id:
                continue

            analysis_result = self._poll_url_analysis_job(
                job_id=job_id, poll_interval=poll_interval, timeout=timeout
            )

            if analysis_result:
                analysis_result["job_id"] = job_id
                results.append(analysis_result)

        if not results:
            print("❌ No URL analyses completed successfully.")
            return

        if output_file:
            self.save_url_analysis_results(results, output_file, output_format)
        else:
            self.display_url_analysis_results(results, output_format)

    def _start_url_analysis_job(
        self, url: str, embedding_model: str, llm_model: str
    ) -> Optional[str]:
        """Submit a new URL analysis job."""
        try:
            payload = {
                "url": url,
                "embedding_model": embedding_model,
                "llm_model": llm_model,
            }
            response = requests.post(
                self._build_api_url("/analyze-url"), json=payload, timeout=30
            )
            if response.status_code != 200:
                detail = response.json().get("detail", response.text)
                print(f"❌ Failed to start analysis for {url}: {detail}")
                return None

            job_info = response.json()
            job_id = job_info.get("job_id")
            print(f"🆔 Job ID: {job_id}")
            return job_id
        except requests.exceptions.RequestException as exc:
            print(f"❌ Network error starting URL analysis: {exc}")
            return None

    def _poll_url_analysis_job(
        self, job_id: str, poll_interval: int, timeout: int
    ) -> Optional[Dict[str, Any]]:
        """Poll the status endpoint until the job completes or fails."""
        deadline = time.time() + timeout
        status_url = self._build_api_url(f"/analysis-status/{job_id}")
        result_url = self._build_api_url(f"/analysis-result/{job_id}")

        while time.time() < deadline:
            try:
                status_response = requests.get(status_url, timeout=15)
                if status_response.status_code != 200:
                    print(f"❌ Failed to fetch status for job {job_id}")
                    return None

                status_payload = status_response.json()
                job_status = status_payload.get("status", "unknown")
                progress = status_payload.get("progress", "")
                print(f"   ⏳ Status: {job_status} ({progress})")

                if job_status == "completed":
                    return self._fetch_url_analysis_result(result_url)
                if job_status == "failed":
                    print(
                        f"❌ Job {job_id} failed: {status_payload.get('error', 'Unknown error')}"
                    )
                    return None

                time.sleep(max(1, poll_interval))
            except requests.exceptions.RequestException as exc:
                print(f"❌ Error polling job {job_id}: {exc}")
                time.sleep(max(1, poll_interval))

        print(f"⚠️  Job {job_id} timed out after {timeout} seconds")
        return None

    def _fetch_url_analysis_result(self, result_url: str) -> Optional[Dict[str, Any]]:
        """Fetch the completed analysis result."""
        try:
            response = requests.get(result_url, timeout=30)
            if response.status_code != 200:
                detail = response.json().get("detail", response.text)
                print(f"❌ Failed to fetch analysis result: {detail}")
                return None
            return response.json()
        except requests.exceptions.RequestException as exc:
            print(f"❌ Error retrieving analysis result: {exc}")
            return None

    def display_url_analysis_results(
        self, results: List[Dict[str, Any]], output_format: str
    ):
        """Display URL workflow results."""
        if not results:
            print("No URL analysis results to display.")
            return

        if output_format == "json":
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return

        print("\n" + "=" * 80)
        print("🌐 BIOANALYZER - URL STUDY ANALYSIS RESULTS")
        print("=" * 80)

        for result in results:
            print(f"\n🔗 Source URL: {result.get('source_url', 'N/A')}")
            print(f"🆔 Job ID: {result.get('job_id', 'N/A')}")
            print(f"🧪 Experiments: {len(result.get('experiments', []))}")
            print(f"🧬 Total Signatures: {result.get('total_signatures', 0)}")
            print(
                f"✅ Curation Ready: {'Yes' if result.get('curation_ready') else 'No'}"
            )
            print(
                f"⚠️  Missing Fields: {', '.join(result.get('missing_fields', [])) or 'None'}"
            )
            print(f"📊 Confidence Score: {result.get('confidence_score', 0.0):.2f}")
            print("-" * 60)

            for exp in result.get("experiments", []):
                metadata = exp.get("metadata", {})
                print(f"   • Experiment: {exp.get('title', 'Untitled')}")
                print(f"     Host Species: {metadata.get('host_species', 'N/A')}")
                print(f"     Body Site   : {metadata.get('body_site', 'N/A')}")
                print(f"     Condition   : {metadata.get('condition', 'N/A')}")
                print(f"     Sequencing  : {metadata.get('sequencing_type', 'N/A')}")
                print(f"     Taxa Level  : {metadata.get('taxa_level', 'N/A')}")
                print(f"     Sample Size : {metadata.get('sample_size', 'N/A')}")
                if exp.get("signatures"):
                    print(f"     Signatures  : {len(exp['signatures'])}")
                else:
                    print("     Signatures  : None detected")
                print()

    def save_url_analysis_results(
        self, results: List[Dict[str, Any]], filename: str, output_format: str
    ):
        """Save URL analysis results to disk."""
        if output_format == "json":
            content = json.dumps(results, indent=2, ensure_ascii=False)
        else:
            content = self.get_url_analysis_table_content(results)

        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(content)

        print(f"💾 URL analysis results saved to: {filename}")

    def get_url_analysis_table_content(self, results: List[Dict[str, Any]]) -> str:
        """Generate a text table for URL analyses."""
        lines = ["BIOANALYZER - URL STUDY ANALYSIS RESULTS", "=" * 60, ""]
        for result in results:
            lines.append(f"Source URL: {result.get('source_url', 'N/A')}")
            lines.append(f"Experiments: {len(result.get('experiments', []))}")
            lines.append(f"Total Signatures: {result.get('total_signatures', 0)}")
            lines.append(
                f"Curation Ready: {'Yes' if result.get('curation_ready') else 'No'}"
            )
            lines.append(
                f"Missing Fields: {', '.join(result.get('missing_fields', [])) or 'None'}"
            )
            lines.append("")
            for exp in result.get("experiments", []):
                meta = exp.get("metadata", {})
                lines.append(f"  - {exp.get('title', 'Untitled')}")
                lines.append(f"    Host Species : {meta.get('host_species', 'N/A')}")
                lines.append(f"    Body Site    : {meta.get('body_site', 'N/A')}")
                lines.append(f"    Condition    : {meta.get('condition', 'N/A')}")
                lines.append(f"    Sequencing   : {meta.get('sequencing_type', 'N/A')}")
                lines.append(f"    Taxa Level   : {meta.get('taxa_level', 'N/A')}")
                lines.append(f"    Sample Size  : {meta.get('sample_size', 'N/A')}")
                if exp.get("signatures"):
                    lines.append(f"    Signatures   : {len(exp['signatures'])}")
                else:
                    lines.append("    Signatures   : None")
                lines.append("")
            lines.append("-" * 60)
        return "\n".join(lines)

    def save_results(
        self, results: List[Dict[str, Any]], filename: str, output_format: str
    ):
        """Save results to a file."""
        if output_format == "json":
            content = json.dumps(results, indent=2, ensure_ascii=False)
        elif output_format == "csv":
            content = self.get_csv_content(results)
        elif output_format == "xml":
            content = self.get_xml_content(results)
        else:
            content = self.get_table_content(results)

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"💾 Results saved to: {filename}")

    def get_csv_content(self, results: List[Dict[str, Any]]) -> str:
        """Get CSV content for results."""
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        headers = [
            "PMID",
            "Title",
            "Journal",
            "Host Species",
            "Host Species Status",
            "Body Site",
            "Body Site Status",
            "Condition",
            "Condition Status",
            "Sequencing Type",
            "Sequencing Type Status",
            "Taxa Level",
            "Taxa Level Status",
            "Sample Size",
            "Sample Size Status",
            "Summary",
            "Processing Time",
        ]
        writer.writerow(headers)

        # Data rows
        for result in results:
            fields = result.get("fields", {})
            row = [
                result.get("pmid", ""),
                result.get("title", ""),
                result.get("journal", ""),
                fields.get("host_species", {}).get("value", ""),
                fields.get("host_species", {}).get("status", ""),
                fields.get("body_site", {}).get("value", ""),
                fields.get("body_site", {}).get("status", ""),
                fields.get("condition", {}).get("value", ""),
                fields.get("condition", {}).get("status", ""),
                fields.get("sequencing_type", {}).get("value", ""),
                fields.get("sequencing_type", {}).get("status", ""),
                fields.get("taxa_level", {}).get("value", ""),
                fields.get("taxa_level", {}).get("status", ""),
                fields.get("sample_size", {}).get("value", ""),
                fields.get("sample_size", {}).get("status", ""),
                result.get("curation_summary", ""),
                result.get("processing_time", 0),
            ]
            writer.writerow(row)

        return output.getvalue()

    def get_xml_content(self, results: List[Dict[str, Any]]) -> str:
        """Get XML content for results."""
        if not results:
            return '<?xml version="1.0" encoding="UTF-8"?>\n<BioAnalyzerResults></BioAnalyzerResults>'

        xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_content.append("<BioAnalyzerResults>")

        for result in results:
            xml_content.append("  <Analysis>")
            xml_content.append(f'    <PMID>{result.get("pmid", "")}</PMID>')
            xml_content.append(f'    <Title>{result.get("title", "")}</Title>')
            xml_content.append(f'    <Journal>{result.get("journal", "")}</Journal>')
            xml_content.append(
                f'    <ProcessingTime>{result.get("processing_time", 0)}</ProcessingTime>'
            )

            fields = result.get("fields", {})
            xml_content.append("    <Fields>")

            field_names = {
                "host_species": "HostSpecies",
                "body_site": "BodySite",
                "condition": "Condition",
                "sequencing_type": "SequencingType",
                "taxa_level": "TaxaLevel",
                "sample_size": "SampleSize",
            }

            for field_key, field_name in field_names.items():
                field_data = fields.get(field_key, {})
                status = field_data.get("status", "UNKNOWN")
                value = field_data.get("value", "N/A")
                confidence = field_data.get("confidence", 0.0)

                xml_content.append(f"      <{field_name}>")
                xml_content.append(f"        <Status>{status}</Status>")
                xml_content.append(f"        <Value><![CDATA[{value}]]></Value>")
                xml_content.append(f"        <Confidence>{confidence:.2f}</Confidence>")
                xml_content.append(f"      </{field_name}>")

            xml_content.append("    </Fields>")
            xml_content.append(
                f'    <Summary><![CDATA[{result.get("curation_summary", "")}]]></Summary>'
            )
            xml_content.append("  </Analysis>")

        xml_content.append("</BioAnalyzerResults>")
        return "\n".join(xml_content)

    def get_table_content(self, results: List[Dict[str, Any]]) -> str:
        """Get table content for results."""
        return "Table content implementation"

    def show_fields_info(self):
        """Show information about BugSigDB fields."""
        print(
            """
🧬 BioAnalyzer - BugSigDB Essential Fields
==========================================

📋 6 Essential Fields for BugSigDB Curation:

🧬 Host Species (host_species):
   Description: The host organism being studied (e.g., Human, Mouse, Rat)
   Required: Yes

📍 Body Site (body_site):
   Description: Where the microbiome sample was collected (e.g., Gut, Oral, Skin)
   Required: Yes

🏥 Condition (condition):
   Description: What disease, treatment, or exposure is being studied
   Required: Yes

🔬 Sequencing Type (sequencing_type):
   Description: What molecular method was used (e.g., 16S, metagenomics)
   Required: Yes

🌳 Taxa Level (taxa_level):
   Description: What taxonomic level was analyzed (e.g., phylum, genus, species)
   Required: Yes

👥 Sample Size (sample_size):
   Description: Number of samples or participants analyzed
   Required: Yes

📊 Field Status Values:
   ✅ PRESENT: Information is complete and clear
   ⚠️  PARTIALLY_PRESENT: Some information available but incomplete
   ❌ ABSENT: Information is missing
        """
        )

    def interactive_qa(self):
        """Start interactive Q&A mode."""
        self.print_banner()
        print("💬 Interactive Q&A Mode")
        print("=" * 40)
        print("Ask any question and get AI-powered answers!")
        print("Type 'help' for commands, 'quit' to exit")
        print()

        import requests

        api_available = False
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                api_available = True
        except:
            pass

        if not api_available:
            print("⚠️  Docker API is not running.")
            print("   Please start BioAnalyzer first: BioAnalyzer start")
            print("   Then the Q&A feature will use the API with all dependencies.")
            return

        print("✅ Connected to BioAnalyzer API")

        print("✅ QA system ready! Ask your questions below.\n")

        while True:
            try:
                user_input = input("BioAnalyzer Q&A> ").strip()

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("👋 Goodbye!")
                    break
                elif user_input.lower() == "help":
                    print(
                        """
📋 Available commands:
   <question>                 Ask any question
   help                       Show this help
   quit                       Exit interactive mode

💡 Examples:
   "What is the microbiome?"
   "Explain 16S rRNA sequencing"
   "What are the differences between metagenomics and 16S sequencing?"
                    """
                    )
                    continue
                elif not user_input:
                    continue

                # Ask the question via API
                print("\n🤔 Thinking...")
                try:
                    # Use API endpoint for Q&A (if available) or fallback to direct call
                    api_response = requests.post(
                        "http://localhost:8000/api/v1/qa",
                        json={"question": user_input},
                        timeout=60,
                    )

                    if api_response.status_code == 200:
                        result = api_response.json()
                        answer = result.get("answer", result.get("text", ""))
                        confidence = result.get("confidence", 0.8)

                        if answer:
                            print(f"\n💡 Answer (confidence: {confidence:.2f}):")
                            print("-" * 60)
                            print(answer)
                            print("-" * 60)
                        else:
                            print(
                                "❌ No answer received. Please try rephrasing your question."
                            )
                    elif api_response.status_code == 404:
                        # Q&A endpoint not available, try direct import as fallback
                        print(
                            "⚠️  Q&A API endpoint not available. Trying direct method..."
                        )
                        # Fallback would go here if we want to support it
                        print("❌ Q&A endpoint not implemented in API yet.")
                        print(
                            "   Please use the web interface or wait for API endpoint."
                        )
                    else:
                        error_detail = api_response.json().get(
                            "detail", "Unknown error"
                        )
                        print(f"❌ API error: {error_detail}")
                except requests.exceptions.RequestException as e:
                    print(f"❌ Error connecting to API: {e}")
                    print("   Make sure BioAnalyzer is running: BioAnalyzer start")
                except Exception as e:
                    print(f"❌ Error: {e}")

                print()  # Empty line for readability

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

    async def ask_question(self, question: str) -> Optional[str]:
        """
        Ask a single question and return the answer via API.

        Args:
            question: The question to ask

        Returns:
            The answer text or None if error
        """
        import requests

        api_available = False
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                api_available = True
        except:
            pass

        if not api_available:
            print("⚠️  Docker API is not running.")
            print("   Please start BioAnalyzer first: BioAnalyzer start")
            return None

        try:
            print("🤔 Thinking...")
            # Use API endpoint for Q&A
            api_response = requests.post(
                "http://localhost:8000/api/v1/qa",
                json={"question": question},
                timeout=60,
            )

            if api_response.status_code == 200:
                result = api_response.json()
                answer = result.get("answer", result.get("text", ""))
                confidence = result.get("confidence", 0.8)

                if answer:
                    print(f"\n💡 Answer (confidence: {confidence:.2f}):")
                    print("-" * 60)
                    print(answer)
                    print("-" * 60)
                    return answer
                else:
                    print("❌ No answer received.")
                    return None
            elif api_response.status_code == 404:
                print("⚠️  Q&A API endpoint not available yet.")
                print(
                    "   Please use: BioAnalyzer start (then access via web interface)"
                )
                return None
            else:
                error_detail = api_response.json().get("detail", "Unknown error")
                print(f"❌ API error: {error_detail}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"❌ Error connecting to API: {e}")
            print("   Make sure BioAnalyzer is running: BioAnalyzer start")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    async def retrieve_papers(
        self,
        pmids: List[str],
        output_format: str = "table",
        output_file: Optional[str] = None,
        save_to_file: bool = False,
    ):
        """Retrieve papers and return results."""
        try:
            retriever = self._get_pubmed_retriever()
            results = self._fetch_papers_data(retriever, pmids)
            self._process_retrieval_results(
                results, output_format, output_file, save_to_file
            )
        except Exception as e:
            self._handle_retrieval_error(e)

    def _get_pubmed_retriever(self):
        """Get a PubMed retriever instance."""
        try:
            from app.services.standalone_pubmed_retriever import (
                StandalonePubMedRetriever,
            )

            return StandalonePubMedRetriever()
        except ImportError:
            # Fallback to inline implementation
            return self._create_standalone_retriever()

    def _fetch_papers_data(self, retriever, pmids: List[str]) -> List[Dict[str, Any]]:
        """Fetch paper data for all PMIDs."""
        total = len(pmids)
        print(f"📥 Retrieving {total} paper(s)...")

        results = []
        for i, pmid in enumerate(pmids, 1):
            paper_data = self._fetch_single_paper(retriever, pmid)
            self._log_retrieval_progress(i, total, paper_data)
            results.append(paper_data)

        return results

    def _fetch_single_paper(self, retriever, pmid: str) -> Dict[str, Any]:
        """Fetch data for a single paper."""
        try:
            return retriever.get_full_paper_data(pmid)
        except Exception as e:
            return {
                "pmid": pmid,
                "error": f"Retrieval failed: {str(e)}",
                "retrieval_timestamp": time.time(),
            }

    def _log_retrieval_progress(
        self, current: int, total: int, paper_data: Dict[str, Any]
    ):
        """Log the progress of paper retrieval."""
        pmid = paper_data.get("pmid", "unknown")
        print(f"[{current}/{total}] Retrieved PMID: {pmid}")

        if "error" in paper_data:
            print(f"❌ Retrieval failed for PMID {pmid}: {paper_data['error']}")
        else:
            print(f"✅ Successfully retrieved PMID {pmid}")
            if paper_data.get("has_full_text"):
                print("   📖 Full text available")
            else:
                print("   📄 Abstract only")

    def _process_retrieval_results(
        self,
        results: List[Dict[str, Any]],
        output_format: str,
        output_file: Optional[str],
        save_to_file: bool,
    ):
        """Process and output the retrieval results."""
        if not results:
            print("❌ No results obtained.")
            return

        if save_to_file:
            self._save_individual_papers(results)

        if output_file:
            self.save_retrieval_results(results, output_file, output_format)
        else:
            self.display_retrieval_results(results, output_format)

    def _save_individual_papers(self, results: List[Dict[str, Any]]):
        """Save individual papers to separate files."""
        for paper_data in results:
            if "error" not in paper_data:
                self._save_individual_paper(paper_data)

    def _handle_retrieval_error(self, error: Exception):
        """Handle retrieval errors."""
        print(f"❌ Error: {error}")
        print("Please check your internet connection and try again.")

    def _create_standalone_retriever(self):
        """Create a fallback standalone PubMed retriever."""
        import requests
        from xml.etree import ElementTree

        class FallbackRetriever:
            def __init__(self):
                self.session = requests.Session()
                self.session.headers.update(
                    {"User-Agent": "BioAnalyzer/1.0 (contact: bioanalyzer@example.com)"}
                )

            def get_full_paper_data(self, pmid: str) -> Dict[str, Any]:
                try:
                    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                    params = {
                        "db": "pubmed",
                        "id": pmid,
                        "retmode": "xml",
                        "email": "bioanalyzer@example.com",
                        "tool": "BioAnalyzer",
                    }

                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()

                    root = ElementTree.fromstring(response.text)
                    article = root.find(".//PubmedArticle/MedlineCitation/Article")

                    if article is None:
                        return {"pmid": pmid, "error": "No article found"}

                    title = article.findtext("ArticleTitle", default="N/A")
                    journal = article.findtext("Journal/Title", default="N/A")

                    return {
                        "pmid": pmid,
                        "title": title,
                        "abstract": "",
                        "journal": journal,
                        "authors": [],
                        "publication_date": "",
                        "full_text": "",
                        "has_full_text": False,
                        "retrieval_timestamp": time.time(),
                    }
                except Exception as e:
                    return {
                        "pmid": pmid,
                        "error": f"Retrieval failed: {str(e)}",
                        "retrieval_timestamp": time.time(),
                    }

        return FallbackRetriever()

    def _save_individual_paper(self, paper_data: Dict[str, Any]) -> str:
        """Save individual paper data to a JSON file."""
        try:
            pmid = paper_data.get("pmid", "unknown")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"paper_data_{pmid}_{timestamp}.json"
            filepath = Path("results") / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(paper_data, f, indent=2, ensure_ascii=False)

            print(f"   💾 Saved to: {filepath}")
            return str(filepath)

        except Exception as e:
            print(f"   ❌ Error saving paper data: {e}")
            return ""

    def display_retrieval_results(
        self, results: List[Dict[str, Any]], output_format: str
    ):
        """Display retrieval results in the specified format."""
        if output_format == "json":
            print(json.dumps(results, indent=2, ensure_ascii=False))
        elif output_format == "csv":
            self.display_csv_retrieval_results(results)
        else:
            self.display_table_retrieval_results(results)

    def display_table_retrieval_results(self, results: List[Dict[str, Any]]):
        """Display retrieval results in table format."""
        if not results:
            print("No results to display.")
            return

        print("\n" + "=" * 80)
        print("📥 BIOANALYZER - PUBMED PAPER RETRIEVAL RESULTS")
        print("=" * 80)

        for result in results:
            if "error" in result:
                print(f"\n❌ PMID: {result.get('pmid', 'N/A')}")
                print(f"Error: {result['error']}")
                continue

            print(f"\n📄 PMID: {result.get('pmid', 'N/A')}")
            print(f"📝 Title: {result.get('title', 'N/A')}")
            print(f"📰 Journal: {result.get('journal', 'N/A')}")
            print(
                f"👥 Authors: {', '.join(result.get('authors', [])[:3])}{' et al.' if len(result.get('authors', [])) > 3 else ''}"
            )
            print(f"📅 Publication Date: {result.get('publication_date', 'N/A')}")
            print(
                f"📖 Full Text: {'✅ Available' if result.get('has_full_text') else '❌ Not available'}"
            )

            # Show abstract preview
            abstract = result.get("abstract", "")
            if abstract:
                preview = abstract[:200] + "..." if len(abstract) > 200 else abstract
                print(f"📋 Abstract Preview: {preview}")

            # Show full text preview if available
            if result.get("has_full_text"):
                full_text = result.get("full_text", "")
                if full_text:
                    preview = (
                        full_text[:300] + "..." if len(full_text) > 300 else full_text
                    )
                    print(f"📄 Full Text Preview: {preview}")

            print("-" * 60)

    def display_csv_retrieval_results(self, results: List[Dict[str, Any]]):
        """Display retrieval results in CSV format."""
        if not results:
            print("No results to display.")
            return
        print(self.get_csv_retrieval_content(results))

    def save_retrieval_results(
        self, results: List[Dict[str, Any]], filename: str, output_format: str
    ):
        """Save retrieval results to a file."""
        if output_format == "json":
            content = json.dumps(results, indent=2, ensure_ascii=False)
        elif output_format == "csv":
            content = self.get_csv_retrieval_content(results)
        else:
            content = self.get_table_retrieval_content(results)

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"💾 Retrieval results saved to: {filename}")

    def get_csv_retrieval_content(self, results: List[Dict[str, Any]]) -> str:
        """Get CSV content for retrieval results."""
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        headers = [
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
        writer.writerow(headers)

        # Data rows
        for result in results:
            row = [
                result.get("pmid", ""),
                result.get("title", ""),
                result.get("journal", ""),
                "; ".join(result.get("authors", [])),
                result.get("publication_date", ""),
                "Yes" if result.get("has_full_text") else "No",
                len(result.get("abstract", "")),
                len(result.get("full_text", "")),
                result.get("error", ""),
            ]
            writer.writerow(row)

        return output.getvalue()

    def get_table_retrieval_content(self, results: List[Dict[str, Any]]) -> str:
        """Get table content for retrieval results."""
        content = "BIOANALYZER - PUBMED PAPER RETRIEVAL RESULTS\n"
        content += "=" * 50 + "\n\n"

        for result in results:
            if "error" in result:
                content += f"PMID: {result.get('pmid', 'N/A')}\n"
                content += f"Error: {result['error']}\n\n"
                continue

            content += f"PMID: {result.get('pmid', 'N/A')}\n"
            content += f"Title: {result.get('title', 'N/A')}\n"
            content += f"Journal: {result.get('journal', 'N/A')}\n"
            content += f"Authors: {', '.join(result.get('authors', [])[:3])}{' et al.' if len(result.get('authors', [])) > 3 else ''}\n"
            content += f"Publication Date: {result.get('publication_date', 'N/A')}\n"
            content += f"Full Text: {'Available' if result.get('has_full_text') else 'Not available'}\n"

            abstract = result.get("abstract", "")
            if abstract:
                content += f"Abstract: {abstract[:200]}{'...' if len(abstract) > 200 else ''}\n"

            content += "\n" + "-" * 40 + "\n\n"

        return content


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="BioAnalyzer - User-Friendly BugSigDB Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  BioAnalyzer help                    # Show help
  BioAnalyzer build                   # Build containers
  BioAnalyzer start                   # Start application
  BioAnalyzer run table               # Run curator table (Streamlit)
  BioAnalyzer analyze 12345678        # Analyze single paper
  BioAnalyzer analyze 12345678,87654321  # Analyze multiple papers
  BioAnalyzer retrieve 12345678       # Retrieve single paper
  BioAnalyzer retrieve 12345678,87654321 --save  # Retrieve multiple papers and save
  BioAnalyzer fields                  # Show field information
  BioAnalyzer qa "What is 16S sequencing?"  # Ask a question
  BioAnalyzer qa --interactive         # Interactive Q&A mode
  BioAnalyzer status                  # Check status
  BioAnalyzer stop                    # Stop application
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Help command
    help_parser = subparsers.add_parser("help", help="Show help information")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build Docker containers")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the application")
    start_parser.add_argument(
        "--interactive", "-i", action="store_true", help="Start in interactive mode"
    )

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the application")

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart the application")

    # Run command (optional components)
    run_parser = subparsers.add_parser("run", help="Run optional components")
    run_subparsers = run_parser.add_subparsers(dest="run_command", help="Component to run")
    run_table_parser = run_subparsers.add_parser(
        "table", help="Run curator table (sortable/searchable predictions)"
    )
    run_table_parser.add_argument(
        "--port", "-p", type=int, default=8501, help="Port for Streamlit (default: 8501)"
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Check system status")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze papers")
    analyze_parser.add_argument("pmids", nargs="*", help="PubMed IDs to analyze")
    analyze_parser.add_argument("--file", "-f", help="File containing PMIDs")
    analyze_parser.add_argument(
        "--format",
        choices=["table", "json", "csv", "xml"],
        default="table",
        help="Output format",
    )
    analyze_parser.add_argument("--output", "-o", help="Output file")
    analyze_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )

    # Analyze URL command
    analyze_url_parser = subparsers.add_parser("analyze-url", help="Analyze study URLs")
    analyze_url_parser.add_argument("urls", nargs="*", help="Study URLs to analyze")
    analyze_url_parser.add_argument("--file", "-f", help="File containing study URLs")
    analyze_url_parser.add_argument(
        "--embedding-model",
        default="gemini/text-embedding-004",
        help="Embedding model identifier",
    )
    analyze_url_parser.add_argument(
        "--llm-model", default="gemini/gemini-2.0-flash", help="LLM model identifier"
    )
    analyze_url_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format for results",
    )
    analyze_url_parser.add_argument("--output", "-o", help="File to save results")
    analyze_url_parser.add_argument(
        "--poll-interval", type=int, default=5, help="Seconds between status polls"
    )
    analyze_url_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Time in seconds before giving up on a job",
    )
    analyze_url_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )

    # Fields command
    fields_parser = subparsers.add_parser("fields", help="Show field information")

    # Q&A command
    qa_parser = subparsers.add_parser(
        "qa", help="Ask questions and get AI-powered answers"
    )
    qa_parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask (optional, will start interactive mode if not provided)",
    )
    qa_parser.add_argument(
        "--interactive", "-i", action="store_true", help="Start interactive Q&A mode"
    )

    # Retrieve command
    retrieve_parser = subparsers.add_parser(
        "retrieve", help="Retrieve full paper text and metadata"
    )
    retrieve_parser.add_argument("pmids", nargs="*", help="PubMed IDs to retrieve")
    retrieve_parser.add_argument("--file", "-f", help="File containing PMIDs")
    retrieve_parser.add_argument(
        "--format",
        choices=["table", "json", "csv", "xml"],
        default="table",
        help="Output format",
    )
    retrieve_parser.add_argument("--output", "-o", help="Output file")
    retrieve_parser.add_argument(
        "--save", "-s", action="store_true", help="Save individual paper data to files"
    )
    retrieve_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )

    # Settings command
    settings_parser = subparsers.add_parser(
        "settings", help="Manage BioAnalyzer settings"
    )
    settings_subparsers = settings_parser.add_subparsers(
        dest="settings_command", help="Settings commands"
    )

    # Settings view command
    settings_view_parser = settings_subparsers.add_parser(
        "view", help="View current settings"
    )
    settings_view_parser.add_argument(
        "--format",
        choices=["json", "yaml", "table"],
        default="table",
        help="Output format",
    )
    settings_view_parser.add_argument("--output", "-o", help="Output file (optional)")

    # Settings save command
    settings_save_parser = settings_subparsers.add_parser(
        "save", help="Save current settings to file"
    )
    settings_save_parser.add_argument(
        "--file",
        "-f",
        help="Settings file path (default: ~/.bioanalyzer/settings.json)",
    )
    settings_save_parser.add_argument(
        "--format", choices=["json", "yaml"], default="json", help="File format"
    )
    settings_save_parser.add_argument(
        "--preset",
        choices=["fast", "balanced", "high_quality", "development", "production"],
        help="Save preset configuration",
    )

    # Settings load command
    settings_load_parser = settings_subparsers.add_parser(
        "load", help="Load settings from file"
    )
    settings_load_parser.add_argument(
        "--file", "-f", required=True, help="Settings file path"
    )
    settings_load_parser.add_argument(
        "--apply", action="store_true", help="Apply loaded settings to environment"
    )

    # Settings preset command
    settings_preset_parser = settings_subparsers.add_parser(
        "preset", help="Apply preset configuration"
    )
    settings_preset_parser.add_argument(
        "name",
        choices=["fast", "balanced", "high_quality", "development", "production"],
        help="Preset name",
    )
    settings_preset_parser.add_argument(
        "--save", "-s", action="store_true", help="Save preset to settings file"
    )

    # Settings migrate command
    settings_migrate_parser = settings_subparsers.add_parser(
        "migrate", help="Migrate old settings to new format"
    )
    settings_migrate_parser.add_argument(
        "--file", "-f", required=True, help="Old settings file path"
    )
    settings_migrate_parser.add_argument(
        "--output", "-o", help="Output file for migrated settings"
    )

    args = parser.parse_args()

    cli = BioAnalyzerCLI()
    cli.verbose = args.verbose if hasattr(args, "verbose") else False

    if not args.command or args.command == "help":
        cli.print_help()
        return

    if args.command == "build":
        cli.build_containers()
        return

    if args.command == "start":
        if args.interactive:
            cli.start_application()
            cli.interactive_analysis()
        else:
            cli.start_application()
        return

    if args.command == "stop":
        cli.stop_application()
        return

    if args.command == "restart":
        cli.restart_application()
        return

    if args.command == "run":
        if getattr(args, "run_command", None) == "table":
            port = getattr(args, "port", 8501)
            cli.run_table(port=port)
        else:
            print("Usage: BioAnalyzer run table   # Run curator table (Streamlit)")
        return

    if args.command == "status":
        cli.get_system_status()
        return

    if args.command == "fields":
        cli.show_fields_info()
        return

    if args.command == "qa":
        if args.interactive or not args.question:
            cli.interactive_qa()
        else:
            asyncio.run(cli.ask_question(args.question))
        return

    if args.command == "retrieve":
        pmids = []

        # Get PMIDs from different sources
        if args.pmids:
            # Handle comma-separated PMIDs
            for pmid in args.pmids:
                if "," in pmid:
                    pmids.extend([p.strip() for p in pmid.split(",") if p.strip()])
                else:
                    pmids.append(pmid)

        if args.file:
            try:
                file_pmids = cli.load_pmids_from_file(args.file)
                pmids.extend(file_pmids)
            except Exception as e:
                print(f"❌ Error reading file: {e}")
                return

        if not pmids:
            print("❌ Error: No PMIDs provided.")
            print("Usage: BioAnalyzer retrieve <pmid1> [pmid2] ...")
            print("   or: BioAnalyzer retrieve <pmid1,pmid2,pmid3>")
            print("   or: BioAnalyzer retrieve --file <file>")
            return

        # Remove duplicates while preserving order
        seen = set()
        unique_pmids = []
        for pmid in pmids:
            if pmid not in seen:
                seen.add(pmid)
                unique_pmids.append(pmid)

        asyncio.run(
            cli.retrieve_papers(unique_pmids, args.format, args.output, args.save)
        )
        return

    if args.command == "analyze-url":
        cli.handle_url_analysis(
            urls=args.urls,
            file_path=args.file,
            embedding_model=args.embedding_model,
            llm_model=args.llm_model,
            output_format=args.format,
            output_file=args.output,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
        return

    if args.command == "analyze":
        pmids = []

        # Get PMIDs from different sources
        if args.pmids:
            # Handle comma-separated PMIDs
            for pmid in args.pmids:
                if "," in pmid:
                    pmids.extend([p.strip() for p in pmid.split(",") if p.strip()])
                else:
                    pmids.append(pmid)

        if args.file:
            try:
                file_pmids = cli.load_pmids_from_file(args.file)
                if not file_pmids:
                    print(
                        f"❌ Error: File '{args.file}' is empty or contains no valid PMIDs."
                    )
                    print(
                        "   Please add PMIDs to the file (one per line or comma-separated)."
                    )
                    return
                pmids.extend(file_pmids)
                print(f"📁 Loaded {len(file_pmids)} PMID(s) from {args.file}")
            except FileNotFoundError:
                print(f"❌ Error: File '{args.file}' not found.")
                return
            except Exception as e:
                print(f"❌ Error reading file '{args.file}': {e}")
                return

        if not pmids:
            print("❌ Error: No PMIDs provided.")
            print("Usage: BioAnalyzer analyze <pmid1> [pmid2] ...")
            print("   or: BioAnalyzer analyze <pmid1,pmid2,pmid3>")
            print("   or: BioAnalyzer analyze --file <file>")
            return

        # Remove duplicates while preserving order
        seen = set()
        unique_pmids = []
        for pmid in pmids:
            if pmid not in seen:
                seen.add(pmid)
                unique_pmids.append(pmid)

        asyncio.run(cli.analyze_papers(unique_pmids, args.format, args.output))
        return

    if args.command == "settings":
        cli.handle_settings_command(args)
        return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
