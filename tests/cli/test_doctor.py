"""Operator-visible static diagnostics never execute or repair project code."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, _doctor, main

MANIFEST = """[project]
name = "commerce"
python = ">=99.0"

[apps.users]
module = "commerce.apps.users"
path = "src/commerce/apps/users"
exposures = ["http", "mcp"]

[apps.payments]
module = "commerce.apps.payments"
path = "src/commerce/apps/payments"
exposures = ["http"]
"""


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, str], list[str]]:
    values = dict.fromkeys(("agnara", "agnara-cli", "agnara-http", "agnara-mcp"), "1.0.3")
    reads: list[str] = []

    def lookup(name: str) -> str:
        reads.append(name)
        if name not in values:
            raise PackageNotFoundError(name)
        return values[name]

    monkeypatch.setattr(_doctor, "version", lookup)
    monkeypatch.setattr(_doctor, "_python_version", lambda: (3, 14, 4))
    return values, reads


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "agnara.toml").write_text(MANIFEST, encoding="utf-8")
    for app in ("users", "payments"):
        (tmp_path / "src" / "commerce" / "apps" / app).mkdir(parents=True)
    return tmp_path


def report(project: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    code = main(["doctor", "--project", str(project), "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return code, json.loads(captured.out)


def checks(document: dict) -> dict[str, dict]:
    return {item["id"]: item for item in document["checks"]}


def test_json_is_deterministic_ordered_and_explicit_about_coverage(
    project: Path, installed, capsys: pytest.CaptureFixture[str]
) -> None:
    code, document = report(project, capsys)
    assert code == EXIT_OK
    assert document["format"] == "agnara.doctor" and document["format_version"] == 1
    assert document["project"] == {"name": "commerce", "python": ">=99.0"}
    assert document["status"] == "pass"
    assert all(item["status"] == "pass" for item in document["checks"])
    assert list(checks(document)) == [
        "python",
        "manifest",
        "distribution:agnara",
        "distribution:agnara-cli",
        "app:users:path",
        "app:payments:path",
        "distribution:agnara-http",
        "distribution:agnara-mcp",
    ]
    assert set(document["unchecked"]) == {
        "project_python_constraint",
        "application_imports",
        "runtime_registration",
        "dependency_cycles",
        "protocol_configuration",
        "architecture_rules",
        "transitive_dependencies",
    }
    assert installed[1] == ["agnara", "agnara-cli", "agnara-http", "agnara-mcp"]
    assert report(project, capsys) == (code, document)


def test_text_report_and_failure_preserve_stdout(
    project: Path, installed, capsys: pytest.CaptureFixture[str]
) -> None:
    installed[0].pop("agnara-http")
    assert main(["doctor", "--project", str(project)]) == EXIT_FAILED
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "doctor commerce: fail" in captured.out
    assert "[fail] distribution:agnara-http: not installed" in captured.out
    assert "Unchecked:" in captured.out and "dependency_cycles" in captured.out
    assert "\x1b" not in captured.out


@pytest.mark.parametrize("distribution", ["agnara", "agnara-cli", "agnara-http", "agnara-mcp"])
@pytest.mark.parametrize("problem", ["missing", "mismatch"])
def test_metadata_absence_and_synchronized_version_refusal(
    project: Path, installed, capsys: pytest.CaptureFixture[str], distribution: str, problem: str
) -> None:
    if problem == "missing":
        installed[0].pop(distribution)
    else:
        installed[0][distribution] = "different-version"
    code, document = report(project, capsys)
    assert code == EXIT_FAILED and document["status"] == "fail"
    if distribution == "agnara" and problem == "mismatch":
        assert checks(document)["distribution:agnara-cli"]["status"] == "fail"
    else:
        assert checks(document)[f"distribution:{distribution}"]["status"] == "fail"


@pytest.mark.parametrize(
    ("exposure", "message"),
    [
        ("a2a", "adapter metadata checks are not implemented for this declared exposure"),
        ("events", "reserved namespace; no implemented Agnara event runtime"),
        ("tasks", "no implemented Agnara task runtime"),
    ],
)
@pytest.mark.parametrize("has_metadata", [False, True])
@pytest.mark.parametrize("as_json", [False, True])
def test_unchecked_exposures_explain_coverage_without_inferring_runtime_from_metadata(
    project: Path,
    installed,
    capsys: pytest.CaptureFixture[str],
    exposure: str,
    message: str,
    has_metadata: bool,
    as_json: bool,
) -> None:
    manifest = project / "agnara.toml"
    manifest.write_text(MANIFEST.replace('["http", "mcp"]', f'["{exposure}"]'), encoding="utf-8")
    if has_metadata:
        installed[0][f"agnara-{exposure}"] = "1.0.3"
    arguments = ["doctor", "--project", str(project)]
    if as_json:
        arguments.append("--json")
    code = main(arguments)
    captured = capsys.readouterr()
    assert code == EXIT_FAILED
    assert captured.err == ""
    if as_json:
        document = json.loads(captured.out)
        assert document["format"] == "agnara.doctor" and document["format_version"] == 1
        assert document["status"] == "fail"
        assert checks(document)[f"exposure:{exposure}"] == {
            "id": f"exposure:{exposure}",
            "status": "fail",
            "message": message,
        }
    else:
        assert "doctor commerce: fail" in captured.out
        assert f"[fail] exposure:{exposure}: {message}" in captured.out
    assert f"agnara-{exposure}" not in installed[1]


@pytest.mark.parametrize("invalid", [None, "", "  "])
def test_missing_version_fields_cannot_pass_as_synchronized_metadata(
    project: Path, installed, capsys: pytest.CaptureFixture[str], invalid: str | None
) -> None:
    for distribution in installed[0]:
        installed[0][distribution] = invalid
    code, document = report(project, capsys)
    assert code == EXIT_FAILED and document["status"] == "fail"
    assert checks(document)["distribution:agnara"]["status"] == "fail"
    assert "non-empty version" in checks(document)["distribution:agnara"]["message"]


@pytest.mark.parametrize(
    "content", [None, b"not toml", b"\xff", b"[project]\nname='commerce'\nunknown=1"]
)
def test_missing_invalid_and_unreadable_encoding_manifests_are_reports(
    tmp_path: Path, installed, capsys: pytest.CaptureFixture[str], content: bytes | None
) -> None:
    if content is not None:
        (tmp_path / "agnara.toml").write_bytes(content)
    code, document = report(tmp_path, capsys)
    assert code == EXIT_FAILED and document["project"] is None
    assert checks(document)["manifest"]["status"] == "fail"
    assert {"declared_app_paths", "declared_adapters"} <= set(document["unchecked"])


def test_explicit_project_must_be_a_directory(
    project: Path, installed, capsys: pytest.CaptureFixture[str]
) -> None:
    code, document = report(project / "agnara.toml", capsys)
    assert code == EXIT_FAILED
    assert "not a directory" in checks(document)["manifest"]["message"]


def test_ancestor_search_and_default_working_directory(
    project: Path, installed, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = project / "src" / "commerce"
    assert report(nested, capsys)[0] == EXIT_OK
    monkeypatch.chdir(nested)
    assert main(["doctor", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["project"]["name"] == "commerce"


@pytest.mark.parametrize("as_file", [False, True])
def test_app_directory_must_exist_and_be_a_directory(
    project: Path, installed, capsys: pytest.CaptureFixture[str], as_file: bool
) -> None:
    path = project / "src" / "commerce" / "apps" / "users"
    path.rmdir()
    if as_file:
        path.write_text("not a directory", encoding="utf-8")
    code, document = report(project, capsys)
    assert code == EXIT_FAILED and checks(document)["app:users:path"]["status"] == "fail"


@pytest.mark.parametrize("problem", ["escape", "unresolvable"])
def test_resolved_paths_must_stay_inside_the_project(
    project: Path,
    installed,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    candidate = project / "src" / "commerce" / "apps" / "users"
    original = Path.resolve

    def resolve(path: Path, *args, **kwargs):
        if path == candidate:
            if problem == "unresolvable":
                raise OSError("fixture symlink loop")
            return project.parent
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    code, document = report(project, capsys)
    assert code == EXIT_FAILED
    check = checks(document)["app:users:path"]
    assert check["status"] == "fail"
    assert ("escapes" if problem == "escape" else "cannot resolve") in check["message"]


def test_interpreter_floor_is_independent_of_the_unparsed_project_constraint(
    project: Path, installed, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_doctor, "_python_version", lambda: (3, 13, 9))
    code, document = report(project, capsys)
    assert code == EXIT_FAILED and checks(document)["python"]["status"] == "fail"
    assert "project_python_constraint" in document["unchecked"]


def test_project_code_is_never_imported_and_files_are_unchanged(
    project: Path, installed, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = project / "unexpected-effect"
    package = project / "src" / "commerce" / "__init__.py"
    package.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "raise RuntimeError('imported')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert report(project, capsys)[0] == EXIT_OK
    assert not marker.exists()
    assert {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    } == before


def test_real_generated_project_and_app_pass_static_checks(
    tmp_path: Path, installed, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["project", "create", "commerce", "--directory", str(tmp_path)]) == EXIT_OK
    capsys.readouterr()
    project = tmp_path / "commerce"
    assert (
        main(["app", "create", "users", "--project", str(project), "--with", "http,mcp"]) == EXIT_OK
    )
    capsys.readouterr()
    code, document = report(project, capsys)
    assert code == EXIT_OK and checks(document)["app:users:path"]["status"] == "pass"


def test_argument_errors_keep_the_existing_usage_exit(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["doctor", "--repair"])
    assert error.value.code == EXIT_USAGE
    assert "unrecognized arguments" in capsys.readouterr().err


@pytest.mark.parametrize("unchecked_exposures", [False, True])
def test_fresh_interpreter_imports_no_application_or_adapter(
    project: Path, unchecked_exposures: bool
) -> None:
    if unchecked_exposures:
        (project / "agnara.toml").write_text(
            MANIFEST.replace('["http", "mcp"]', '["http", "mcp", "a2a", "events", "tasks"]'),
            encoding="utf-8",
        )
    script = """
import importlib.abc
import sys

class RefuseImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'commerce', 'agnara_http', 'agnara_mcp', 'agnara_a2a', 'agnara_events',
            'a2a', 'mcp',
        }:
            raise AssertionError(f'doctor attempted forbidden import: {fullname}')

sys.meta_path.insert(0, RefuseImports())
from agnara_cli import main
raise SystemExit(main(['doctor', '--project', sys.argv[1], '--json']))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(project)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    expected_exit = EXIT_FAILED if unchecked_exposures else EXIT_OK
    assert completed.returncode == expected_exit, completed.stderr
    document = json.loads(completed.stdout)
    assert document["status"] == ("fail" if unchecked_exposures else "pass")
    if unchecked_exposures:
        assert [check["id"] for check in document["checks"] if check["status"] == "fail"] == [
            "exposure:a2a",
            "exposure:events",
            "exposure:tasks",
        ]
