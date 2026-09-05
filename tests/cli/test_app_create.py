"""E0A.3/E0A.4: what ``agnara app create`` generates, and what it refuses.

`docs/SCAFFOLDING.md` specifies the modular-hexagonal layout and says the
generator must not produce "dozens of meaningless empty files". So these tests
check that the generated app *works* — its capabilities register, compile and
invoke — not merely that the files exist.

The project is called ``ledger`` here so its package cannot collide with the
one `test_project_create.py` imports.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
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
from agnara_cli._manifest import MANIFEST_FILENAME, parse_manifest

APP_ROOT = "src/ledger/apps/billing"

#: The tree `docs/SCAFFOLDING.md` gives for a modular-hexagonal app.
EXPECTED_FILES = {
    f"{APP_ROOT}/__init__.py",
    f"{APP_ROOT}/module.py",
    f"{APP_ROOT}/domain/__init__.py",
    f"{APP_ROOT}/domain/models.py",
    f"{APP_ROOT}/domain/value_objects.py",
    f"{APP_ROOT}/domain/errors.py",
    f"{APP_ROOT}/application/__init__.py",
    f"{APP_ROOT}/application/capabilities.py",
    f"{APP_ROOT}/application/ports.py",
    f"{APP_ROOT}/adapters/__init__.py",
    f"{APP_ROOT}/adapters/inbound/__init__.py",
    f"{APP_ROOT}/adapters/outbound/__init__.py",
    f"{APP_ROOT}/adapters/outbound/memory.py",
    f"{APP_ROOT}/tests/__init__.py",
    f"{APP_ROOT}/tests/test_capabilities.py",
}

TRANSPORT_PACKAGES = ("agnara_http", "agnara_mcp", "agnara_a2a", "agnara_events", "fastapi")


def create_app(*argv: str) -> int:
    return main(["app", "create", *argv])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert main(["project", "create", "ledger", "--directory", str(tmp_path)]) == EXIT_OK
    return tmp_path / "ledger"


@pytest.fixture
def generated(project: Path) -> Path:
    assert create_app("billing", "--project", str(project)) == EXIT_OK
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
            if name == "ledger" or name.startswith("ledger."):
                del sys.modules[name]


def app_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix() for path in (root / APP_ROOT).rglob("*") if path.is_file()
    }


def source_of(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


def test_it_writes_the_modular_hexagonal_layout(generated: Path) -> None:
    assert app_files(generated) == EXPECTED_FILES


def test_generation_is_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    roots = []
    for directory in ("a", "b"):
        parent = tmp_path / directory
        parent.mkdir()
        main(["project", "create", "ledger", "--directory", str(parent)])
        create_app("billing", "--project", str(parent / "ledger"))
        roots.append(parent / "ledger")

    left = {name: source_of(roots[0], name) for name in EXPECTED_FILES}
    right = {name: source_of(roots[1], name) for name in EXPECTED_FILES}
    assert left == right


def test_the_app_name_reaches_the_package_and_the_error_class(generated: Path) -> None:
    assert "class BillingError(Exception):" in source_of(generated, f"{APP_ROOT}/domain/errors.py")


def test_a_multi_word_app_name_becomes_a_camel_case_error_class(project: Path) -> None:
    assert create_app("payment_methods", "--project", str(project)) == EXIT_OK

    errors = source_of(project, "src/ledger/apps/payment_methods/domain/errors.py")
    assert "class PaymentMethodsError(Exception):" in errors


# ---------------------------------------------------------------------------
# The generated app actually works
# ---------------------------------------------------------------------------


def test_every_generated_python_file_compiles(generated: Path) -> None:
    for relative in EXPECTED_FILES:
        path = generated / relative
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_the_generated_app_registers_compiles_and_invokes(importable: Path) -> None:
    """The whole point of the layering, exercised end to end."""
    module = importlib.import_module("ledger.apps.billing.module")
    app = Agnara("ledger")
    dependencies = DIRegistry()

    module.register(app, dependencies)
    capabilities = app.compile()

    assert {str(identifier) for identifier in capabilities} == {
        "ledger.get_record",
        "ledger.list_records",
    }

    plan = ExecutionPlan.compile(capabilities["ledger.get_record"], dependencies)
    # The port is runtime-owned: a caller supplies a reference, never a repository.
    assert set(plan.input_schemas) == {"reference"}
    assert "records" in plan.protected_parameters

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


def test_the_generated_app_tests_pass_when_executed(importable: Path) -> None:
    location = importable / APP_ROOT / "tests" / "test_capabilities.py"
    spec = importlib.util.spec_from_file_location("generated_app_tests", location)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

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


# ---------------------------------------------------------------------------
# The layering is real, not decorative
# ---------------------------------------------------------------------------


def test_no_generated_module_imports_a_transport(generated: Path) -> None:
    offenders = [
        f"{relative}: {package}"
        for relative in EXPECTED_FILES
        for package in TRANSPORT_PACKAGES
        if f"import {package}" in source_of(generated, relative)
    ]
    assert not offenders, offenders


@pytest.mark.parametrize(
    "relative",
    [
        f"{APP_ROOT}/domain/models.py",
        f"{APP_ROOT}/domain/value_objects.py",
        f"{APP_ROOT}/domain/errors.py",
        f"{APP_ROOT}/application/capabilities.py",
        f"{APP_ROOT}/application/ports.py",
    ],
)
def test_the_inner_layers_never_import_an_adapter(generated: Path, relative: str) -> None:
    """Dependencies point inward; the application knows its port, not its adapter."""
    assert ".adapters." not in source_of(generated, relative)


def test_the_domain_imports_nothing_from_the_application(generated: Path) -> None:
    for relative in EXPECTED_FILES:
        if "/domain/" not in relative:
            continue
        assert ".application." not in source_of(generated, relative), relative


def test_only_the_module_knows_both_the_application_and_its_adapters(
    generated: Path,
) -> None:
    """`module.py` is the app's composition boundary, and the only one.

    The app's own tests are excluded: wiring an adapter to the code under test
    is what testing the composition means, and forbidding it would only push
    the same import somewhere less honest.
    """
    knows_both = [
        relative
        for relative in sorted(EXPECTED_FILES)
        if "/tests/" not in relative
        and ".adapters." in source_of(generated, relative)
        and ".application." in source_of(generated, relative)
    ]
    assert knows_both == [f"{APP_ROOT}/module.py"]


# ---------------------------------------------------------------------------
# The manifest update
# ---------------------------------------------------------------------------


def test_the_app_is_declared_in_the_manifest(generated: Path) -> None:
    manifest = parse_manifest(source_of(generated, MANIFEST_FILENAME))

    assert [app.name for app in manifest.apps] == ["billing"]
    declared = manifest.apps[0]
    assert declared.module == "ledger.apps.billing"
    assert str(declared.path) == "src/ledger/apps/billing"
    assert declared.architecture == "modular-hexagonal"
    assert declared.exposures == ()


def test_the_manifest_update_preserves_comments_and_existing_content(
    generated: Path,
) -> None:
    """Re-serializing would delete what an operator wrote; appending does not."""
    text = source_of(generated, MANIFEST_FILENAME)

    assert text.startswith("# The project composition manifest.")
    assert 'name = "ledger"' in text
    assert "[defaults]" in text


def test_a_second_app_is_appended_without_disturbing_the_first(project: Path) -> None:
    create_app("billing", "--project", str(project))
    create_app("catalog", "--project", str(project))

    manifest = parse_manifest(source_of(project, MANIFEST_FILENAME))
    assert [app.name for app in manifest.apps] == ["billing", "catalog"]


def test_agnara_apps_lists_the_created_app(
    generated: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["apps", "--project", str(generated)]) == EXIT_OK

    output = capsys.readouterr().out
    assert "billing" in output
    assert "modular-hexagonal" in output
    assert "ledger.apps.billing" in output


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_a_dry_run_writes_nothing_and_leaves_the_manifest_alone(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = source_of(project, MANIFEST_FILENAME)

    assert create_app("billing", "--project", str(project), "--dry-run") == EXIT_OK

    assert not (project / APP_ROOT).exists()
    assert source_of(project, MANIFEST_FILENAME) == before
    output = capsys.readouterr().out
    assert "UPDATE" in output
    assert f"CREATE {project.name}/{APP_ROOT}/module.py" in output


def test_an_already_declared_app_is_refused(
    generated: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert create_app("billing", "--project", str(generated)) == EXIT_FAILED

    error = capsys.readouterr().err
    assert "already declared" in error


def test_an_existing_app_directory_is_still_a_conflict(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The manifest is an intended update; a stray app file is not."""
    stray = project / APP_ROOT / "module.py"
    stray.parent.mkdir(parents=True)
    stray.write_text("# mine\n", encoding="utf-8")

    assert create_app("billing", "--project", str(project)) == EXIT_FAILED

    assert stray.read_text(encoding="utf-8") == "# mine\n"
    assert "refusing to replace" in capsys.readouterr().err


def test_a_refused_run_does_not_update_the_manifest(project: Path) -> None:
    stray = project / APP_ROOT / "module.py"
    stray.parent.mkdir(parents=True)
    stray.write_text("# mine\n", encoding="utf-8")
    before = source_of(project, MANIFEST_FILENAME)

    create_app("billing", "--project", str(project))

    assert source_of(project, MANIFEST_FILENAME) == before


def test_a_missing_manifest_points_at_project_create(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert create_app("billing", "--project", str(empty)) == EXIT_FAILED
    assert "agnara project create" in capsys.readouterr().err


def test_an_invalid_manifest_is_refused_before_anything_is_written(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (project / MANIFEST_FILENAME).write_text("[project]\n", encoding="utf-8")

    assert create_app("billing", "--project", str(project)) == EXIT_FAILED

    assert not (project / APP_ROOT).exists()
    assert "project.name: is required" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["not-a-name", "1billing", "with space", "", "Billing"])
def test_an_unusable_app_name_is_refused(
    project: Path,
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert create_app(name, "--project", str(project)) == EXIT_FAILED
    assert "invalid app name" in capsys.readouterr().err


def test_the_command_never_prompts(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object) -> str:
        raise AssertionError("the generator must never read from stdin")

    monkeypatch.setattr("builtins.input", refuse)

    assert create_app("billing", "--project", str(project)) == EXIT_OK


# ---------------------------------------------------------------------------
# Machine-readable output
# ---------------------------------------------------------------------------


def test_json_marks_the_manifest_as_an_intended_update_not_a_conflict(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_app("billing", "--project", str(project), "--dry-run", "--json")

    document = json.loads(capsys.readouterr().out)
    manifest = next(entry for entry in document["files"] if entry["path"] == MANIFEST_FILENAME)
    assert manifest["action"] == "update"
    assert manifest["exists"] is True
    assert manifest["intended_update"] is True
    assert document["conflicts"] == []


def test_json_output_is_deterministic(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_app("billing", "--project", str(project), "--dry-run", "--json")
    first = capsys.readouterr().out

    create_app("billing", "--project", str(project), "--dry-run", "--json")
    assert capsys.readouterr().out == first
