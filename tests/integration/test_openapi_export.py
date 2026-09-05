"""``agnara schema openapi`` exports exactly what ``agnara-http`` would serve.

The CLI must not import an adapter, so it duplicates the projection's
serialization arguments instead. A duplicated constant is a promise; this is
the test that keeps it one. The composition module here does what a real one
does — it imports `agnara-http`, projects, and exposes the result — while the
CLI stays on the other side of the package boundary.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agnara_cli import EXIT_OK, main

COMPOSITION = """
from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _compile_exposures, _HTTPExposure, _OpenAPIPublication
from agnara_http._openapi import _OpenAPIInfo, _project_openapi, _serialize_openapi

app = Agnara("billing")


@app.capability(description="Refund a captured payment.")
def refund(payment_id: str) -> str:
    return "refunded"


@app.capability(description="Report service health.")
def health() -> str:
    return "ok"


registry = DIRegistry()
routes = _compile_exposures(
    [
        _HTTPExposure(
            "POST",
            "/refunds/{payment_id}",
            ExecutionPlan.compile(app.capabilities["billing.refund"], registry),
            bindings=(_InputBinding("payment_id", _BindingSource.PATH),),
            openapi=_OpenAPIPublication(summary="Refund", publish_description=True),
        ),
        _HTTPExposure(
            "GET",
            "/health",
            ExecutionPlan.compile(app.capabilities["billing.health"], registry),
            openapi=_OpenAPIPublication(summary="Health"),
        ),
    ]
)

document = _project_openapi(routes, _OpenAPIInfo("Billing API", "2026-09-05"))
served = _serialize_openapi(document)


def build():
    return served
"""


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "composition.py").write_text(COMPOSITION, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("composition", None)


def exported(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    attribute: str,
    *arguments: str,
) -> bytes:
    code = main(
        [
            "schema",
            "openapi",
            f"composition:{attribute}",
            "--path",
            str(project),
            *arguments,
        ]
    )
    assert code == EXIT_OK
    return capsys.readouterr().out.encode("utf-8")


def composition() -> Any:
    return importlib.import_module("composition")


def test_the_export_is_byte_identical_to_what_the_http_surface_serves(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    served = composition().served

    assert exported(project, capsys, "served") == served
    assert exported(project, capsys, "build") == served


def test_projecting_the_mapping_in_the_cli_reproduces_the_adapter_bytes(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The duplicated serialization arguments are kept honest here.

    The CLI serializes the mapping itself; `agnara-http` serialized the same
    mapping with its own arguments. Equal bytes is the only evidence that the
    duplication has not drifted.
    """
    served = composition().served

    assert exported(project, capsys, "document") == served


def test_the_exported_document_describes_the_compiled_exposures(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = json.loads(exported(project, capsys, "served"))

    assert document["openapi"].startswith("3.2")
    assert sorted(document["paths"]) == ["/health", "/refunds/{payment_id}"]
    assert "post" in document["paths"]["/refunds/{payment_id}"]
    assert "get" in document["paths"]["/health"]
    # An unpublished description stays unpublished, exactly as the projection
    # decided; the CLI re-decides nothing.
    refund = document["paths"]["/refunds/{payment_id}"]["post"]
    assert refund["description"] == "Refund a captured payment."
    assert "description" not in document["paths"]["/health"]["get"]


def test_writing_to_a_file_stores_the_same_bytes(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "openapi.json"

    assert (
        main(
            [
                "schema",
                "openapi",
                "composition:served",
                "--path",
                str(project),
                "--output",
                str(destination),
            ]
        )
        == EXIT_OK
    )
    assert capsys.readouterr().out == ""
    assert destination.read_bytes() == composition().served


def test_pretty_output_is_the_same_document_and_not_the_same_bytes(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    served = composition().served
    pretty = exported(project, capsys, "served", "--pretty")

    assert pretty != served
    assert json.loads(pretty) == json.loads(served)
