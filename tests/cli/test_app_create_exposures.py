"""E0A.6: ``--with`` selects which inbound adapters are scaffolded.

`docs/SCAFFOLDING.md` fixes the contract: ``adapters/inbound/`` starts as a
documented, empty package, and "only the requested inbound adapters are
added". `docs/CLI_SPEC.md` lines 107-110 give the surface.

Two properties matter more than the file list.

The first is that the manifest describes the app. ``exposures`` was written as
``[]`` regardless of what was asked for, the same declared-versus-actual defect
`test_app_create_minimal.py` pins for ``architecture``. ``agnara apps`` reports
this field without importing anything, so it has to be true.

The second is that no generated module imports a transport. A generated
adapter names the capabilities it projects and documents the wiring; it does
not import ``agnara_http`` or ``agnara_mcp``. Those distributions are not on
PyPI and a generated project depends on ``agnara`` alone, so an import would
produce a project that cannot install -- and ``agnara-http``, ``agnara-a2a``
and ``agnara-events`` declare an empty public surface on purpose, so it would
be an import of private names. See ADR 0063.

The project is called ``depot`` here, matching the sibling minimal-template
module, because neither imports the other's generated package.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, main
from agnara_cli._manifest import EXPOSURES, MANIFEST_FILENAME, load_manifest

APP = "payments"
APP_ROOT = f"src/depot/apps/{APP}"
INBOUND = f"{APP_ROOT}/adapters/inbound"

TRANSPORT_PACKAGES = ("agnara_http", "agnara_mcp", "agnara_a2a", "agnara_events", "fastapi")


def create_app(*argv: str) -> int:
    return main(["app", "create", *argv])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert main(["project", "create", "depot", "--directory", str(tmp_path)]) == EXIT_OK
    return tmp_path / "depot"


def app_files(root: Path, app: str = APP) -> set[str]:
    base = root / f"src/depot/apps/{app}"
    return {path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file()}


def declared_exposures(root: Path, app: str = APP) -> tuple[str, ...]:
    manifest = load_manifest(root / MANIFEST_FILENAME)
    return next(entry.exposures for entry in manifest.apps if entry.name == app)


def inbound_modules(root: Path, app: str = APP) -> set[str]:
    """Adapter modules, excluding the package marker the layout always has."""
    return {
        name.rsplit("/", 1)[-1].removesuffix(".py")
        for name in app_files(root, app)
        if "/adapters/inbound/" in name and not name.endswith("__init__.py")
    }


# ---------------------------------------------------------------------------
# What --with adds
# ---------------------------------------------------------------------------


def test_only_the_requested_inbound_adapters_are_added(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--with", "http,mcp") == EXIT_OK

    assert inbound_modules(project) == {"http", "mcp"}


def test_it_adds_nothing_beyond_the_requested_adapters(project: Path) -> None:
    """`--with` changes the inbound package and nothing else in the layout."""
    assert create_app("plain", "--project", str(project)) == EXIT_OK
    assert create_app(APP, "--project", str(project), "--with", "http,mcp") == EXIT_OK

    plain = {name.replace("/plain/", "/APP/") for name in app_files(project, "plain")}
    exposed = {name.replace(f"/{APP}/", "/APP/") for name in app_files(project)}

    assert exposed - plain == {
        "src/depot/apps/APP/adapters/inbound/http.py",
        "src/depot/apps/APP/adapters/inbound/mcp.py",
    }
    assert not plain - exposed


def test_no_with_flag_scaffolds_no_adapter(project: Path) -> None:
    assert create_app(APP, "--project", str(project)) == EXIT_OK

    assert inbound_modules(project) == set()
    assert declared_exposures(project) == ()
    assert (project / INBOUND / "__init__.py").is_file()


@pytest.mark.parametrize("exposure", EXPOSURES)
def test_every_exposure_in_the_vocabulary_can_be_scaffolded(project: Path, exposure: str) -> None:
    assert create_app(APP, "--project", str(project), "--with", exposure) == EXIT_OK

    assert inbound_modules(project) == {exposure}
    assert declared_exposures(project) == (exposure,)


def test_generation_is_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    sources = []
    for directory in ("a", "b"):
        parent = tmp_path / directory
        parent.mkdir()
        main(["project", "create", "depot", "--directory", str(parent)])
        create_app(APP, "--project", str(parent / "depot"), "--with", "http,mcp")
        root = parent / "depot"
        sources.append(
            {name: (root / name).read_text(encoding="utf-8") for name in app_files(root)}
        )

    assert sources[0] == sources[1]


# ---------------------------------------------------------------------------
# The manifest describes the app
# ---------------------------------------------------------------------------


def test_the_manifest_records_the_exposures_that_were_scaffolded(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--with", "http,mcp") == EXIT_OK

    assert declared_exposures(project) == ("http", "mcp")


def test_the_declared_order_is_the_order_that_was_asked_for(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--with", "mcp,http") == EXIT_OK

    assert declared_exposures(project) == ("mcp", "http")


def test_a_repeated_exposure_is_declared_and_written_once(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--with", "mcp,http,mcp") == EXIT_OK

    assert declared_exposures(project) == ("mcp", "http")
    assert inbound_modules(project) == {"http", "mcp"}


def test_the_manifest_stays_readable_by_its_own_parser(project: Path) -> None:
    """A generator that writes TOML its own reader rejects is worse than useless."""
    assert create_app(APP, "--project", str(project), "--with", "http,mcp,tasks") == EXIT_OK

    manifest = load_manifest(project / MANIFEST_FILENAME)
    entry = next(app for app in manifest.apps if app.name == APP)
    assert entry.exposures == ("http", "mcp", "tasks")


# ---------------------------------------------------------------------------
# The generated adapters
# ---------------------------------------------------------------------------


def test_every_generated_adapter_compiles(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--with", ",".join(EXPOSURES)) == EXIT_OK

    for exposure in EXPOSURES:
        path = project / INBOUND / f"{exposure}.py"
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_no_generated_adapter_imports_a_transport(project: Path) -> None:
    """The invariant `docs/SCAFFOLDING.md` states, made true by construction."""
    assert create_app(APP, "--project", str(project), "--with", ",".join(EXPOSURES)) == EXIT_OK

    offenders = [
        f"{name}: {package}"
        for name in app_files(project)
        for package in TRANSPORT_PACKAGES
        if f"import {package}" in (project / name).read_text(encoding="utf-8")
    ]
    assert not offenders, offenders


def test_an_adapter_projects_this_app_s_capabilities(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--with", "http") == EXIT_OK

    source = (project / INBOUND / "http.py").read_text(encoding="utf-8")
    assert "from depot.apps.payments.application.capabilities import" in source
    assert "EXPOSED" in source


def test_the_generated_project_still_passes_ruff_with_adapters(project: Path) -> None:
    """Under the generated project's own configuration, not this one's."""
    try:
        from ruff.__main__ import find_ruff_bin
    except ImportError:  # pragma: no cover - ruff is a development pin
        pytest.skip("ruff is not installed")

    assert create_app(APP, "--project", str(project), "--with", ",".join(EXPOSURES)) == EXIT_OK

    for command in (("check",), ("format", "--check")):
        completed = subprocess.run(
            [str(find_ruff_bin()), *command, "."],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


# ---------------------------------------------------------------------------
# What --with refuses
# ---------------------------------------------------------------------------


def test_an_unknown_exposure_is_refused_before_anything_is_written(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")

    assert create_app(APP, "--project", str(project), "--with", "http,soap") == EXIT_FAILED

    message = capsys.readouterr().err
    assert "soap" in message
    assert "http, mcp, a2a, tasks, events" in message
    assert not (project / APP_ROOT).exists()
    assert (project / MANIFEST_FILENAME).read_text(encoding="utf-8") == before


@pytest.mark.parametrize("value", ["http,,mcp", "http,", ",http", ""])
def test_a_malformed_list_is_refused(
    project: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    assert create_app(APP, "--project", str(project), "--with", value) == EXIT_FAILED

    assert "empty entry" in capsys.readouterr().err
    assert not (project / APP_ROOT).exists()


def test_the_minimal_architecture_refuses_an_exposure(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A minimal app has no adapters package; giving it one makes it the other
    template, so the command says which flag resolves it rather than guessing.
    """
    assert (
        create_app(APP, "--project", str(project), "--architecture", "minimal", "--with", "http")
        == EXIT_FAILED
    )

    message = capsys.readouterr().err
    assert "no adapters package" in message
    assert "--architecture modular-hexagonal" in message
    assert not (project / APP_ROOT).exists()


def test_minimal_without_an_exposure_is_still_fine(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--architecture", "minimal") == EXIT_OK
    assert declared_exposures(project) == ()


# ---------------------------------------------------------------------------
# The shared plan mechanism carries the new files
# ---------------------------------------------------------------------------


def test_a_dry_run_writes_no_adapter(project: Path) -> None:
    before = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")

    assert create_app(APP, "--project", str(project), "--with", "http,mcp", "--dry-run") == EXIT_OK

    assert not (project / APP_ROOT).exists()
    assert (project / MANIFEST_FILENAME).read_text(encoding="utf-8") == before


def test_json_lists_the_adapters_and_is_deterministic(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = (APP, "--project", str(project), "--with", "http,mcp", "--dry-run", "--json")

    assert create_app(*arguments) == EXIT_OK
    first = capsys.readouterr().out
    assert create_app(*arguments) == EXIT_OK
    second = capsys.readouterr().out

    assert first == second
    paths = {entry["path"] for entry in json.loads(first)["files"]}
    assert {f"{INBOUND}/http.py", f"{INBOUND}/mcp.py"}.issubset(paths)
