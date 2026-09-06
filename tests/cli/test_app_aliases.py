"""E0A.8: the convenience aliases are the canonical command, not a copy.

`docs/CLI_SPEC.md` "Convenience aliases" states the constraint twice:

> These MUST behave as aliases only.

> The implementation must not create separate code paths or framework types
> for these aliases.

So the interesting test is not that `agnara app-mcp tools` works. It is that
it is *indistinguishable* from `agnara app create tools --profile mcp` --
byte-identical output, the same flags, the same refusals. Two implementations
that agree today would satisfy a weaker test and drift later, which is the
failure this item is named after.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, main
from agnara_cli._app import ALIASES, PROFILES
from agnara_cli._manifest import MANIFEST_FILENAME, load_manifest

#: `docs/CLI_SPEC.md` "Convenience aliases", transcribed from the document.
SPECIFIED = {
    "app-api": "api",
    "app-mcp": "mcp",
    "app-agent": "agentic",
    "app-worker": "worker",
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert main(["project", "create", "depot", "--directory", str(tmp_path)]) == EXIT_OK
    return tmp_path / "depot"


def tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file()
    }


def fresh_project(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    assert main(["project", "create", "depot", "--directory", str(parent)]) == EXIT_OK
    return parent / "depot"


def declared_exposures(root: Path, app: str) -> tuple[str, ...]:
    manifest = load_manifest(root / MANIFEST_FILENAME)
    return next(entry.exposures for entry in manifest.apps if entry.name == app)


# ---------------------------------------------------------------------------
# The mapping
# ---------------------------------------------------------------------------


def test_exactly_the_specified_aliases_exist() -> None:
    """`core` and `full` have no alias, and none should be invented."""
    assert ALIASES == SPECIFIED


def test_every_alias_names_a_real_profile() -> None:
    assert set(ALIASES.values()) <= set(PROFILES)


@pytest.mark.parametrize(("alias", "profile"), sorted(SPECIFIED.items()))
def test_an_alias_declares_its_profile_s_exposures(project: Path, alias: str, profile: str) -> None:
    assert main([alias, "svc", "--project", str(project)]) == EXIT_OK

    assert declared_exposures(project, "svc") == PROFILES[profile]


# ---------------------------------------------------------------------------
# An alias is the canonical command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("alias", "profile"), sorted(SPECIFIED.items()))
def test_an_alias_and_its_canonical_form_produce_identical_projects(
    tmp_path: Path, alias: str, profile: str
) -> None:
    """The property `docs/CLI_SPEC.md` actually asks for."""
    aliased = fresh_project(tmp_path / "aliased")
    assert main([alias, "svc", "--project", str(aliased)]) == EXIT_OK

    canonical = fresh_project(tmp_path / "canonical")
    assert (
        main(["app", "create", "svc", "--project", str(canonical), "--profile", profile]) == EXIT_OK
    )

    assert tree(aliased) == tree(canonical)


@pytest.mark.parametrize("alias", sorted(SPECIFIED))
def test_an_alias_accepts_the_other_options_unchanged(tmp_path: Path, alias: str) -> None:
    """Only the profile is fixed; the rest of the command is the same command."""
    aliased = fresh_project(tmp_path / "aliased")
    assert (
        main(
            [
                alias,
                "svc",
                "--project",
                str(aliased),
                "--with",
                "http",
                "--architecture",
                "modular-hexagonal",
            ]
        )
        == EXIT_OK
    )

    canonical = fresh_project(tmp_path / "canonical")
    assert (
        main(
            [
                "app",
                "create",
                "svc",
                "--project",
                str(canonical),
                "--profile",
                SPECIFIED[alias],
                "--with",
                "http",
                "--architecture",
                "modular-hexagonal",
            ]
        )
        == EXIT_OK
    )

    assert tree(aliased) == tree(canonical)


@pytest.mark.parametrize("alias", sorted(SPECIFIED))
def test_an_alias_shares_the_refusals(
    project: Path, capsys: pytest.CaptureFixture[str], alias: str
) -> None:
    """A separate code path would be free to refuse differently, or not at all."""
    assert main([alias, "svc", "--project", str(project), "--architecture", "minimal"]) == (
        EXIT_FAILED
    )

    assert "no adapters package" in capsys.readouterr().err
    assert not (project / "src/depot/apps/svc").exists()


@pytest.mark.parametrize("alias", sorted(SPECIFIED))
def test_an_alias_refuses_an_unusable_app_name(
    project: Path, capsys: pytest.CaptureFixture[str], alias: str
) -> None:
    assert main([alias, "Not-An-Identifier", "--project", str(project)]) == EXIT_FAILED
    assert "invalid app name" in capsys.readouterr().err


@pytest.mark.parametrize("alias", sorted(SPECIFIED))
def test_an_alias_dry_run_writes_nothing(project: Path, alias: str) -> None:
    before = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")

    assert main([alias, "svc", "--project", str(project), "--dry-run"]) == EXIT_OK

    assert not (project / "src/depot/apps/svc").exists()
    assert (project / MANIFEST_FILENAME).read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# What an alias does not offer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("alias", sorted(SPECIFIED))
def test_an_alias_does_not_take_a_profile(project: Path, alias: str) -> None:
    """The alias *is* the profile; accepting both invites a self-contradiction."""
    with pytest.raises(SystemExit) as raised:
        main([alias, "svc", "--project", str(project), "--profile", "worker"])
    assert raised.value.code == 2


@pytest.mark.parametrize("alias", sorted(SPECIFIED))
def test_the_profile_name_still_never_reaches_the_manifest(project: Path, alias: str) -> None:
    """ADR 0013 holds however the request arrived."""
    assert main([alias, "svc", "--project", str(project)]) == EXIT_OK

    assert "profile" not in (project / MANIFEST_FILENAME).read_text(encoding="utf-8")
