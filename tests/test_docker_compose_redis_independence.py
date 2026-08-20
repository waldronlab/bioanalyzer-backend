"""Regression coverage for a real bug: docker-compose.yml gated the app
service's startup on `depends_on: redis: condition: service_healthy`, even
though the app has no Redis client anywhere in the codebase (rate limiting
is in-memory - see app/api/middleware/rate_limit.py - and the cache is
SQLite-backed - see app/services/cache_manager.py). If Redis failed its
healthcheck or never came up, Compose refused to even create the app
container, taking the whole service down with it. This was observed live:
see the comment on `test_main_exits_nonzero_when_lifecycle_command_fails` in
test_cli_health.py, which documents install.sh failing because "docker-
compose's redis service failed to bind its port" and blocked the app.

Two layers of protection:
  * test_no_service_depends_on_redis_health - a static, semantic check (not
    mere YAML-syntax validation) that neither compose file re-introduces a
    hard dependency on Redis for the app service. Always runs.
  * test_app_starts_and_becomes_healthy_when_redis_is_unhealthy - an actual
    live Docker Compose smoke test: it forces the redis service's
    healthcheck to always fail, brings the stack up, and asserts the app
    container still starts and reaches a healthy state anyway. Skipped when
    Docker/Compose or the prebuilt image aren't available, since the
    ordinary `pytest tests/` CI job (see CLAUDE.md) runs on a bare host
    without building the image.
"""

import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILES = ["docker-compose.yml", "docker-compose.prod.yml"]
IMAGE_NAME = "bioanalyzer-package:latest"


def _app_service(compose_data: dict) -> tuple[str, dict]:
    services = compose_data["services"]
    (key,) = [k for k in services if "bioanalyzer" in k.lower()]
    return key, services[key]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_no_service_depends_on_redis_health(compose_file):
    """The app service must not hard-gate startup on Redis being healthy."""
    with open(PROJECT_ROOT / compose_file) as fh:
        data = yaml.safe_load(fh)

    _, app_service = _app_service(data)
    depends_on = app_service.get("depends_on")

    if depends_on is None:
        return

    # depends_on may legitimately exist for other reasons in the future, as
    # long as it never re-imposes a health-gated wait on redis specifically.
    redis_dep = depends_on.get("redis") if isinstance(depends_on, dict) else None
    if isinstance(redis_dep, dict):
        assert redis_dep.get("condition") != "service_healthy", (
            f"{compose_file}: app service depends_on.redis.condition is "
            "service_healthy again - this blocks the app from starting "
            "whenever Redis is slow, misconfigured, or unavailable, even "
            "though nothing in the app actually uses Redis."
        )


def _docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=10)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return True


def _image_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", IMAGE_NAME],
            capture_output=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


@pytest.mark.integration
@pytest.mark.skipif(
    not _docker_compose_available(),
    reason="docker/docker compose not available in this environment",
)
@pytest.mark.skipif(
    not _image_available(),
    reason=f"{IMAGE_NAME} not built locally; build it before running this test",
)
def test_app_starts_and_becomes_healthy_when_redis_is_unhealthy(tmp_path):
    """Bring up only the app service - Redis is never started at all, i.e.
    fully "unavailable" - and confirm the app still reaches a healthy
    state. Targeting a single service with `up -d <service>` only pulls in
    services it `depends_on`; since the app no longer depends on redis,
    redis is never created for this project. Before the fix, the app
    service's `depends_on: redis: condition: service_healthy` meant Compose
    would refuse to even create the app container without redis present and
    healthy.
    """
    project = f"bioanalyzer_redis_regress_{uuid.uuid4().hex[:8]}"
    app_container = f"{project}-app"
    host_port = 18000 + (uuid.uuid4().int % 500)

    override = {
        "services": {
            "bioanalyzer-package": {
                "container_name": app_container,
                "ports": [f"{host_port}:8000"],
            },
        }
    }
    override_file = tmp_path / "docker-compose.app-only.override.yml"
    override_file.write_text(yaml.safe_dump(override))

    compose_cmd = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(PROJECT_ROOT / "docker-compose.yml"),
        "-f",
        str(override_file),
    ]

    def _cleanup():
        subprocess.run(
            compose_cmd + ["down", "--volumes", "--remove-orphans"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=60,
        )

    _cleanup()
    try:
        up = subprocess.run(
            compose_cmd + ["up", "-d", "--no-build", "bioanalyzer-package"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert up.returncode == 0, (
            "docker compose up failed even though the app service no "
            f"longer depends on redis health:\n{up.stdout}\n{up.stderr}"
        )

        redis_ps = subprocess.run(
            compose_cmd + ["ps", "-a", "--format", "{{.Service}}", "redis"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        assert redis_ps.stdout.strip() == "", (
            "test setup bug: redis got created for this project, so this "
            "run didn't actually exercise 'Redis is unavailable'"
            f" (compose ps: {redis_ps.stdout!r})"
        )

        def _health_status(container: str) -> str:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    container,
                ],
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        deadline = time.time() + 90
        app_status = ""
        while time.time() < deadline:
            app_status = _health_status(app_container)
            if app_status == "healthy":
                break
            time.sleep(2)

        assert app_status == "healthy", (
            "app container did not reach a healthy state while redis was "
            f"never started (last status: {app_status!r}). If this fails, "
            "the app is once again being blocked by Redis at startup."
        )
    finally:
        _cleanup()
