"""Run the V1-42 reference consumers from installed wheels, never the checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from tests.architecture.boundaries import WORKSPACE_ROOT

REFERENCE_APPS = WORKSPACE_ROOT / "tests" / "reference_apps"
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
            "mcp==2.1.1",
            "opentelemetry-api>=1.44,<2",
            "opentelemetry-sdk==1.44.0",
            "fastapi==0.141.1",
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
    ):
        completed = subprocess.run(
            [str(python), "-I", str(consumers / script)],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"{script} failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
        assert marker in completed.stdout
