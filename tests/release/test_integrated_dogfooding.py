"""Run the V1-42 reference consumers from installed wheels, never the checkout."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from tests.architecture.boundaries import WORKSPACE_ROOT

REFERENCE_APPS = WORKSPACE_ROOT / "tests" / "reference_apps"
HOST_GUIDES = ("starlette_embedding.py", "litestar_embedding.py", "django_embedding.py")
ADDITIONAL_GUIDES = ("fastapi_embedding.py", "sqlite_persistence.py")
STRUCTURED_GUIDES = (
    ("direct_streaming.py", "direct_streaming_guide.py", "DIRECT_STREAMING_GUIDE_ARTIFACT_OK"),
    ("mcp_tools.py", "mcp_guide.py", "MCP_GUIDE_ARTIFACT_OK"),
    ("http_sse.py", "sse_guide.py", "SSE_GUIDE_ARTIFACT_OK"),
    ("schema_contracts.py", "schema_guide.py", "SCHEMA_GUIDE_ARTIFACT_OK"),
    ("dependencies.py", "dependencies_guide.py", "DEPENDENCIES_GUIDE_ARTIFACT_OK"),
    ("invocation_telemetry.py", "telemetry_guide.py", "TELEMETRY_GUIDE_ARTIFACT_OK"),
    ("deadlines.py", "deadlines_guide.py", "DEADLINES_GUIDE_ARTIFACT_OK"),
    ("confirmation.py", "confirmation_guide.py", "CONFIRMATION_GUIDE_ARTIFACT_OK"),
    ("introspection.py", "introspection_guide.py", "INTROSPECTION_GUIDE_ARTIFACT_OK"),
    ("nested_invocation.py", "nested_invocation_guide.py", "NESTED_INVOCATION_GUIDE_ARTIFACT_OK"),
    (
        "direct_idempotency.py",
        "direct_idempotency_guide.py",
        "DIRECT_IDEMPOTENCY_GUIDE_ARTIFACT_OK",
    ),
)
UV = shutil.which("uv")
CANDIDATE_VERSION = tomllib.loads(
    (WORKSPACE_ROOT / "packages" / "agnara" / "pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"]


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"command failed: {command}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def assert_host_guide_output(stdout: str) -> None:
    """Prove results/effects/cleanup, rather than accepting exit zero or status text."""
    cases = {
        "success": (200, {"order_id": 7}),
        "policy denial": (403, {"error": "forbidden"}),
        "unknown credential": (401, {"error": "unauthenticated"}),
        "missing credential": (401, {"error": "unauthenticated"}),
        "malformed JSON": (400, {"error": "malformed_json"}),
        "invalid input": (422, {"error": "invalid_input"}),
        "native health": (200, {"status": "ok"}),
    }
    observations: dict[str, str] = {}
    for line in stdout.splitlines():
        label, separator, value = line.partition(": ")
        assert separator and label not in observations, f"invalid/duplicate case: {line!r}"
        observations[label] = value
    assert set(observations) == cases.keys() | {"recorded orders", "cleanup"}
    for label, expected in cases.items():
        status, separator, body = observations[label].partition(" ")
        assert separator, f"missing response body for {label}"
        assert (int(status), json.loads(body)) == expected, label
    assert json.loads(observations["recorded orders"]) == [7]
    assert observations["cleanup"] == "['audit.close', 'runtime.close']"


def assert_fastapi_guide_output(stdout: str) -> None:
    """Check wire outcomes and bounded correlation, not unobserved cleanup."""
    observations: dict[str, str] = {}
    for line in stdout.splitlines():
        label, separator, value = line.partition(" -> ")
        if not separator:
            continue  # The example ends with explanatory prose.
        label = label.strip()
        assert label not in observations, f"duplicate case: {label}"
        observations[label] = value
    cases = {
        "authorized, scoped": (200, {"order": "A-1", "status": "shipped"}),
        "authenticated, missing scope": (403, {"error": "forbidden"}),
        "unknown credential": (401, {"detail": "unauthenticated"}),
        "no credential": (401, {"detail": "unauthenticated"}),
        "plain FastAPI route": (200, {"status": "ok"}),
    }
    correlation = {
        "correlation accepted": "req-7f3a9c",
        "correlation dropped (long)": None,
        "correlation dropped (token)": None,
    }
    assert set(observations) == cases.keys() | correlation.keys()
    for label, expected in cases.items():
        status, separator, body = observations[label].partition(" ")
        assert separator, f"missing response body for {label}"
        assert (int(status), json.loads(body)) == expected, label
    for label, expected_correlation in correlation.items():
        assert ast.literal_eval(observations[label]) == expected_correlation, label


def assert_sqlite_guide_output(stdout: str) -> None:
    """Check durable rows, refusals, rollback and the complete ownership trace."""
    observations: dict[str, str] = {}
    for line in stdout.splitlines():
        label, separator, value = line.partition(": ")
        assert separator and label not in observations, f"invalid/duplicate case: {line!r}"
        observations[label] = value
    outcomes = {
        "success": "committed",
        "denied": "forbidden",
        "invalid": "invalid_input",
        "failed": "internal_failure",
        "cancelled": "CancelledError",
    }
    assert set(observations) == outcomes.keys() | {"persisted", "events"}
    for label, expected in outcomes.items():
        assert observations[label] == expected, label
    assert ast.literal_eval(observations["persisted"]) == ("committed",)
    assert ast.literal_eval(observations["events"]) == [
        "session.open",
        "port.open",
        "write:committed",
        "port.close",
        "host.commit",
        "host.rollback",  # Denial does not acquire a port.
        "host.rollback",  # Invalid input does not acquire a port.
        "port.open",
        "write:rolled-back",
        "port.close",
        "host.rollback",
        "port.open",
        "write:cancelled",
        "port.close",
        "host.rollback",
        "runtime.close",
        "session.close",
        "engine.dispose",
    ]


def test_reference_apps_run_from_fresh_installed_artifacts(tmp_path: Path) -> None:
    """A release consumer gets only wheels, public imports and pinned host fixtures."""
    assert UV is not None, "the release gate requires uv to build and install the candidate wheels"
    dist = tmp_path / "dist"
    environment_dir = tmp_path / "consumer-environment"
    consumers = tmp_path / "consumers"
    cache = tmp_path / "uv-cache"
    env = {**os.environ, "UV_CACHE_DIR": str(cache)}

    _run(
        [UV, "build", "--all-packages", "--wheel", "--out-dir", str(dist)],
        cwd=WORKSPACE_ROOT,
        environment=env,
    )
    _run([UV, "venv", "--python", "3.14", str(environment_dir)], cwd=tmp_path, environment=env)
    python = _python(environment_dir)
    _run(
        [
            UV,
            "pip",
            "install",
            "--python",
            str(python),
            "mcp==2.2.0",
            "opentelemetry-api>=1.44,<2",
            "opentelemetry-sdk==1.44.0",
            "fastapi==0.141.1",
            "starlette==1.6.0",
            "litestar==2.24.0",
            "Django==6.1.1",
            "SQLAlchemy==2.0.54",
        ],
        cwd=tmp_path,
        environment=env,
    )
    wheels = sorted(str(wheel) for wheel in dist.glob("*.whl"))
    assert len(wheels) == 7
    _run(
        [
            UV,
            "pip",
            "install",
            "--python",
            str(python),
            "--no-index",
            "--find-links",
            str(dist),
            *wheels,
        ],
        cwd=tmp_path,
        environment=env,
    )

    shutil.copytree(REFERENCE_APPS, consumers)
    for guide in (*HOST_GUIDES, *ADDITIONAL_GUIDES):
        shutil.copy2(WORKSPACE_ROOT / "examples" / guide, consumers / guide)
    for guide, _, _ in STRUCTURED_GUIDES:
        shutil.copy2(WORKSPACE_ROOT / "examples" / guide, consumers / guide)
    _run(
        [
            str(python),
            "-I",
            str(WORKSPACE_ROOT / "scripts" / "check_public_imports.py"),
            str(consumers),
        ],
        cwd=tmp_path,
        environment=env,
    )
    _run(
        [
            str(python),
            "-I",
            str(WORKSPACE_ROOT / "scripts" / "check_distributions.py"),
            "--workspace",
            str(WORKSPACE_ROOT),
            "--require-installed",
            "--expected-version",
            CANDIDATE_VERSION,
        ],
        cwd=tmp_path,
        environment=env,
    )
    for script, marker in (
        ("standalone.py", "STANDALONE_DOGFOOD_OK"),
        ("host_sqlite.py", "HOST_DOGFOOD_OK"),
        ("embedded_fastapi.py", "EMBEDDED_DOGFOOD_OK"),
        ("side_by_side_fastapi.py", "SIDE_BY_SIDE_DOGFOOD_OK"),
        ("nested_resource_lifecycle.py", "NESTED_RESOURCE_LIFECYCLE_ARTIFACT_OK"),
    ):
        completed = subprocess.run(
            [str(python), "-I", str(consumers / script)],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        assert completed.returncode == 0, (
            f"{script} failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
        assert marker in completed.stdout

    for guide, consumer, marker in STRUCTURED_GUIDES:
        completed = subprocess.run(
            [str(python), "-I", str(consumers / consumer), str(consumers / guide)],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, (
            f"{guide} failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
        assert completed.stdout.splitlines() == [marker]

    validators = {
        **dict.fromkeys(HOST_GUIDES, assert_host_guide_output),
        "fastapi_embedding.py": assert_fastapi_guide_output,
        "sqlite_persistence.py": assert_sqlite_guide_output,
    }
    for guide, validate in validators.items():
        completed = subprocess.run(
            [str(python), "-I", str(consumers / guide)],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, (
            f"{guide} failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
        validate(completed.stdout)
