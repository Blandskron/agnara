"""E8.7: ``agnara schema openapi`` exports a document it did not build."""

from __future__ import annotations

import ast
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main

MODULE = """
served = b\'{"info":{"title":"Billing API","version":"1"},"openapi":"3.2.0","paths":{}}\'
document = {
    "openapi": "3.2.0",
    "info": {"title": "Billing API", "version": "1"},
    "paths": {"/refunds": {"post": {"operationId": "billing.refund.post"}}},
}
unicode_document = {"openapi": "3.2.0", "info": {"title": "Caf\\u00e9", "version": "1"}}
not_json = b"\\xff\\xfe not json"
malformed = b"{not json"
not_an_object = b"[1, 2, 3]"
without_version = b'{"info":{"title":"x"}}'
numeric_version = b'{"openapi":3}'
wrong_type = 42
unserializable = {"openapi": "3.2.0", "extra": object()}


def build():
    return served


def explode():
    raise RuntimeError("projection failed on purpose")
"""


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "contract.py").write_text(MODULE, encoding="utf-8")
    yield tmp_path
    sys.modules.pop("contract", None)


def run(
    project: Path,
    attribute: str = "served",
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, bytes, str]:
    code = main(["schema", "openapi", f"contract:{attribute}", "--path", str(project), *arguments])
    captured = capsys.readouterr()
    return code, captured.out.encode("utf-8"), captured.err


def test_serialized_bytes_are_emitted_exactly_as_a_server_would_send_them(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(project, capsys=capsys)

    assert code == EXIT_OK
    assert err == ""
    assert out.rstrip(b"\n") == (
        b'{"info":{"title":"Billing API","version":"1"},"openapi":"3.2.0","paths":{}}'
    )


def test_a_mapping_is_serialized_the_way_the_http_projection_does(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(project, "document", capsys=capsys)
    body = out.rstrip(b"\n")

    assert code == EXIT_OK
    # Compact, key-sorted, UTF-8: the same shape `_serialize_openapi` produces.
    assert b", " not in body
    assert body.index(b'"info"') < body.index(b'"openapi"') < body.index(b'"paths"')
    assert json.loads(body)["openapi"] == "3.2.0"


def test_a_callable_target_is_invoked_once(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(project, "build", capsys=capsys)

    assert code == EXIT_OK
    assert json.loads(out)["info"]["title"] == "Billing API"


def test_non_ascii_survives_unescaped(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(project, "unicode_document", capsys=capsys)

    assert "Café".encode() in out
    assert b"\\u00e9" not in out


def test_pretty_output_says_it_is_no_longer_what_a_server_sends(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, plain, _ = run(project, "document", capsys=capsys)
    _, pretty, _ = run(project, "document", "--pretty", capsys=capsys)

    assert json.loads(plain) == json.loads(pretty)
    assert pretty != plain
    assert b"\n  " in pretty


def test_output_writes_a_file_and_prints_nothing(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "openapi.json"

    code, out, err = run(project, "served", "--output", str(destination), capsys=capsys)

    assert code == EXIT_OK
    assert out == b""
    assert err == ""
    assert destination.read_bytes() == (
        b'{"info":{"title":"Billing API","version":"1"},"openapi":"3.2.0","paths":{}}'
    )


def test_an_existing_file_is_not_replaced_without_authorization(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "openapi.json"
    destination.write_text("keep me", encoding="utf-8")

    code, _, err = run(project, "served", "--output", str(destination), capsys=capsys)

    assert code == EXIT_FAILED
    assert "pass --overwrite" in err
    assert destination.read_text(encoding="utf-8") == "keep me"


def test_overwrite_replaces_the_file(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "openapi.json"
    destination.write_text("replace me", encoding="utf-8")

    code, _, _ = run(project, "served", "--output", str(destination), "--overwrite", capsys=capsys)

    assert code == EXIT_OK
    assert json.loads(destination.read_bytes())["openapi"] == "3.2.0"


def test_an_unwritable_destination_is_a_diagnostic(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "somewhere"

    code, _, err = run(
        project, "served", "--output", str(directory / "nested" / "x.json"), capsys=capsys
    )

    assert code == EXIT_FAILED
    assert "cannot write" in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("not_json", "not valid UTF-8"),
        ("malformed", "not valid JSON"),
        ("not_an_object", "must be a JSON object"),
        ("without_version", "'openapi' version"),
        ("numeric_version", "'openapi' version"),
        ("wrong_type", "must be bytes, a mapping, or a callable"),
        ("unserializable", "cannot be serialized as JSON"),
    ],
)
def test_a_target_that_is_not_an_openapi_document_is_refused(
    project: Path, capsys: pytest.CaptureFixture[str], attribute: str, expected: str
) -> None:
    code, out, err = run(project, attribute, capsys=capsys)

    assert code == EXIT_FAILED
    assert out == b""
    assert expected in err
    assert "Traceback" not in err


def test_a_producer_that_raises_reports_the_reason(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(project, "explode", capsys=capsys)

    assert code == EXIT_FAILED
    assert "producing the OpenAPI document failed" in err
    assert "projection failed on purpose" in err
    assert "Traceback" not in err


def test_an_absent_attribute_is_refused(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project, "absent", capsys=capsys)

    assert code == EXIT_FAILED
    assert "defines no attribute 'absent'" in err


def test_a_format_must_be_named() -> None:
    with pytest.raises(SystemExit) as captured:
        main(["schema"])

    assert captured.value.code == EXIT_USAGE


def test_the_export_path_imports_no_adapter() -> None:
    """The whole design exists to keep this true.

    `tests/architecture` owns the package-wide rule; this checks the module
    that would be tempted to break it, where a reader of `_schema.py` will
    look for the reason it duplicates a serialization instead of importing it.
    """
    import agnara_cli._schema as schema

    source = ast.parse(Path(schema.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(source)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(source)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    foreign = {
        name
        for name in imported
        if name.split(".")[0].startswith("agnara")
        and name.split(".")[0] not in {"agnara", "agnara_cli"}
    }
    assert not foreign, sorted(foreign)
