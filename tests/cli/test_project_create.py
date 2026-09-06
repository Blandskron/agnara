"""E0A.1: what ``agnara project create`` writes, and what it refuses to write.

The BACKLOG acceptance for EPIC 0A is that generated code imports on Python
3.14, passes the linters, contains no transport dependency in domain or
application layers, is deterministic for identical inputs, and refuses
overwrite without explicit authorization. These tests assert each of those
against a really generated project rather than against the templates.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agnara import Agnara
from agnara_cli import EXIT_FAILED, EXIT_OK, main
from agnara_cli._manifest import parse_manifest
from agnara_cli._templates import project_files

#: The tree `docs/CLI_SPEC.md` specifies, plus the files that make it work.
EXPECTED_FILES = {
    "AGENTS.md",
    "README.md",
    "agnara.toml",
    "pyproject.toml",
    "src/commerce/__init__.py",
    "src/commerce/apps/__init__.py",
    "src/commerce/bootstrap.py",
    "src/commerce/settings.py",
    "tests/__init__.py",
    "tests/test_bootstrap.py",
}

#: Packages a generated project's own code must never import. An app decides
#: its transports; a generator does not decide them for it.
TRANSPORT_PACKAGES = ("agnara_http", "agnara_mcp", "agnara_a2a", "agnara_events", "fastapi")


def create(*argv: str) -> int:
    return main(["project", "create", *argv])


@pytest.fixture
def generated(tmp_path: Path) -> Path:
    assert create("commerce", "--directory", str(tmp_path)) == EXIT_OK
    return tmp_path / "commerce"


@pytest.fixture
def importable(generated: Path) -> Iterator[Path]:
    """Put the generated project on the path, and take it off again."""
    source = str(generated / "src")
    sys.path.insert(0, source)
    before = set(sys.modules)
    try:
        yield generated
    finally:
        sys.path.remove(source)
        for name in set(sys.modules) - before:
            if name == "commerce" or name.startswith("commerce."):
                del sys.modules[name]


def written(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


def test_it_writes_exactly_the_specified_tree(generated: Path) -> None:
    assert written(generated) == EXPECTED_FILES


def test_generation_is_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    """A generated project is reviewed in a diff; the diff must not drift."""
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()

    create("commerce", "--directory", str(first))
    create("commerce", "--directory", str(second))

    left = {name: (first / "commerce" / name).read_bytes() for name in EXPECTED_FILES}
    right = {name: (second / "commerce" / name).read_bytes() for name in EXPECTED_FILES}
    assert left == right


def test_every_written_file_uses_newline_endings(generated: Path) -> None:
    """A project is shared; its line endings are not the generating machine's."""
    for relative in EXPECTED_FILES:
        assert b"\r\n" not in (generated / relative).read_bytes(), relative


def test_the_project_name_reaches_the_package_the_manifest_and_the_docs(
    generated: Path,
) -> None:
    assert (generated / "src" / "commerce").is_dir()
    assert 'name = "commerce"' in (generated / "agnara.toml").read_text(encoding="utf-8")
    assert "# commerce" in (generated / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The generated project actually works
# ---------------------------------------------------------------------------


def test_every_generated_python_file_compiles(generated: Path) -> None:
    for path in generated.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_the_generated_composition_builds_a_named_application(importable: Path) -> None:
    bootstrap = importlib.import_module("commerce.bootstrap")

    assert isinstance(bootstrap.app, Agnara)
    assert bootstrap.app.name == "commerce"
    assert bootstrap.dependencies is not None


def test_the_generated_registry_compiles_and_freezes(importable: Path) -> None:
    """Startup compilation is the property the generated test also checks."""
    bootstrap = importlib.import_module("commerce.bootstrap")

    bootstrap.app.compile()

    assert bootstrap.app.is_compiled


def test_the_generated_tests_pass_when_executed(importable: Path) -> None:
    """Run the project's own test module rather than trusting the template.

    Loaded by path under a private name: the generated package is also called
    ``tests``, and importing it normally would resolve to this repository's
    own test package instead.
    """
    location = importable / "tests" / "test_bootstrap.py"
    spec = importlib.util.spec_from_file_location("generated_project_tests", location)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cases = [name for name in dir(module) if name.startswith("test_")]
    assert cases, "the generated project must ship at least one test"
    for name in cases:
        getattr(module, name)()


def _linter(name: str) -> str | None:
    """Locate a linter binary next to the interpreter running these tests."""
    if name == "ruff":
        try:
            from ruff.__main__ import find_ruff_bin
        except ImportError:  # pragma: no cover - ruff is a development pin
            return None
        return str(find_ruff_bin())
    return shutil.which(name)


@pytest.mark.parametrize("command", [("check",), ("format", "--check")])
def test_the_generated_project_passes_ruff(generated: Path, command: tuple[str, ...]) -> None:
    """BACKLOG EPIC 0A acceptance: generated code passes Ruff.

    Run with the real linter rather than asserted about, because a template
    that stops being clean is exactly the regression this criterion exists to
    catch. The generated project brings its own Ruff configuration, so this
    checks it under the rules it ships with, not under this repository's.
    """
    ruff = _linter("ruff")
    if ruff is None:  # pragma: no cover - only without the development pin
        pytest.skip("ruff is not installed")

    completed = subprocess.run(
        [ruff, *command, "."],
        cwd=generated,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_the_generated_manifest_is_accepted_by_the_manifest_reader(
    generated: Path,
) -> None:
    """The generator and E0A.2's validator agree by construction, not luck."""
    manifest = parse_manifest((generated / "agnara.toml").read_text(encoding="utf-8"))

    assert manifest.name == "commerce"
    assert manifest.python == ">=3.14"
    assert manifest.default_architecture == "modular-hexagonal"
    assert manifest.apps == ()


def test_agnara_apps_reads_the_generated_project(
    generated: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["apps", "--project", str(generated)]) == EXIT_OK

    output = capsys.readouterr().out
    assert "project commerce" in output
    assert "no apps declared" in output


def test_agnara_inspect_reads_the_generated_composition_root(
    generated: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The bootstrap convention is real: the tooling can find `app`."""
    exit_code = main(
        [
            "inspect",
            "commerce.bootstrap:app",
            "--path",
            str(generated / "src"),
            "--dependencies",
            "dependencies",
        ]
    )

    assert exit_code == EXIT_OK
    assert "agnara-introspection" in capsys.readouterr().out


def test_no_generated_module_imports_a_transport_package(generated: Path) -> None:
    """AGENTS.md: generated domain and application code stays protocol-free."""
    offenders = []
    for path in generated.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for package in TRANSPORT_PACKAGES:
            if f"import {package}" in source or f"from {package}" in source:
                offenders.append(f"{path.name}: {package}")
    assert not offenders, offenders


def test_the_generated_project_declares_only_agnara_as_a_dependency(
    generated: Path,
) -> None:
    pyproject = (generated / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dependencies = ["agnara"]' in pyproject
    assert 'requires-python = ">=3.14"' in pyproject


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_a_dry_run_writes_nothing_at_all(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not even the project directory: a preview must leave no trace."""
    assert create("commerce", "--directory", str(tmp_path), "--dry-run") == EXIT_OK

    assert list(tmp_path.iterdir()) == []
    output = capsys.readouterr().out
    assert "CREATE commerce/agnara.toml" in output


def test_a_dry_run_lists_the_same_files_the_real_run_writes(tmp_path: Path) -> None:
    """One plan drives both, so a preview cannot disagree with the result."""
    plan = tmp_path / "plan"
    real = tmp_path / "real"
    plan.mkdir()
    real.mkdir()

    create("commerce", "--directory", str(plan), "--dry-run", "--json")
    create("commerce", "--directory", str(real), "--json")

    assert set(project_files("commerce")) == written(real / "commerce")


def test_an_existing_file_is_never_replaced_without_authorization(
    generated: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    edited = generated / "src" / "commerce" / "bootstrap.py"
    edited.write_text("# my own composition\n", encoding="utf-8")

    assert create("commerce", "--directory", str(tmp_path)) == EXIT_FAILED

    # The edit survives, and so does everything else.
    assert edited.read_text(encoding="utf-8") == "# my own composition\n"
    error = capsys.readouterr().err
    assert "refusing to replace" in error
    assert "src/commerce/bootstrap.py" in error
    assert "--overwrite" in error


def test_a_refused_run_writes_no_file_at_all(
    generated: Path,
    tmp_path: Path,
) -> None:
    """The refusal precedes the first write, so nothing is half-applied."""
    (generated / "README.md").write_text("mine\n", encoding="utf-8")
    (generated / "src" / "commerce" / "settings.py").unlink()

    create("commerce", "--directory", str(tmp_path))

    assert (generated / "README.md").read_text(encoding="utf-8") == "mine\n"
    assert not (generated / "src" / "commerce" / "settings.py").exists()


def test_overwrite_replaces_the_files_it_was_authorized_to_replace(
    generated: Path,
    tmp_path: Path,
) -> None:
    edited = generated / "README.md"
    edited.write_text("mine\n", encoding="utf-8")

    assert create("commerce", "--directory", str(tmp_path), "--overwrite") == EXIT_OK
    assert edited.read_text(encoding="utf-8").startswith("# commerce")


@pytest.mark.parametrize("name", ["not-a-name", "1commerce", "with space", "", "Commerce"])
def test_an_unusable_project_name_is_refused_before_anything_is_created(
    name: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert create(name, "--directory", str(tmp_path)) == EXIT_FAILED

    assert list(tmp_path.iterdir()) == []
    assert "invalid project name" in capsys.readouterr().err


def test_a_directory_argument_that_is_not_a_directory_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = tmp_path / "not-a-directory"
    file.write_text("", encoding="utf-8")

    assert create("commerce", "--directory", str(file)) == EXIT_FAILED
    assert "is not a directory" in capsys.readouterr().err


def test_a_target_that_exists_as_a_file_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "commerce").write_text("", encoding="utf-8")

    assert create("commerce", "--directory", str(tmp_path)) == EXIT_FAILED
    assert "exists and is not a directory" in capsys.readouterr().err


def test_the_command_never_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generators must run in CI and for agents; a prompt would hang both."""

    def refuse(*_: object) -> str:
        raise AssertionError("the generator must never read from stdin")

    monkeypatch.setattr("builtins.input", refuse)

    assert create("commerce", "--directory", str(tmp_path)) == EXIT_OK


# ---------------------------------------------------------------------------
# Machine-readable output
# ---------------------------------------------------------------------------


def test_json_output_is_deterministic_and_versioned(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create("commerce", "--directory", str(tmp_path), "--dry-run", "--json")
    first = capsys.readouterr().out

    create("commerce", "--directory", str(tmp_path), "--dry-run", "--json")
    assert capsys.readouterr().out == first

    document = json.loads(first)
    assert document["format_version"] == 1
    assert {entry["path"] for entry in document["files"]} == EXPECTED_FILES
    assert all(entry["action"] == "create" for entry in document["files"])
    assert document["conflicts"] == []


def test_json_reports_conflicts_before_they_are_written(
    generated: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create("commerce", "--directory", str(tmp_path), "--dry-run", "--json")

    document = json.loads(capsys.readouterr().out)
    assert set(document["conflicts"]) == EXPECTED_FILES
    assert all(entry["action"] == "update" for entry in document["files"])


def test_json_paths_are_posix_on_every_platform(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create("commerce", "--directory", str(tmp_path), "--dry-run", "--json")

    document = json.loads(capsys.readouterr().out)
    paths = [entry["path"] for entry in document["files"]]
    assert all("\\" not in path for path in paths)
    assert "src/commerce/bootstrap.py" in paths
