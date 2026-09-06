"""E0A.2: the shape of `agnara.toml` and every way it is refused.

`docs/PROJECT_MANIFEST.md` proposes the format; ADR 0059 records the decisions
it left open. These tests are the format: what is accepted, what is rejected,
and what each rejection says. Generators land next and will write to the paths
declared here, so validation is a safety boundary, not a convenience.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from agnara_cli._manifest import (
    ARCHITECTURES,
    DEFAULT_ARCHITECTURE,
    EXPOSURES,
    MANIFEST_FILENAME,
    ManifestError,
    find_manifest,
    load_manifest,
    parse_manifest,
)

COMPLETE = """
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

MINIMAL = """
[project]
name = "commerce"
"""


def refused(text: str) -> str:
    with pytest.raises(ManifestError) as raised:
        parse_manifest(text)
    return str(raised.value)


# ---------------------------------------------------------------------------
# What is accepted
# ---------------------------------------------------------------------------


def test_a_complete_manifest_is_read_in_declaration_order() -> None:
    manifest = parse_manifest(COMPLETE)

    assert manifest.name == "commerce"
    assert manifest.python == ">=3.14"
    assert manifest.default_architecture == "minimal"
    assert [app.name for app in manifest.apps] == ["users", "payments"]

    users, payments = manifest.apps
    assert users.module == "commerce.apps.users"
    assert users.path == PurePosixPath("src/commerce/apps/users")
    assert users.architecture == "modular-hexagonal"
    assert users.exposures == ("http", "mcp")

    # An app that declares no architecture inherits the project default,
    # not the built-in default.
    assert payments.architecture == "minimal"
    assert payments.exposures == ()


def test_a_project_with_no_apps_is_valid() -> None:
    """A freshly created project has none, and must still load."""
    manifest = parse_manifest(MINIMAL)

    assert manifest.apps == ()
    assert manifest.python is None
    assert manifest.default_architecture == DEFAULT_ARCHITECTURE


def test_an_empty_apps_table_is_valid() -> None:
    assert parse_manifest(MINIMAL + "\n[apps]\n").apps == ()


@pytest.mark.parametrize("architecture", ARCHITECTURES)
def test_every_documented_architecture_is_accepted(architecture: str) -> None:
    text = f'{MINIMAL}\n[defaults]\narchitecture = "{architecture}"\n'

    assert parse_manifest(text).default_architecture == architecture


@pytest.mark.parametrize("exposure", EXPOSURES)
def test_every_documented_exposure_is_accepted(exposure: str) -> None:
    text = (
        f"{MINIMAL}\n[apps.one]\nmodule = 'commerce.one'\n"
        f"path = 'src/commerce/one'\nexposures = ['{exposure}']\n"
    )

    assert parse_manifest(text).apps[0].exposures == (exposure,)


def test_a_named_app_can_be_looked_up() -> None:
    manifest = parse_manifest(COMPLETE)

    assert manifest.app("payments").module == "commerce.apps.payments"


def test_looking_up_an_absent_app_lists_the_declared_ones() -> None:
    manifest = parse_manifest(COMPLETE)

    with pytest.raises(ManifestError) as raised:
        manifest.app("catalog")

    assert "'catalog'" in str(raised.value)
    assert "users, payments" in str(raised.value)


def test_declaration_order_is_preserved_rather_than_sorted() -> None:
    """Order is the operator's; re-sorting would make diffs lie."""
    text = MINIMAL + "".join(
        f"\n[apps.{name}]\nmodule = 'commerce.{name}'\npath = 'src/commerce/{name}'\n"
        for name in ("zulu", "alpha", "mike")
    )

    assert [app.name for app in parse_manifest(text).apps] == ["zulu", "alpha", "mike"]


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_invalid_toml_is_refused_with_the_parser_reason() -> None:
    assert "is not valid TOML" in refused("[project\nname = 'x'")


def test_a_missing_project_table_is_refused() -> None:
    assert "project: table is required" in refused("[defaults]\narchitecture = 'minimal'\n")


def test_a_missing_project_name_is_refused() -> None:
    assert "project.name: is required" in refused("[project]\npython = '>=3.14'\n")


@pytest.mark.parametrize("name", ["", "  ", "not an identifier", "1commerce", "com-merce"])
def test_an_unusable_project_name_is_refused(name: str) -> None:
    message = refused(f"[project]\nname = '{name}'\n")

    assert "project.name" in message


def test_an_unknown_top_level_table_is_refused_rather_than_ignored() -> None:
    """The whole point of strictness: a typo must fail, not do nothing."""
    message = refused(MINIMAL + "\n[application.users]\nmodule = 'x'\n")

    assert "'application'" in message
    assert "accepted: apps, defaults, project" in message


def test_a_misspelled_app_key_is_refused_rather_than_ignored() -> None:
    text = (
        MINIMAL + "\n[apps.users]\nmodule = 'commerce.users'\n"
        "path = 'src/commerce/users'\nexposure = ['http']\n"
    )
    message = refused(text)

    assert "apps.users" in message
    assert "'exposure'" in message
    assert "architecture, exposures, module, path" in message


@pytest.mark.parametrize("field", ["module", "path"])
def test_a_required_app_field_is_refused_when_absent(field: str) -> None:
    fields = {"module": "commerce.users", "path": "src/commerce/users"}
    del fields[field]
    body = "".join(f"{key} = '{value}'\n" for key, value in fields.items())

    assert f"apps.users.{field}: is required" in refused(f"{MINIMAL}\n[apps.users]\n{body}")


@pytest.mark.parametrize("module", ["commerce apps", "commerce..users", "1commerce", "-x"])
def test_an_unusable_app_module_is_refused(module: str) -> None:
    text = f"{MINIMAL}\n[apps.users]\nmodule = '{module}'\npath = 'src/commerce/users'\n"

    assert "is not a module path" in refused(text)


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/etc/agnara", "must be relative"),
        ("../outside", "must not leave the project directory"),
        ("src/../../outside", "must not leave the project directory"),
        ("src\\commerce\\users", "must use '/' separators"),
    ],
)
def test_an_app_path_that_escapes_the_project_is_refused(path: str, reason: str) -> None:
    """Generators will write here later; containment is checked before that."""
    text = f"{MINIMAL}\n[apps.users]\nmodule = 'commerce.users'\npath = '{path}'\n"
    message = refused(text)

    assert "apps.users.path" in message
    assert reason in message


@pytest.mark.parametrize("architecture", ["hexagonal", "modular_hexagonal", "MINIMAL"])
def test_an_unknown_architecture_is_refused_with_the_accepted_set(architecture: str) -> None:
    message = refused(f"{MINIMAL}\n[defaults]\narchitecture = '{architecture}'\n")

    assert "defaults.architecture" in message
    assert "modular-hexagonal, minimal, vertical" in message


def test_an_unknown_exposure_is_refused_with_the_accepted_set() -> None:
    text = (
        f"{MINIMAL}\n[apps.users]\nmodule = 'commerce.users'\n"
        "path = 'src/commerce/users'\nexposures = ['http', 'grpc']\n"
    )
    message = refused(text)

    assert "apps.users.exposures[1]" in message
    assert "http, mcp, a2a, tasks, events" in message


def test_a_repeated_exposure_is_refused() -> None:
    text = (
        f"{MINIMAL}\n[apps.users]\nmodule = 'commerce.users'\n"
        "path = 'src/commerce/users'\nexposures = ['http', 'http']\n"
    )

    assert "listed more than once" in refused(text)


def test_a_non_string_exposure_is_refused() -> None:
    text = (
        f"{MINIMAL}\n[apps.users]\nmodule = 'commerce.users'\n"
        "path = 'src/commerce/users'\nexposures = [1]\n"
    )

    assert "must be a string, not int" in refused(text)


def test_exposures_must_be_an_array() -> None:
    text = (
        f"{MINIMAL}\n[apps.users]\nmodule = 'commerce.users'\n"
        "path = 'src/commerce/users'\nexposures = 'http'\n"
    )

    assert "must be an array, not str" in refused(text)


def test_two_apps_may_not_share_a_module() -> None:
    text = MINIMAL + "".join(
        f"\n[apps.{name}]\nmodule = 'commerce.shared'\npath = 'src/commerce/{name}'\n"
        for name in ("users", "payments")
    )
    message = refused(text)

    assert "apps.payments.module" in message
    assert "already declared by app 'users'" in message


def test_two_apps_may_not_share_a_path() -> None:
    text = MINIMAL + "".join(
        f"\n[apps.{name}]\nmodule = 'commerce.{name}'\npath = 'src/commerce/shared'\n"
        for name in ("users", "payments")
    )

    assert "already declared by app 'users'" in refused(text)


@pytest.mark.parametrize("name", ["not-an-app", "1users", "with space"])
def test_an_unusable_app_name_is_refused(name: str) -> None:
    text = f"{MINIMAL}\n[apps.'{name}']\nmodule = 'commerce.x'\npath = 'src/x'\n"

    assert "is not a valid app name" in refused(text)


def test_a_non_table_project_is_refused() -> None:
    assert "must be a table, not str" in refused("project = 'commerce'\n")


def test_an_empty_python_specifier_is_refused() -> None:
    assert "project.python" in refused("[project]\nname = 'commerce'\npython = '  '\n")


# ---------------------------------------------------------------------------
# Files and discovery
# ---------------------------------------------------------------------------


def test_a_manifest_is_loaded_from_disk_and_remembers_its_path(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_FILENAME
    path.write_text(COMPLETE, encoding="utf-8")

    manifest = load_manifest(path)

    assert manifest.source == path
    assert manifest.name == "commerce"


def test_a_diagnostic_names_the_file_it_came_from(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_FILENAME
    path.write_text("[project]\n", encoding="utf-8")

    with pytest.raises(ManifestError) as raised:
        load_manifest(path)

    assert str(path) in str(raised.value)


def test_a_missing_file_is_an_operator_error_not_an_oserror(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="no such file"):
        load_manifest(tmp_path / MANIFEST_FILENAME)


def test_a_manifest_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_FILENAME
    path.write_bytes(b"[project]\nname = '\xff\xfe'\n")

    with pytest.raises(ManifestError, match="is not valid UTF-8"):
        load_manifest(path)


def test_discovery_finds_a_manifest_in_an_ancestor_directory(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(MINIMAL, encoding="utf-8")
    nested = tmp_path / "src" / "commerce" / "apps"
    nested.mkdir(parents=True)

    assert find_manifest(nested) == tmp_path / MANIFEST_FILENAME


def test_discovery_prefers_the_nearest_manifest(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(MINIMAL, encoding="utf-8")
    nested = tmp_path / "inner"
    nested.mkdir()
    (nested / MANIFEST_FILENAME).write_text(MINIMAL, encoding="utf-8")

    assert find_manifest(nested) == nested / MANIFEST_FILENAME


def test_discovery_returning_nothing_is_a_normal_answer(tmp_path: Path) -> None:
    """A project without a manifest is not an exception; the caller decides."""
    empty = tmp_path / "empty"
    empty.mkdir()

    assert find_manifest(empty) is None


def test_a_directory_named_like_the_manifest_is_not_a_manifest(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).mkdir()

    assert find_manifest(tmp_path) is None
