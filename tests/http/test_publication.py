"""Independent HTTP documentation-surface selection (E6.14)."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _compile_exposures, _HTTPExposure
from agnara_http._publication import (
    _compile_publication,
    _DocumentationUIRoute,
    _ExplorerRoute,
    _OpenAPIArtifact,
    _PublicationConfiguration,
    _PublicationDefinitionError,
    _SchemaRoute,
)

OPENAPI_BYTES = b'{"info":{"title":"API","version":"1"},"openapi":"3.2.0","paths":{}}'


def artifact() -> _OpenAPIArtifact:
    return _OpenAPIArtifact("3.2.0", OPENAPI_BYTES)


def capabilities(*exposures: _HTTPExposure):
    return _compile_exposures(exposures)


def ui(
    provider_name: str = "swagger",
    path: str = "/docs",
    *,
    try_it: bool = False,
) -> _DocumentationUIRoute:
    return _DocumentationUIRoute(
        provider_name,
        path,
        f"/{provider_name}-assets",
        f"{provider_name.title()} API",
        try_it,
    )


# --- independent selection ------------------------------------------------


def test_empty_configuration_produces_an_empty_plan_without_openapi() -> None:
    plan = _compile_publication(_PublicationConfiguration(), capabilities())

    assert plan.surfaces == ()
    assert plan.documentation == ()


def test_an_unused_openapi_artifact_does_not_publish_anything() -> None:
    plan = _compile_publication(_PublicationConfiguration(openapi=artifact()), capabilities())
    assert plan.surfaces == ()
    assert plan.documentation == ()


def test_schema_only_publishes_no_html_surface() -> None:
    plan = _compile_publication(
        _PublicationConfiguration(openapi=artifact(), schema=_SchemaRoute("/contract.json")),
        capabilities(),
    )

    assert [(item.name, item.path, item.body) for item in plan.surfaces] == [
        ("schema", "/contract.json", OPENAPI_BYTES)
    ]
    assert plan.documentation == ()


def test_explorer_only_does_not_depend_on_openapi() -> None:
    plan = _compile_publication(
        _PublicationConfiguration(explorer=_ExplorerRoute("/agnara", b"<main>Explorer</main>")),
        capabilities(),
    )

    assert [(item.name, item.path, item.body) for item in plan.surfaces] == [
        ("explorer", "/agnara", b"<main>Explorer</main>")
    ]
    assert plan.documentation == ()


def test_schema_uis_and_explorer_are_selected_independently() -> None:
    plan = _compile_publication(
        _PublicationConfiguration(
            openapi=artifact(),
            schema=_SchemaRoute("/schema"),
            documentation=(ui("swagger", "/docs"), ui("redoc", "/reference")),
            explorer=_ExplorerRoute("/agnara", b"explorer"),
        ),
        capabilities(),
    )

    assert [(item.name, item.path) for item in plan.surfaces] == [
        ("explorer", "/agnara"),
        ("schema", "/schema"),
    ]
    assert [(item.provider_name, item.path) for item in plan.documentation] == [
        ("redoc", "/reference"),
        ("swagger", "/docs"),
    ]


def test_disabling_one_ui_does_not_change_another_ui_request() -> None:
    swagger = ui("swagger", "/docs", try_it=True)
    redoc = ui("redoc", "/reference")
    together = _compile_publication(
        _PublicationConfiguration(openapi=artifact(), documentation=(swagger, redoc)),
        capabilities(),
    )
    swagger_only = _compile_publication(
        _PublicationConfiguration(openapi=artifact(), documentation=(swagger,)), capabilities()
    )

    selected_together = next(
        item for item in together.documentation if item.provider_name == "swagger"
    )
    assert selected_together == swagger_only.documentation[0]
    assert selected_together.request.try_it is True


def test_try_it_defaults_off_and_is_scoped_to_one_ui() -> None:
    plan = _compile_publication(
        _PublicationConfiguration(
            openapi=artifact(),
            documentation=(ui("swagger", try_it=True), ui("redoc", "/redoc")),
        ),
        capabilities(),
    )

    requests = {item.provider_name: item.request for item in plan.documentation}
    assert requests["swagger"].try_it is True
    assert requests["redoc"].try_it is False


def test_selection_uses_presence_not_a_global_boolean_bag() -> None:
    names = {field.name for field in dataclasses.fields(_PublicationConfiguration)}
    assert names == {"openapi", "schema", "documentation", "explorer"}
    assert "enabled" not in names
    assert "try_it" not in names


# --- truthful provider document source ------------------------------------


def test_ui_with_schema_receives_only_the_served_local_url() -> None:
    plan = _compile_publication(
        _PublicationConfiguration(
            openapi=artifact(),
            schema=_SchemaRoute("/schema.json"),
            documentation=(ui(),),
        ),
        capabilities(),
    )
    request = plan.documentation[0].request

    assert request.document_url == "/schema.json"
    assert request.document is None


def test_ui_without_schema_receives_only_the_serialized_document() -> None:
    plan = _compile_publication(
        _PublicationConfiguration(openapi=artifact(), documentation=(ui(),)), capabilities()
    )
    request = plan.documentation[0].request

    assert request.document_url is None
    assert request.document == OPENAPI_BYTES


@pytest.mark.parametrize(
    "configuration",
    [
        _PublicationConfiguration(schema=_SchemaRoute("/schema.json")),
        _PublicationConfiguration(documentation=(ui(),)),
    ],
)
def test_schema_and_ui_require_an_openapi_artifact(
    configuration: _PublicationConfiguration,
) -> None:
    with pytest.raises(_PublicationDefinitionError, match="require an OpenAPI artifact"):
        _compile_publication(configuration, capabilities())


# --- deterministic validation ---------------------------------------------


def test_ui_compilation_order_is_stable() -> None:
    declared = (ui("swagger", "/docs"), ui("redoc", "/reference"))
    first = _compile_publication(
        _PublicationConfiguration(openapi=artifact(), documentation=declared), capabilities()
    )
    second = _compile_publication(
        _PublicationConfiguration(openapi=artifact(), documentation=tuple(reversed(declared))),
        capabilities(),
    )

    assert first == second


def test_duplicate_provider_selection_fails_independently_of_order() -> None:
    declared = (ui("swagger", "/docs"), ui("swagger", "/other-docs"))
    messages = []
    for order in (declared, tuple(reversed(declared))):
        with pytest.raises(_PublicationDefinitionError, match="duplicate HTTP surface name") as e:
            _compile_publication(
                _PublicationConfiguration(openapi=artifact(), documentation=order), capabilities()
            )
        messages.append(str(e.value))
    assert messages[0] == messages[1]


def test_cross_surface_route_collision_fails_before_provider_rendering() -> None:
    with pytest.raises(_PublicationDefinitionError, match="both reserve '/shared'"):
        _compile_publication(
            _PublicationConfiguration(
                openapi=artifact(),
                schema=_SchemaRoute("/shared"),
                documentation=(ui("swagger", "/shared"),),
            ),
            capabilities(),
        )


def test_invalid_selected_surface_is_reported_at_the_publication_boundary() -> None:
    with pytest.raises(_PublicationDefinitionError, match="route path must start"):
        _compile_publication(
            _PublicationConfiguration(openapi=artifact(), schema=_SchemaRoute("schema.json")),
            capabilities(),
        )


def test_selected_route_collision_with_a_capability_is_refused() -> None:
    def handler(page: str) -> str:
        return page

    routes = capabilities(
        _HTTPExposure(
            "POST",
            "/docs/{page}",
            ExecutionPlan.compile(
                CapabilityDefinition(CapabilityId("publication", "page"), handler), DIRegistry()
            ),
            (_InputBinding("page", _BindingSource.PATH),),
        )
    )
    with pytest.raises(_PublicationDefinitionError, match="conflicts with capability"):
        _compile_publication(
            _PublicationConfiguration(
                openapi=artifact(), documentation=(ui("swagger", "/docs/current"),)
            ),
            routes,
        )


def test_literal_selected_route_collides_with_a_literal_capability() -> None:
    def handler() -> None:
        return None

    routes = capabilities(
        _HTTPExposure(
            "POST",
            "/docs",
            ExecutionPlan.compile(
                CapabilityDefinition(CapabilityId("publication", "docs"), handler), DIRegistry()
            ),
        )
    )
    with pytest.raises(_PublicationDefinitionError, match="conflicts with capability"):
        _compile_publication(
            _PublicationConfiguration(openapi=artifact(), documentation=(ui(),)), routes
        )


# --- declaration validation -----------------------------------------------


@pytest.mark.parametrize(
    ("version", "document", "message"),
    [
        ("", OPENAPI_BYTES, "version must be non-empty"),
        ("3.2.0", b"", "document must be non-empty bytes"),
        ("3.2.0", b"not json", "valid UTF-8 JSON"),
        ("3.2.0", '{"openapi":"3.2.0"}'.encode("utf-16"), "valid UTF-8 JSON"),
        ("3.2.0", b"[]", "must be a JSON object"),
        ("3.1.0", OPENAPI_BYTES, "declares '3.2.0', not '3.1.0'"),
        (" 3.2.0", OPENAPI_BYTES, "version must be non-empty"),
    ],
)
def test_openapi_artifact_is_self_consistent(version: str, document: bytes, message: str) -> None:
    with pytest.raises(_PublicationDefinitionError, match=re.escape(message)):
        _OpenAPIArtifact(version, document)


@pytest.mark.parametrize("provider_name", ["", "Swagger", "docs:swagger", "9provider"])
def test_ui_provider_name_uses_the_provider_contract(provider_name: str) -> None:
    with pytest.raises(_PublicationDefinitionError, match="invalid documentation provider name"):
        ui(provider_name)


def test_try_it_requires_a_real_boolean() -> None:
    with pytest.raises(_PublicationDefinitionError, match="try_it must be a boolean"):
        ui(try_it="yes")  # ty: ignore[invalid-argument-type]


def test_invalid_ui_request_is_reported_at_the_publication_boundary() -> None:
    invalid = _DocumentationUIRoute("swagger", "/docs", "assets", "Swagger API")
    with pytest.raises(_PublicationDefinitionError, match="same-origin absolute path"):
        _compile_publication(
            _PublicationConfiguration(openapi=artifact(), documentation=(invalid,)),
            capabilities(),
        )


def test_explorer_requires_complete_html_bytes() -> None:
    with pytest.raises(_PublicationDefinitionError, match="non-empty bytes"):
        _ExplorerRoute("/agnara", b"")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"openapi": object()}, "openapi must be"),
        ({"schema": object()}, "schema must be"),
        ({"documentation": [ui()]}, "documentation must be a tuple"),
        ({"documentation": (object(),)}, "documentation must be a tuple"),
        ({"explorer": object()}, "explorer must be"),
    ],
)
def test_configuration_rejects_wrong_component_types(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(_PublicationDefinitionError, match=message):
        _PublicationConfiguration(**kwargs)


def test_compiler_rejects_the_wrong_configuration_type() -> None:
    with pytest.raises(TypeError, match="configuration must be"):
        _compile_publication(object(), capabilities())  # ty: ignore[invalid-argument-type]
