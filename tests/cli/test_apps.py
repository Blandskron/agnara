"""E0A.2: ``agnara apps`` reads the manifest and imports nothing.

`docs/CLI_SPEC.md` specifies the command as listing apps, architecture and
exposures. These tests drive `main` so the exit codes, stderr and argument
wiring are covered as an operator meets them, not just the renderer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, main
from agnara_cli._manifest import MANIFEST_FILENAME

MANIFEST = """
[project]
name = "commerce"
python = ">=3.14"

[defaults]
architecture = "minimal"

[apps.users]
module = "commerce.apps.users"
path = "src/commerce/apps/users"
architecture = "modular-hexagonal"
exposures = ["http", "mcp"]

[apps.payments]
module = "commerce.apps.payments"
path = "src/commerce/apps/payments"
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / MANIFEST_FILENAME).write_text(MANIFEST, encoding="utf-8")
    return tmp_path


def run(*argv: str) -> int:
    return main(["apps", *argv])


def test_it_lists_every_app_with_architecture_and_exposures(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("--project", str(project)) == EXIT_OK

    output = capsys.readouterr().out
    assert "project commerce" in output
    assert "python >=3.14" in output
    assert "users" in output
    assert "modular-hexagonal" in output
    assert "exposures: http, mcp" in output
    # An app that declares no exposures says so rather than showing a blank.
    assert "exposures: none" in output
    assert "commerce.apps.payments" in output


def test_an_app_inherits_the_project_default_architecture(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run("--project", str(project))

    lines = capsys.readouterr().out.splitlines()
    payments = next(line for line in lines if line.startswith("payments"))
    assert "minimal" in payments


def test_json_output_is_deterministic_and_versioned(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("--project", str(project), "--json") == EXIT_OK

    first = capsys.readouterr().out
    document = json.loads(first)
    assert document["format_version"] == 1
    assert document["project"] == {
        "name": "commerce",
        "python": ">=3.14",
        "default_architecture": "minimal",
    }
    assert [app["name"] for app in document["apps"]] == ["users", "payments"]
    assert document["apps"][0]["exposures"] == ["http", "mcp"]
    assert document["apps"][1]["exposures"] == []

    run("--project", str(project), "--json")
    assert capsys.readouterr().out == first


def test_json_paths_use_forward_slashes_on_every_platform(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The manifest declares POSIX paths; the export must not localize them."""
    run("--project", str(project), "--json")

    document = json.loads(capsys.readouterr().out)
    assert document["apps"][0]["path"] == "src/commerce/apps/users"
    assert "\\" not in json.dumps(document)


def test_a_project_with_no_apps_says_so(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text("[project]\nname = 'commerce'\n", encoding="utf-8")

    assert run("--project", str(tmp_path)) == EXIT_OK
    assert "no apps declared" in capsys.readouterr().out


def test_the_manifest_is_found_in_a_parent_directory(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nested = project / "src" / "commerce"
    nested.mkdir(parents=True)

    assert run("--project", str(nested)) == EXIT_OK
    assert "project commerce" in capsys.readouterr().out


def test_a_missing_manifest_is_one_line_on_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert run("--project", str(empty)) == EXIT_FAILED

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("agnara: no agnara.toml found")
    assert len(captured.err.splitlines()) == 1


def test_an_invalid_manifest_is_reported_without_a_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(
        "[project]\nname = 'commerce'\n[apps.users]\nmodule = 'commerce.users'\n",
        encoding="utf-8",
    )

    assert run("--project", str(tmp_path)) == EXIT_FAILED

    error = capsys.readouterr().err
    assert "apps.users.path: is required" in error
    assert "Traceback" not in error


def test_a_project_argument_that_is_not_a_directory_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = tmp_path / "not-a-directory"
    file.write_text("", encoding="utf-8")

    assert run("--project", str(file)) == EXIT_FAILED
    assert "is not a directory" in capsys.readouterr().err


def test_it_reads_the_working_directory_by_default(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(project)

    assert run() == EXIT_OK
    assert "project commerce" in capsys.readouterr().out


def test_listing_apps_imports_no_project_module(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command answers from the manifest, so no project code runs."""
    before = set(sys.modules)

    run("--project", str(project))

    new = {name for name in set(sys.modules) - before if name.startswith("commerce")}
    assert not new
