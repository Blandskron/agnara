"""Pinned OpenAPI structural fixtures for the projection (E6.11).

`test_openapi.py` checks the projection behaviour by behaviour. This module
checks the artefact: the whole document, pinned, plus the structural and
negative properties a behaviour test cannot express.

The negative ones matter most. The adapter has no authentication, so the
document declares no security. Asserting that here means the day
authentication ships without an OpenAPI update, this fails instead of the
framework quietly publishing an unsecured API.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agnara_http._dispatch import _compile_exposures
from agnara_http._openapi import _OPENAPI_VERSION, _project_openapi, _serialize_openapi
from tests.http.reference_application import (
    FIXTURE,
    INFO,
    document,
    exposures,
    routes,
    serialized,
)

REGENERATE = "uv run python -m tests.http.reference_application"

#: OpenAPI Objects the projection does not implement. Absent on purpose, not
#: by accident, and listed here so adding one is a deliberate act.
UNSUPPORTED_ROOT_FIELDS = (
    "servers",
    "webhooks",
    "externalDocs",
    "security",
    "tags",
)

#: Operation Object fields the projection does not implement.
UNSUPPORTED_OPERATION_FIELDS = ("servers", "security", "callbacks", "externalDocs")


def operations(doc: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, operation)
        for path, item in doc["paths"].items()
        for method, operation in item.items()
    ]


def refs(value: Any) -> list[str]:
    """Every `$ref` string anywhere in the document."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                found.append(item)
            else:
                found.extend(refs(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(refs(item))
    return found


def resolve(doc: dict[str, Any], ref: str) -> Any:
    assert ref.startswith("#/"), f"only local references are supported, got {ref!r}"
    node: Any = doc
    for segment in ref[2:].split("/"):
        assert isinstance(node, dict) and segment in node, f"dangling reference: {ref}"
        node = node[segment]
    return node


# --- the pinned document ---------------------------------------------------


def test_the_projected_document_matches_the_pinned_fixture() -> None:
    expected = FIXTURE.read_bytes()
    actual = serialized() + b"\n"

    if actual != expected:  # pragma: no cover - only on drift
        pytest.fail(
            "The OpenAPI projection changed.\n"
            "This document is what every client and documentation UI reads, so the "
            "change must be reviewed, not absorbed.\n"
            f"If it is intended, regenerate with:\n    {REGENERATE}\n\n"
            f"expected {len(expected)} bytes, produced {len(actual)} bytes\n"
            f"--- pinned ---\n{expected.decode('utf-8')}\n"
            f"--- produced ---\n{actual.decode('utf-8')}"
        )


def test_the_fixture_is_generated_output_rather_than_a_parallel_schema() -> None:
    # It must round-trip through the same serializer, so nobody can hand-edit
    # it into a second source of truth that merely looks right.
    pinned = json.loads(FIXTURE.read_bytes())
    assert _serialize_openapi(pinned) + b"\n" == FIXTURE.read_bytes()


def test_the_fixture_covers_every_projection_feature_the_adapter_implements() -> None:
    doc = json.loads(FIXTURE.read_bytes())

    assert "summary" in doc["info"]
    assert any("parameters" in operation for _, _, operation in operations(doc))
    assert any("requestBody" in operation for _, _, operation in operations(doc))
    assert any("tags" in operation for _, _, operation in operations(doc))
    assert any(operation.get("deprecated") for _, _, operation in operations(doc))
    assert any("description" in operation for _, _, operation in operations(doc))
    locations = {
        parameter["in"]
        for _, _, operation in operations(doc)
        for parameter in operation.get("parameters", [])
    }
    assert locations == {"path", "query", "header"}
    assert refs(doc), "the fixture should exercise a shared component reference"


# --- structure -------------------------------------------------------------


def test_the_document_declares_the_pinned_openapi_version_and_required_fields() -> None:
    doc = document()

    assert doc["openapi"] == _OPENAPI_VERSION
    assert set(doc["info"]) >= {"title", "version"}
    assert doc["info"]["title"] == INFO.title
    assert doc["info"]["version"] == INFO.version
    assert isinstance(doc["paths"], dict)


def test_every_reference_resolves_inside_the_document() -> None:
    doc = document()
    found = refs(doc)

    assert found, "the document should reference its shared Problem schema"
    for ref in found:
        assert resolve(doc, ref) is not None


def test_no_component_is_defined_without_being_referenced() -> None:
    doc = document()
    referenced = {ref.rsplit("/", 1)[-1] for ref in refs(doc)}
    defined = set(doc["components"]["schemas"])

    assert defined == referenced, (
        f"components defined but unused: {sorted(defined - referenced)}; "
        f"referenced but undefined: {sorted(referenced - defined)}"
    )


def test_path_templates_and_declared_path_parameters_agree() -> None:
    doc = document()
    for path, method, operation in operations(doc):
        in_template = {
            segment[1:-1]
            for segment in path.split("/")
            if segment.startswith("{") and segment.endswith("}")
        }
        declared = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter["in"] == "path"
        }
        assert declared == in_template, f"{method.upper()} {path}: {declared} != {in_template}"
        for parameter in operation.get("parameters", []):
            if parameter["in"] == "path":
                assert parameter["required"] is True, (
                    f"{method.upper()} {path}: path parameter {parameter['name']!r} is optional"
                )


def test_every_parameter_and_body_declares_a_schema() -> None:
    for path, method, operation in operations(document()):
        for parameter in operation.get("parameters", []):
            assert "schema" in parameter, f"{method.upper()} {path}: {parameter['name']} has none"
        body = operation.get("requestBody")
        if body is not None:
            assert "application/json" in body["content"]
            assert "schema" in body["content"]["application/json"]


def test_operation_ids_are_unique_and_stable_across_projections_and_order() -> None:
    first = [operation["operationId"] for _, _, operation in operations(document())]
    assert len(first) == len(set(first)), "operationId collision"

    again = [operation["operationId"] for _, _, operation in operations(document())]
    assert again == first

    reordered = _project_openapi(_compile_exposures(tuple(reversed(exposures()))), INFO)
    assert sorted(operation["operationId"] for _, _, operation in operations(reordered)) == sorted(
        first
    )


def test_serialization_is_deterministic_across_registration_order() -> None:
    # Order-independence is the property a pinned fixture depends on; without
    # it the fixture would drift on an unrelated refactor.
    reordered = _serialize_openapi(
        _project_openapi(_compile_exposures(tuple(reversed(exposures()))), INFO)
    )
    assert reordered == serialized()


# --- what the document does not claim --------------------------------------


def test_the_document_declares_no_security_because_there_is_no_authentication() -> None:
    # The adapter authenticates nobody and every invocation runs as the
    # anonymous principal. If authentication ships without updating the
    # projection, this fails rather than publishing an unsecured API as though
    # it were designed that way.
    doc = document()

    assert "security" not in doc
    assert "securitySchemes" not in doc.get("components", {})
    for path, method, operation in operations(doc):
        assert "security" not in operation, f"{method.upper()} {path} declares security"


@pytest.mark.parametrize("field", UNSUPPORTED_ROOT_FIELDS)
def test_the_document_does_not_claim_an_unimplemented_root_field(field: str) -> None:
    assert field not in document()


@pytest.mark.parametrize("field", UNSUPPORTED_OPERATION_FIELDS)
def test_no_operation_claims_an_unimplemented_field(field: str) -> None:
    for path, method, operation in operations(document()):
        assert field not in operation, f"{method.upper()} {path} claims {field!r}"


def test_the_document_only_uses_local_references() -> None:
    # A remote reference would make the document depend on a network fetch to
    # be understood, which the documentation asset policy forbids.
    for ref in refs(document()):
        assert ref.startswith("#/"), f"non-local reference: {ref}"


def test_an_unpublished_exposure_leaves_no_trace_in_the_pinned_document() -> None:
    doc = json.loads(FIXTURE.read_bytes())
    rendered = json.dumps(doc)

    # The reference application exposes it, and dispatch would serve it.
    assert any(exposure.path_template == "/internal/probe" for exposure in exposures())
    assert routes().match("GET", "/internal/probe") is not None

    assert "/internal/probe" not in doc["paths"]
    assert "internal_probe" not in rendered
    assert "Never published" not in rendered
