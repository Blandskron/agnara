"""E0A.7: profiles are scaffolding aliases that resolve to exposures.

`docs/CLI_SPEC.md` "Profiles" gives the mapping, and ADR 0013 fixes what a
profile *is*: it "selects initial adapter scaffolding only" and is "not
persisted as a runtime application type".

Two properties carry that decision, and both are tested here rather than
assumed. A profile must produce exactly the exposures its row specifies, and
it must leave **no trace of itself** in `agnara.toml` -- recording a profile
name would make it look like a runtime app type, which is the thing ADR 0013
refuses.

`docs/CLI_SPEC.md` says profiles can be "combined/overridden with `--with`",
which permits two different behaviours. ADR 0064 chooses union and records
why; `test_with_adds_to_a_profile_rather_than_replacing_it` is what pins it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, main
from agnara_cli._app import PROFILES
from agnara_cli._manifest import MANIFEST_FILENAME, load_manifest

APP = "catalog"

#: The table in `docs/CLI_SPEC.md` "Profiles", transcribed from the document
#: rather than from the implementation, so a change to either is visible here.
SPECIFIED = {
    "core": (),
    "api": ("http",),
    "mcp": ("mcp",),
    "agentic": ("mcp", "a2a"),
    "worker": ("tasks", "events"),
    "full": ("http", "mcp", "a2a", "events", "tasks"),
}


def create_app(*argv: str) -> int:
    return main(["app", "create", *argv])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert main(["project", "create", "depot", "--directory", str(tmp_path)]) == EXIT_OK
    return tmp_path / "depot"


def declared_exposures(root: Path, app: str = APP) -> tuple[str, ...]:
    manifest = load_manifest(root / MANIFEST_FILENAME)
    return next(entry.exposures for entry in manifest.apps if entry.name == app)


def inbound_modules(root: Path, app: str = APP) -> set[str]:
    base = root / f"src/depot/apps/{app}/adapters/inbound"
    if not base.is_dir():
        return set()
    return {path.stem for path in base.glob("*.py") if path.stem != "__init__"}


# ---------------------------------------------------------------------------
# The mapping
# ---------------------------------------------------------------------------


def test_the_implementation_covers_exactly_the_specified_profiles() -> None:
    assert set(PROFILES) == set(SPECIFIED)


@pytest.mark.parametrize("profile", sorted(SPECIFIED))
def test_a_profile_declares_the_exposures_its_row_specifies(project: Path, profile: str) -> None:
    assert create_app(APP, "--project", str(project), "--profile", profile) == EXIT_OK

    assert declared_exposures(project) == SPECIFIED[profile]


@pytest.mark.parametrize("profile", sorted(SPECIFIED))
def test_a_profile_scaffolds_the_adapters_it_declares(project: Path, profile: str) -> None:
    """The manifest and the directory agree, whichever way the request arrived."""
    assert create_app(APP, "--project", str(project), "--profile", profile) == EXIT_OK

    assert inbound_modules(project) == set(SPECIFIED[profile])
    assert set(declared_exposures(project)) == inbound_modules(project)


def test_the_default_is_core(project: Path) -> None:
    assert create_app(APP, "--project", str(project)) == EXIT_OK
    assert declared_exposures(project) == SPECIFIED["core"]


def test_core_is_not_a_special_case(project: Path) -> None:
    """Asking for the default explicitly does the same as not asking."""
    assert create_app(APP, "--project", str(project), "--profile", "core") == EXIT_OK
    assert declared_exposures(project) == ()
    assert inbound_modules(project) == set()


# ---------------------------------------------------------------------------
# A profile is an alias, not an app type (ADR 0013)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile", sorted(SPECIFIED))
def test_the_profile_name_never_reaches_the_manifest(project: Path, profile: str) -> None:
    """Recording it would make a scaffolding alias look like a runtime type."""
    assert create_app(APP, "--project", str(project), "--profile", profile) == EXIT_OK

    assert "profile" not in (project / MANIFEST_FILENAME).read_text(encoding="utf-8")


def test_a_profile_and_the_equivalent_with_produce_the_same_app(tmp_path: Path) -> None:
    """`--profile agentic` is `--with mcp,a2a`; nothing else distinguishes them."""
    results = []
    for directory, argv in (("a", ("--profile", "agentic")), ("b", ("--with", "mcp,a2a"))):
        parent = tmp_path / directory
        parent.mkdir()
        main(["project", "create", "depot", "--directory", str(parent)])
        root = parent / "depot"
        assert create_app(APP, "--project", str(root), *argv) == EXIT_OK
        results.append(
            {
                path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
                for path in root.rglob("*")
                if path.is_file()
            }
        )

    assert results[0] == results[1]


# ---------------------------------------------------------------------------
# Combining with --with
# ---------------------------------------------------------------------------


def test_with_adds_to_a_profile_rather_than_replacing_it(project: Path) -> None:
    """ADR 0064: "combined/overridden" is resolved as union."""
    assert create_app(APP, "--project", str(project), "--profile", "api", "--with", "mcp") == (
        EXIT_OK
    )

    assert declared_exposures(project) == ("http", "mcp")


def test_the_profile_contributes_first_and_with_appends(project: Path) -> None:
    assert (
        create_app(APP, "--project", str(project), "--profile", "worker", "--with", "http")
        == EXIT_OK
    )

    assert declared_exposures(project) == ("tasks", "events", "http")


def test_an_exposure_a_profile_already_brought_is_not_repeated(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--profile", "api", "--with", "http") == (
        EXIT_OK
    )

    assert declared_exposures(project) == ("http",)
    assert inbound_modules(project) == {"http"}


def test_with_on_top_of_full_changes_nothing(project: Path) -> None:
    assert create_app(APP, "--project", str(project), "--profile", "full", "--with", "mcp") == (
        EXIT_OK
    )

    assert declared_exposures(project) == SPECIFIED["full"]


# ---------------------------------------------------------------------------
# What a profile refuses
# ---------------------------------------------------------------------------


def test_an_unknown_profile_is_a_usage_error(project: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        create_app(APP, "--project", str(project), "--profile", "serverless")
    assert raised.value.code == 2


def test_minimal_refuses_a_profile_that_brings_exposures(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same rule as `--with`: a minimal app has no adapters package."""
    assert (
        create_app(APP, "--project", str(project), "--architecture", "minimal", "--profile", "api")
        == EXIT_FAILED
    )

    message = capsys.readouterr().err
    assert "no adapters package" in message
    # The message names the flag that actually caused it, not a flag not passed.
    assert "--profile api" in message
    assert not (project / f"src/depot/apps/{APP}").exists()


def test_minimal_accepts_the_core_profile(project: Path) -> None:
    """`core` brings no exposures, so there is nothing for minimal to refuse."""
    assert (
        create_app(APP, "--project", str(project), "--architecture", "minimal", "--profile", "core")
        == EXIT_OK
    )

    assert declared_exposures(project) == ()


def test_a_refused_profile_leaves_the_manifest_alone(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")

    assert (
        create_app(APP, "--project", str(project), "--architecture", "minimal", "--profile", "full")
        == EXIT_FAILED
    )
    capsys.readouterr()

    assert (project / MANIFEST_FILENAME).read_text(encoding="utf-8") == before
