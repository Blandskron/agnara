"""E0A.12-E0A.14: what the generators produce, pinned and checked as a whole.

Three backlog items share one idea. Everything here is derived from the
generated tree rather than from a list someone has to remember to update --
which is what the four dependency-direction tests in `test_app_create.py`
could not do, being bound to a literal `EXPECTED_FILES` for the default
template with no exposures.

* **E0A.12** — every scenario is pinned against
  `fixtures/generated_reference.json`, so an unintended change to generated
  content is a reviewable diff rather than a silent one.
* **E0A.13** — line endings and path separators belong to the generated
  project, not to the machine that generated it.
* **E0A.14** — the direction rules, applied across both architectures and
  across an app that has inbound adapters.

A test that iterates a file set proves nothing when the set is empty, so the
counts are asserted first. `test_the_scenarios_are_not_vacuous` is the guard
for every parametrised case below it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agnara_cli import EXIT_OK, main
from agnara_cli._manifest import MANIFEST_FILENAME, load_manifest
from tests.cli import reference_projects
from tests.cli.reference_projects import FIXTURE, SCENARIOS

REGENERATE = "uv run python -m tests.cli.reference_projects"

#: The smallest each scenario may be before the assertions below stop meaning
#: anything. Deliberately loose: this guards vacuity, not the exact layout,
#: which the golden fixture already pins.
MINIMUM_FILES = {
    "project": 8,
    "default-app": 20,
    "minimal-app": 12,
    "exposed-app": 22,
}

TRANSPORT_PACKAGES = ("agnara_http", "agnara_mcp", "agnara_a2a", "agnara_events", "fastapi")


@pytest.fixture(scope="module")
def pinned() -> dict[str, dict[str, str]]:
    """The recorded generator output, keyed by scenario."""
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {name: scenario["files"] for name, scenario in document["scenarios"].items()}


@pytest.fixture(scope="module")
def produced(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, str]]:
    """What the generators produce right now, for every scenario."""
    trees = {}
    for scenario in SCENARIOS:
        directory = tmp_path_factory.mktemp(scenario)
        root = reference_projects.generate(scenario, directory)
        trees[scenario] = reference_projects._tree(root)
    return trees


def python_files(tree: dict[str, str]) -> dict[str, str]:
    return {name: text for name, text in tree.items() if name.endswith(".py")}


# ---------------------------------------------------------------------------
# Non-vacuity
# ---------------------------------------------------------------------------


def test_the_scenarios_are_not_vacuous(produced: dict[str, dict[str, str]]) -> None:
    """Every assertion below iterates these trees; an empty one proves nothing."""
    assert set(produced) == set(SCENARIOS)
    for scenario, minimum in MINIMUM_FILES.items():
        assert len(produced[scenario]) >= minimum, (scenario, sorted(produced[scenario]))
        assert python_files(produced[scenario]), scenario


def test_the_fixture_covers_every_scenario(pinned: dict[str, dict[str, str]]) -> None:
    assert set(pinned) == set(SCENARIOS)


# ---------------------------------------------------------------------------
# E0A.12 — golden files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_generated_tree_matches_the_pinned_record(
    scenario: str, produced: dict[str, dict[str, str]], pinned: dict[str, dict[str, str]]
) -> None:
    """An unintended change to generated content fails here, as a diff."""
    assert sorted(produced[scenario]) == sorted(pinned[scenario]), (
        f"{scenario}: the generated file set changed. If intended, regenerate with: {REGENERATE}"
    )
    for name in sorted(produced[scenario]):
        assert produced[scenario][name] == pinned[scenario][name], (
            f"{scenario}: {name} changed. If intended, regenerate with: {REGENERATE}"
        )


def test_the_fixture_records_how_to_regenerate_itself(pinned: dict[str, dict[str, str]]) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert document["regenerate_with"] == REGENERATE


def test_regenerating_twice_produces_the_same_record() -> None:
    """The fixture is only trustworthy if the generators are deterministic."""
    assert reference_projects.serialized() == reference_projects.serialized()


# ---------------------------------------------------------------------------
# E0A.13 — paths and line endings belong to the project, not the host
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_every_generated_file_uses_newline_endings(
    scenario: str, produced: dict[str, dict[str, str]]
) -> None:
    """A generated project is shared; its line endings are not this machine's."""
    offenders = [name for name, text in produced[scenario].items() if "\r\n" in text]
    assert not offenders, offenders


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_manifest_declares_posix_paths(
    scenario: str, tmp_path: Path, produced: dict[str, dict[str, str]]
) -> None:
    """`agnara.toml` is committed and read on other platforms than this one."""
    manifest = produced[scenario][MANIFEST_FILENAME]
    for line in manifest.splitlines():
        if line.startswith("path = "):
            assert "\\" not in line, line
            assert ":" not in line, f"an absolute path leaked into the manifest: {line}"


def test_the_manifest_parses_back_into_posix_paths(tmp_path: Path) -> None:
    root = reference_projects.generate("exposed-app", tmp_path)
    manifest = load_manifest(root / MANIFEST_FILENAME)

    for app in manifest.apps:
        assert not app.path.is_absolute(), app.path
        assert ".." not in app.path.parts, app.path
        assert "\\" not in str(app.path), app.path


def test_the_json_plan_reports_posix_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plan is machine-readable output; a backslash would not survive a move."""
    assert main(["project", "create", "commerce", "--directory", str(tmp_path)]) == EXIT_OK
    root = tmp_path / "commerce"
    capsys.readouterr()  # discard the project report; only the plan is JSON

    assert (
        main(
            [
                "app",
                "create",
                "payments",
                "--project",
                str(root),
                "--with",
                "http",
                "--dry-run",
                "--json",
            ]
        )
        == EXIT_OK
    )

    plan = json.loads(capsys.readouterr().out)
    assert plan["files"], "an empty plan would pass every assertion below"
    for entry in plan["files"]:
        assert "\\" not in entry["path"], entry


def test_a_generated_project_carries_no_host_absolute_path(
    produced: dict[str, dict[str, str]],
) -> None:
    """Nothing generated may embed the directory it happened to be created in."""
    offenders = [
        f"{scenario}:{name}"
        for scenario, tree in produced.items()
        for name, text in tree.items()
        if "C:\\" in text or "/tmp/" in text or "\\Users\\" in text
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("name", ["Billing", "BILLING", "Payments"])
def test_an_upper_case_app_name_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    """On a case-insensitive filesystem the package and the import would diverge."""
    assert main(["project", "create", "commerce", "--directory", str(tmp_path)]) == EXIT_OK
    root = tmp_path / "commerce"

    assert main(["app", "create", name, "--project", str(root)]) != EXIT_OK
    assert "lower_case" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# E0A.14 — dependency direction, derived from the tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_no_generated_module_imports_a_transport(
    scenario: str, produced: dict[str, dict[str, str]]
) -> None:
    offenders = [
        f"{name}: {package}"
        for name, text in python_files(produced[scenario]).items()
        for package in TRANSPORT_PACKAGES
        if f"import {package}" in text
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_inner_layers_never_import_an_adapter(
    scenario: str, produced: dict[str, dict[str, str]]
) -> None:
    """Dependencies point inward: the application knows its port, not its adapter.

    Derived from the tree, so a file the generator starts writing is covered
    without anyone adding it to a list.
    """
    inner = {
        name: text
        for name, text in python_files(produced[scenario]).items()
        if "/domain/" in name or "/application/" in name
    }
    offenders = [name for name, text in inner.items() if ".adapters." in text]
    assert not offenders, offenders


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_domain_imports_nothing_from_the_application(
    scenario: str, produced: dict[str, dict[str, str]]
) -> None:
    offenders = [
        name
        for name, text in python_files(produced[scenario]).items()
        if "/domain/" in name and ".application." in text
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_only_the_module_knows_both_the_application_and_its_adapters(
    scenario: str, produced: dict[str, dict[str, str]]
) -> None:
    """`module.py` is the app's composition boundary, and the only one.

    The app's own tests are excluded: wiring an adapter to the code under test
    is what testing the composition means.
    """
    knows_both = [
        name
        for name, text in sorted(python_files(produced[scenario]).items())
        if "/tests/" not in name and ".adapters." in text and ".application." in text
    ]
    assert all(name.endswith("/module.py") for name in knows_both), knows_both


def test_an_inbound_adapter_depends_on_the_application_and_nothing_deeper(
    produced: dict[str, dict[str, str]],
) -> None:
    """The exposed scenario is the only one with inbound adapters to check."""
    adapters = {
        name: text
        for name, text in python_files(produced["exposed-app"]).items()
        if "/adapters/inbound/" in name and not name.endswith("__init__.py")
    }
    assert adapters, "the exposed scenario generated no inbound adapter"

    for name, text in adapters.items():
        assert ".application.capabilities" in text, name
        assert ".domain." not in text, f"{name} reaches past the application layer"


def test_nothing_imports_an_inbound_adapter(produced: dict[str, dict[str, str]]) -> None:
    """An inbound adapter is an entry point; importing one inverts the direction."""
    offenders = [
        name
        for name, text in python_files(produced["exposed-app"]).items()
        if "/adapters/inbound/" not in name and ".adapters.inbound." in text
    ]
    assert not offenders, offenders
