"""E0A.5: the ``minimal`` architecture, and how one is selected.

`docs/SCAFFOLDING.md` fixes the layout and `docs/CLI_SPEC.md` describes the
architecture as being "for very small capabilities, experiments and examples".
As with the default template, these tests check that the generated app *works*
rather than that the files exist.

They also pin the property that made `--architecture` necessary: the manifest
entry must describe the layout that was actually written. Before E0A.5,
``agnara app create`` recorded the project's declared default while always
generating the modular-hexagonal tree, so a project defaulting to ``minimal``
produced a manifest that disagreed with its own directory.

The project is called ``depot`` here so its package cannot collide with the
ones the sibling CLI test modules import.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agnara import Agnara
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
    invoke_result,
)
from agnara_cli import EXIT_FAILED, EXIT_OK, main
from agnara_cli._manifest import MANIFEST_FILENAME, load_manifest

APP_ROOT = "src/depot/apps/health"

#: The tree `docs/SCAFFOLDING.md` gives under "Minimal architecture".
EXPECTED_FILES = {
    f"{APP_ROOT}/__init__.py",
    f"{APP_ROOT}/module.py",
    f"{APP_ROOT}/capabilities.py",
    f"{APP_ROOT}/tests/__init__.py",
    f"{APP_ROOT}/tests/test_capabilities.py",
}

#: Directories the modular-hexagonal template creates and this one must not.
HEXAGONAL_ONLY = ("domain", "application", "adapters")

TRANSPORT_PACKAGES = ("agnara_http", "agnara_mcp", "agnara_a2a", "agnara_events", "fastapi")


def create_app(*argv: str) -> int:
    return main(["app", "create", *argv])


def set_default_architecture(project: Path, architecture: str) -> None:
    manifest = project / MANIFEST_FILENAME
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace('architecture = "modular-hexagonal"', f'architecture = "{architecture}"'),
        encoding="utf-8",
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert main(["project", "create", "depot", "--directory", str(tmp_path)]) == EXIT_OK
    return tmp_path / "depot"


@pytest.fixture
def generated(project: Path) -> Path:
    assert create_app("health", "--project", str(project), "--architecture", "minimal") == EXIT_OK
    return project


@pytest.fixture
def importable(generated: Path) -> Iterator[Path]:
    source = str(generated / "src")
    sys.path.insert(0, source)
    try:
        yield generated
    finally:
        sys.path.remove(source)
        for name in list(sys.modules):
            if name == "depot" or name.startswith("depot."):
                del sys.modules[name]


def app_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix() for path in (root / APP_ROOT).rglob("*") if path.is_file()
    }


def source_of(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def declared_architecture(root: Path, app: str) -> str:
    manifest = load_manifest(root / MANIFEST_FILENAME)
    return next(entry.architecture for entry in manifest.apps if entry.name == app)


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


def test_it_writes_the_minimal_layout(generated: Path) -> None:
    assert app_files(generated) == EXPECTED_FILES


def test_it_writes_none_of_the_hexagonal_packages(generated: Path) -> None:
    """The point of the escape hatch is the layers it does not create."""
    present = [name for name in HEXAGONAL_ONLY if (generated / APP_ROOT / name).exists()]
    assert not present, present


def test_generation_is_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    roots = []
    for directory in ("a", "b"):
        parent = tmp_path / directory
        parent.mkdir()
        main(["project", "create", "depot", "--directory", str(parent)])
        create_app("health", "--project", str(parent / "depot"), "--architecture", "minimal")
        roots.append(parent / "depot")

    left = {name: source_of(roots[0], name) for name in EXPECTED_FILES}
    right = {name: source_of(roots[1], name) for name in EXPECTED_FILES}
    assert left == right


def test_the_app_name_reaches_the_generated_documentation(generated: Path) -> None:
    assert "the health app" in source_of(generated, f"{APP_ROOT}/capabilities.py")


# ---------------------------------------------------------------------------
# The generated app actually works
# ---------------------------------------------------------------------------


def test_every_generated_python_file_compiles(generated: Path) -> None:
    for relative in EXPECTED_FILES:
        path = generated / relative
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_the_generated_app_registers_compiles_and_invokes(importable: Path) -> None:
    module = importlib.import_module("depot.apps.health.module")
    app = Agnara("depot")
    dependencies = DIRegistry()

    module.register(app, dependencies)
    capabilities = app.compile()

    assert {str(identifier) for identifier in capabilities} == {
        "health.get_record",
        "health.list_records",
    }

    plan = ExecutionPlan.compile(capabilities["health.get_record"], dependencies)
    assert set(plan.input_schemas) == {"reference"}
    # Unlike the hexagonal template, nothing here is runtime-owned: a minimal
    # app declares no ports, so it has no protected parameters at all.
    assert not plan.protected_parameters

    outcome = asyncio.run(
        invoke_result(
            plan,
            ExecutionContext(
                Invocation(
                    capability_id=plan.definition.id,
                    payload={"reference": "example-1"},
                    metadata={},
                ),
                DIContainer(dependencies),
            ),
        )
    )

    assert isinstance(outcome, Success)
    assert outcome.value == {"reference": "example-1", "label": "first example record"}


def test_registering_needs_no_provider(importable: Path) -> None:
    """An empty registry is enough, which is what makes this template minimal.

    The hexagonal template binds ``RecordRepository`` in ``register``; this one
    binds nothing, so every capability must still compile against a registry
    that was never touched.
    """
    module = importlib.import_module("depot.apps.health.module")
    app = Agnara("depot")
    dependencies = DIRegistry()

    module.register(app, dependencies)
    capabilities = app.compile()

    for definition in capabilities.values():
        plan = ExecutionPlan.compile(definition, dependencies)
        assert not plan.protected_parameters


def test_the_generated_app_tests_pass_when_executed(importable: Path) -> None:
    module = importlib.import_module("depot.apps.health.tests.test_capabilities")

    cases = [name for name in dir(module) if name.startswith("test_")]
    assert len(cases) >= 4
    for name in cases:
        getattr(module, name)()


@pytest.mark.parametrize("command", [("check",), ("format", "--check")])
def test_the_generated_app_passes_ruff(generated: Path, command: tuple[str, ...]) -> None:
    """Under the generated project's own Ruff configuration, not this one's."""
    try:
        from ruff.__main__ import find_ruff_bin
    except ImportError:  # pragma: no cover - ruff is a development pin
        pytest.skip("ruff is not installed")

    completed = subprocess.run(
        [str(find_ruff_bin()), *command, "."],
        cwd=generated,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_no_generated_module_imports_a_transport(generated: Path) -> None:
    offenders = [
        f"{relative}: {package}"
        for relative in EXPECTED_FILES
        for package in TRANSPORT_PACKAGES
        if f"import {package}" in source_of(generated, relative)
    ]
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# Selecting an architecture
# ---------------------------------------------------------------------------


def test_the_manifest_records_the_architecture_that_was_generated(generated: Path) -> None:
    assert declared_architecture(generated, "health") == "minimal"


def test_the_default_architecture_still_generates_the_hexagonal_tree(project: Path) -> None:
    assert create_app("billing", "--project", str(project)) == EXIT_OK

    assert declared_architecture(project, "billing") == "modular-hexagonal"
    assert (project / "src/depot/apps/billing/domain/models.py").is_file()


def test_the_project_default_selects_the_template_when_no_flag_is_given(project: Path) -> None:
    """The regression E0A.5 closes: declared and generated must agree.

    Before this, the manifest recorded the project default while the generator
    always wrote the hexagonal tree, so `agnara apps` reported an architecture
    the directory contradicted.
    """
    set_default_architecture(project, "minimal")

    assert create_app("billing", "--project", str(project)) == EXIT_OK

    assert declared_architecture(project, "billing") == "minimal"
    assert not (project / "src/depot/apps/billing/domain").exists()
    assert (project / "src/depot/apps/billing/capabilities.py").is_file()


def test_an_explicit_architecture_overrides_the_project_default(project: Path) -> None:
    set_default_architecture(project, "minimal")

    assert (
        create_app("billing", "--project", str(project), "--architecture", "modular-hexagonal")
        == EXIT_OK
    )

    assert declared_architecture(project, "billing") == "modular-hexagonal"
    assert (project / "src/depot/apps/billing/domain/models.py").is_file()


# ---------------------------------------------------------------------------
# Architectures that have no generator
# ---------------------------------------------------------------------------


def test_a_reserved_architecture_is_refused_rather_than_substituted(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`vertical` is manifest vocabulary with no template behind it."""
    assert create_app("billing", "--project", str(project), "--architecture", "vertical") == (
        EXIT_FAILED
    )

    message = capsys.readouterr().err
    assert "vertical" in message
    assert "no generator yet" in message
    assert not (project / "src/depot/apps/billing").exists()


def test_a_reserved_project_default_names_the_flag_that_resolves_it(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    set_default_architecture(project, "vertical")

    assert create_app("billing", "--project", str(project)) == EXIT_FAILED

    message = capsys.readouterr().err
    assert "--architecture" in message
    assert "minimal, modular-hexagonal" in message


def test_a_reserved_default_can_still_be_overridden_explicitly(project: Path) -> None:
    """A project default nobody has implemented must not block every app."""
    set_default_architecture(project, "vertical")

    assert create_app("billing", "--project", str(project), "--architecture", "minimal") == EXIT_OK
    assert declared_architecture(project, "billing") == "minimal"


def test_an_unknown_architecture_is_a_usage_error(project: Path) -> None:
    """Outside the manifest vocabulary entirely, argparse rejects the value."""
    with pytest.raises(SystemExit) as raised:
        create_app("billing", "--project", str(project), "--architecture", "hexagonal")
    assert raised.value.code == 2


# ---------------------------------------------------------------------------
# Planning behaviour is shared, so prove it holds for this template too
# ---------------------------------------------------------------------------


def test_a_dry_run_writes_nothing_and_leaves_the_manifest_alone(project: Path) -> None:
    before = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")

    assert (
        create_app("health", "--project", str(project), "--architecture", "minimal", "--dry-run")
        == EXIT_OK
    )

    assert not (project / APP_ROOT).exists()
    assert (project / MANIFEST_FILENAME).read_text(encoding="utf-8") == before


def test_json_lists_every_minimal_file_and_is_deterministic(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ("health", "--project", str(project), "--architecture", "minimal")

    assert create_app(*arguments, "--dry-run", "--json") == EXIT_OK
    first = capsys.readouterr().out
    assert create_app(*arguments, "--dry-run", "--json") == EXIT_OK
    second = capsys.readouterr().out

    assert first == second
    paths = {entry["path"] for entry in json.loads(first)["files"]}
    assert EXPECTED_FILES.issubset(paths)
