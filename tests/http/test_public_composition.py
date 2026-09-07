"""The supported HTTP composition path, exercised as an application would.

Every import in this module is one an external application may write. Nothing
here reaches into `agnara_http._...`, which is the whole claim under test:
`tests/architecture/test_public_http_surface.py` enforces that mechanically,
and this module proves the public names are actually sufficient.

The internal-facing HTTP tests stay where they are. They test routing, binding
and projection in detail and are free to use private modules; this file tests
that an application never has to.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from agnara import Agnara, AgnaraError, DefinitionError, Risk, ScopePolicy
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan, TelemetryHook
from agnara.exposure import ExposureId, SurfaceId, compile_exposures
from agnara.introspection import describe_app, snapshot
from agnara_http import (
    Binding,
    BindingSource,
    Http,
    HttpApplication,
    HttpDefinitionError,
    OpenApiInfo,
    OpenApiOperation,
)

PUBLIC_NAMES = [
    "Binding",
    "BindingSource",
    "Http",
    "HttpApplication",
    "HttpDefinitionError",
    "OpenApiInfo",
    "OpenApiOperation",
]


@dataclass
class Order:
    """Issue #296: a dataclass-typed body cannot be filled from JSON yet."""

    sku: str


class Ledger:
    """Whatever the application really talks to."""

    def record(self, sku: str) -> str:
        return f"recorded {sku}"


@provider(scope=Scope.SINGLETON)
def provide_ledger() -> Ledger:
    return Ledger()


@pytest.fixture
def dependencies() -> DIRegistry:
    registry = DIRegistry()
    registry.bind(Ledger, provide_ledger)
    return registry


@pytest.fixture
def app() -> Agnara:
    application = Agnara("shop")

    @application.capability(description="Read one order.")
    def show(order_id: str, verbose: bool = False) -> dict[str, Any]:
        return {"id": order_id, "verbose": verbose}

    # `dict[str, Any]` rather than a dataclass: a dataclass-typed body cannot
    # succeed today, and Issue #296 records that as a framework defect instead
    # of it being worked around silently here.
    @application.capability(description="Create an order.")
    def create(order: dict[str, Any], ledger: Ledger) -> dict[str, Any]:
        return {"sku": order["sku"], "note": ledger.record(str(order["sku"]))}

    @application.capability(description="Archive every order.", risk=Risk.HIGH)
    def archive() -> None:
        return None

    def restricted() -> str:  # pragma: no cover - the policy denies it first
        return "secret"

    # A policy is attached by constructing the definition, because
    # `@app.capability` takes declarative metadata and not policy objects.
    application.capabilities.register(
        CapabilityDefinition(
            id=CapabilityId("shop", "restricted"),
            handler=restricted,
            description="Never allowed.",
            policies=(ScopePolicy(required_scopes={"shop:admin"}),),
        )
    )
    return application


def compose(app: Agnara, dependencies: DIRegistry, **kwargs: Any) -> HttpApplication:
    http = Http("public")
    http.get(
        "/orders/{order_id}",
        app.capabilities["shop.show"],
        Binding("order_id", BindingSource.PATH),
        Binding("verbose", BindingSource.QUERY),
        openapi=OpenApiOperation(
            summary="Show an order", publish_description=True, tags=("orders",)
        ),
    )
    http.post(
        "/orders",
        app.capabilities["shop.create"],
        Binding("order", BindingSource.BODY),
        openapi=OpenApiOperation(summary="Create an order", tags=("orders",)),
    )
    http.delete("/orders", app.capabilities["shop.archive"])
    http.get("/restricted", app.capabilities["shop.restricted"])
    return http.compile(app.compile(), dependencies=dependencies, **kwargs)


type Exchange = tuple[int, dict[bytes, bytes], bytes]


def request(
    asgi: HttpApplication,
    method: str,
    path: str,
    *,
    query: bytes = b"",
    body: bytes | None = None,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> Exchange:
    """Drive one request the way an ASGI server would."""
    events: list[dict[str, Any]] = []
    pending = [{"type": "http.request", "body": b"" if body is None else body, "more_body": False}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query,
        "headers": list(headers),
        "root_path": "",
    }
    asyncio.run(asgi(scope, receive, send))
    return (
        events[0]["status"],
        dict(events[0]["headers"]),
        b"".join(event.get("body", b"") for event in events[1:]),
    )


# ---------------------------------------------------------------------------
# The public surface itself
# ---------------------------------------------------------------------------


def test_the_package_exports_exactly_the_documented_names() -> None:
    """A new export must be a decision, not a side effect of an import."""
    import agnara_http

    assert agnara_http.__all__ == PUBLIC_NAMES


def test_every_exported_name_exists_and_is_public() -> None:
    import agnara_http

    for name in agnara_http.__all__:
        assert hasattr(agnara_http, name), name
        assert not name.startswith("_"), name


def test_the_composition_module_agrees_with_the_package() -> None:
    from agnara_http import composition

    assert composition.__all__ == PUBLIC_NAMES


# ---------------------------------------------------------------------------
# Minimal composition, and the request path
# ---------------------------------------------------------------------------


def test_the_smallest_useful_application_needs_four_public_names() -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)
    asgi = http.compile(application.compile())

    assert request(asgi, "GET", "/ping") == (
        200,
        {b"content-type": b"application/json; charset=utf-8", b"content-length": b"6"},
        b'"pong"',
    )


def test_a_capability_can_be_declared_by_callable_or_by_definition() -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    by_callable = Http("a")
    by_callable.get("/ping", ping)
    by_definition = Http("b")
    by_definition.get("/ping", application.capabilities["tiny.ping"])

    frozen = application.compile()
    assert request(by_callable.compile(frozen), "GET", "/ping")[0] == 200
    assert request(by_definition.compile(frozen), "GET", "/ping")[0] == 200


def test_a_get_path_binds_path_and_query_inputs(app: Agnara, dependencies: DIRegistry) -> None:
    asgi = compose(app, dependencies)

    status, headers, payload = request(asgi, "GET", "/orders/A1", query=b"verbose=true")

    assert status == 200
    assert headers[b"content-type"] == b"application/json; charset=utf-8"
    assert json.loads(payload) == {"id": "A1", "verbose": True}


def test_head_follows_from_get(app: Agnara, dependencies: DIRegistry) -> None:
    asgi = compose(app, dependencies)

    status, headers, payload = request(asgi, "HEAD", "/orders/A1")

    assert status == 200
    assert headers[b"content-length"] != b"0"
    assert payload == b""


def test_a_body_bearing_operation_resolves_its_dependencies(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies)

    status, _, payload = request(
        asgi,
        "POST",
        "/orders",
        body=json.dumps({"sku": "X", "quantity": 2}).encode("utf-8"),
        headers=((b"content-type", b"application/json"),),
    )

    assert status == 200
    assert json.loads(payload) == {"sku": "X", "note": "recorded X"}


def test_a_capability_returning_none_answers_204(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies)

    status, _, payload = request(asgi, "DELETE", "/orders")

    assert status == 204
    assert payload == b""


def test_an_unrouted_target_is_a_structured_problem(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies)

    status, headers, payload = request(asgi, "GET", "/missing")

    assert status == 404
    assert headers[b"content-type"] == b"application/problem+json"
    assert json.loads(payload)["code"] == "not_found"


def test_a_wrong_method_reports_the_allowed_ones(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies)

    status, headers, _ = request(asgi, "PATCH", "/orders")

    assert status == 405
    assert b"POST" in headers[b"allow"]
    assert b"DELETE" in headers[b"allow"]


def test_a_binding_failure_reports_where_the_value_came_from(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    """A transport-level decode failure names the request location."""
    asgi = compose(app, dependencies)

    status, headers, payload = request(asgi, "GET", "/orders/A1", query=b"verbose=maybe")

    assert status == 400
    assert headers[b"content-type"] == b"application/problem+json"
    problem = json.loads(payload)
    assert problem["code"] == "invalid_input"
    assert problem["details"]["location"] == "query.verbose"
    assert problem["instance"] == "/orders/A1"


def test_a_malformed_body_is_a_structured_problem(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies)

    status, _, payload = request(
        asgi,
        "POST",
        "/orders",
        body=b'{"sku": ',
        headers=((b"content-type", b"application/json"),),
    )

    problem = json.loads(payload)
    assert status == 400
    assert problem["code"] == "invalid_input"
    assert problem["details"]["location"] == "body"


def test_a_schema_validation_failure_reports_the_input_path(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    """A well-formed body of the wrong shape fails in the compiled schema."""
    asgi = compose(app, dependencies)

    status, headers, payload = request(
        asgi,
        "POST",
        "/orders",
        body=b'"not an object"',
        headers=((b"content-type", b"application/json"),),
    )

    assert status == 400
    assert headers[b"content-type"] == b"application/problem+json"
    problem = json.loads(payload)
    assert problem["code"] == "invalid_input"
    assert problem["details"]["path"] == ["order"]
    assert problem["title"] == "Invalid Input"


def test_a_policy_denial_maps_to_403(app: Agnara, dependencies: DIRegistry) -> None:
    """Every HTTP invocation is anonymous today, so a scope policy denies it."""
    asgi = compose(app, dependencies)

    status, headers, payload = request(asgi, "GET", "/restricted")

    assert status == 403
    assert headers[b"content-type"] == b"application/problem+json"
    problem = json.loads(payload)
    assert problem["code"] == "forbidden"
    assert problem["title"] == "Forbidden"


def test_a_problem_base_uri_replaces_about_blank(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies, problem_base_uri="https://errors.example/")

    _, _, payload = request(asgi, "GET", "/missing")

    assert json.loads(payload)["type"] == "https://errors.example/not-found"


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


def test_openapi_is_generated_from_the_compiled_surface(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies, openapi=OpenApiInfo("Shop API", "1.0.0"))

    document = asgi.openapi()

    assert document["openapi"] == "3.2.0"
    assert document["info"] == {"title": "Shop API", "version": "1.0.0"}
    assert sorted(document["paths"]) == ["/orders", "/orders/{order_id}"]
    operation = document["paths"]["/orders/{order_id}"]["get"]
    assert operation["summary"] == "Show an order"
    assert operation["description"] == "Read one order."
    assert operation["tags"] == ["orders"]


def test_an_undocumented_exposure_is_served_and_not_published(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    """ADR 0035: publication is per exposure and opt-in."""
    asgi = compose(app, dependencies, openapi=OpenApiInfo("Shop API", "1.0.0"))

    document = asgi.openapi()

    assert "delete" not in document["paths"]["/orders"]
    assert "/restricted" not in document["paths"]
    assert request(asgi, "DELETE", "/orders")[0] == 204


def test_openapi_generation_is_deterministic(app: Agnara, dependencies: DIRegistry) -> None:
    asgi = compose(app, dependencies, openapi=OpenApiInfo("Shop API", "1.0.0"))

    assert json.dumps(asgi.openapi(), sort_keys=True) == json.dumps(asgi.openapi(), sort_keys=True)


def test_the_document_can_be_served_at_a_chosen_path(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(
        app,
        dependencies,
        openapi=OpenApiInfo("Shop API", "1.0.0"),
        openapi_path="/openapi.json",
    )

    status, headers, payload = request(asgi, "GET", "/openapi.json")

    assert status == 200
    assert headers[b"content-type"] == b"application/json; charset=utf-8"
    assert headers[b"cache-control"] == b"no-store"
    assert json.loads(payload) == asgi.openapi()


def test_no_document_is_served_unless_a_path_is_chosen(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    """Publishing an API description is a deliberate act, so there is no default."""
    asgi = compose(app, dependencies, openapi=OpenApiInfo("Shop API", "1.0.0"))

    assert request(asgi, "GET", "/openapi.json")[0] == 404


def test_asking_for_openapi_without_info_says_what_to_pass(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    asgi = compose(app, dependencies)

    with pytest.raises(HttpDefinitionError, match="OpenApiInfo"):
        asgi.openapi()


def test_a_document_path_without_info_fails_at_compile(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    with pytest.raises(HttpDefinitionError, match="OpenApiInfo"):
        compose(app, dependencies, openapi_path="/openapi.json")


def test_a_document_route_cannot_shadow_a_capability(dependencies: DIRegistry) -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)

    with pytest.raises(HttpDefinitionError, match="conflicts with capability"):
        http.compile(
            application.compile(),
            openapi=OpenApiInfo("Tiny", "1.0"),
            openapi_path="/ping",
        )


# ---------------------------------------------------------------------------
# The error surface
# ---------------------------------------------------------------------------


def test_a_duplicate_route_fails_at_compile(dependencies: DIRegistry) -> None:
    application = Agnara("tiny")

    @application.capability
    def first() -> str:
        return "a"

    @application.capability
    def second() -> str:
        return "b"

    http = Http()
    http.get("/thing", first)
    http.get("/thing", second)

    with pytest.raises(HttpDefinitionError) as raised:
        http.compile(application.compile())
    assert "/thing" in str(raised.value)


def test_an_input_with_no_binding_names_the_input(dependencies: DIRegistry) -> None:
    application = Agnara("tiny")

    @application.capability
    def show(order_id: str) -> str:
        return order_id

    http = Http()
    http.get("/orders/{order_id}", show)

    with pytest.raises(HttpDefinitionError, match="order_id"):
        http.compile(application.compile())


def test_an_unsupported_binding_is_refused(dependencies: DIRegistry) -> None:
    """A non-scalar cannot arrive in a query string."""
    application = Agnara("tiny")

    @application.capability
    def create(order: dict[str, Any]) -> str:
        return "ok"

    http = Http()
    http.post("/orders", create, Binding("order", BindingSource.QUERY))

    with pytest.raises(HttpDefinitionError, match="scalar"):
        http.compile(application.compile())


def test_an_invalid_path_template_is_refused(dependencies: DIRegistry) -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("no-leading-slash", ping)

    with pytest.raises(HttpDefinitionError):
        http.compile(application.compile())


def test_declaring_a_route_after_compilation_is_refused(dependencies: DIRegistry) -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)
    http.compile(application.compile())

    assert http.is_compiled
    with pytest.raises(HttpDefinitionError, match="after 'http:default' compiled"):
        http.get("/late", ping)


def test_an_undeclared_capability_is_refused(dependencies: DIRegistry) -> None:
    application = Agnara("tiny")

    def stranger() -> str:
        return "who"

    http = Http()
    http.get("/stranger", stranger)

    with pytest.raises(DefinitionError, match="not a declared capability"):
        http.compile(application.compile())


def test_a_capability_from_another_application_is_refused() -> None:
    first = Agnara("first")
    second = Agnara("second")

    @second.capability
    def elsewhere() -> str:
        return "there"

    http = Http()
    http.get("/elsewhere", second.capabilities["second.elsewhere"])

    with pytest.raises(DefinitionError, match="not declared on the registry"):
        http.compile(first.compile())


def test_an_ambiguous_callable_asks_for_a_definition() -> None:
    application = Agnara("tiny")

    def shared() -> str:
        return "s"

    application.capability(name="first")(shared)
    application.capability(name="second")(shared)

    http = Http()
    http.get("/shared", shared)

    with pytest.raises(DefinitionError, match="several capabilities"):
        http.compile(application.compile())


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"method": "", "path": "/a"}, "method must be a non-empty string"),
        ({"method": "GET", "path": ""}, "path must be a non-empty string"),
    ],
)
def test_a_malformed_declaration_is_refused_immediately(
    kwargs: dict[str, str],
    match: str,
) -> None:
    with pytest.raises(HttpDefinitionError, match=match):
        Http().route(kwargs["method"], kwargs["path"], lambda: None)


def test_a_non_binding_argument_is_refused() -> None:
    with pytest.raises(HttpDefinitionError, match="must be a Binding"):
        Http().get("/a", lambda: None, "order_id")  # ty: ignore[invalid-argument-type]


def test_an_invalid_surface_name_is_refused() -> None:
    with pytest.raises(HttpDefinitionError, match="surface name"):
        Http("Public")


def test_compile_requires_the_frozen_registry() -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)

    with pytest.raises(HttpDefinitionError, match=r"Agnara\.compile"):
        http.compile(application.capabilities)  # ty: ignore[invalid-argument-type]


def test_every_composition_error_is_an_agnara_error() -> None:
    """An application catching `AgnaraError` already covers HTTP composition."""
    assert issubclass(HttpDefinitionError, DefinitionError)
    assert issubclass(HttpDefinitionError, AgnaraError)


def test_a_translated_error_keeps_the_adapter_diagnostic() -> None:
    """The private failure stays on __cause__ rather than being swallowed."""
    application = Agnara("tiny")

    @application.capability
    def show(order_id: str) -> str:
        return order_id

    http = Http()
    http.get("/orders/{order_id}", show)

    with pytest.raises(HttpDefinitionError) as raised:
        http.compile(application.compile())
    assert raised.value.__cause__ is not None


# ---------------------------------------------------------------------------
# Lifecycle ownership
# ---------------------------------------------------------------------------


def test_the_application_owns_startup_and_shutdown(dependencies: DIRegistry) -> None:
    events: list[str] = []
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    @asynccontextmanager
    async def lifecycle() -> AsyncIterator[None]:
        events.append("startup")
        try:
            yield
        finally:
            events.append("shutdown")

    http = Http()
    http.get("/ping", ping)
    asgi = http.compile(application.compile(), lifecycle=lifecycle)

    assert cycle(asgi) == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
    assert events == ["startup", "shutdown"]


def cycle(asgi: HttpApplication) -> list[str]:
    """Run one ASGI lifespan cycle and return the message types."""
    sent: list[str] = []
    pending = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message["type"])

    asyncio.run(asgi({"type": "lifespan"}, receive, send))
    return sent


def test_without_a_lifecycle_the_application_declares_no_lifespan() -> None:
    """Raising is how an ASGI application says it has no lifespan protocol."""
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)
    asgi = http.compile(application.compile())

    with pytest.raises(RuntimeError):
        cycle(asgi)


def test_two_surfaces_in_one_process_are_independent(dependencies: DIRegistry) -> None:
    """No module-level registry, so nothing is shared behind the caller's back."""
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    frozen = application.compile()
    public = Http("public")
    public.get("/ping", ping)
    admin = Http("admin")
    admin.get("/admin/ping", ping)

    first = public.compile(frozen)
    second = admin.compile(frozen)

    assert first.surface == SurfaceId("http", "public")
    assert second.surface == SurfaceId("http", "admin")
    assert request(first, "GET", "/ping")[0] == 200
    assert request(first, "GET", "/admin/ping")[0] == 404
    assert request(second, "GET", "/admin/ping")[0] == 200


def test_a_request_timeout_is_enforced() -> None:
    application = Agnara("tiny")

    @application.capability
    async def slow() -> str:
        await asyncio.sleep(1)
        return "late"

    http = Http()
    http.get("/slow", slow)
    asgi = http.compile(application.compile(), request_timeout=0.01)

    status, _, payload = request(asgi, "GET", "/slow")

    assert status == 504
    assert json.loads(payload)["code"] == "timeout"


def test_telemetry_hooks_reach_every_compiled_plan() -> None:
    observed: list[str] = []

    class Recorder:
        def on_invocation_start(self, event: Any) -> None:
            observed.append("start")

        def on_invocation_terminal(self, event: Any) -> None:
            observed.append("terminal")

    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)
    hook: TelemetryHook = Recorder()
    asgi = http.compile(application.compile(), hooks=(hook,))

    request(asgi, "GET", "/ping")

    assert observed == ["start", "terminal"]


# ---------------------------------------------------------------------------
# The exposure model, from public API only
# ---------------------------------------------------------------------------


def test_the_compiled_application_contributes_neutral_exposure_records(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    frozen = app.compile()
    http = Http("public")
    http.get(
        "/orders/{order_id}", app.capabilities["shop.show"], Binding("order_id", BindingSource.PATH)
    )
    asgi = http.compile(frozen, dependencies=dependencies)

    exposures = compile_exposures(frozen, [asgi.exposures])

    identity = ExposureId(SurfaceId("http", "public"), "GET /orders/{order_id}")
    assert list(exposures) == [identity]
    assert exposures[identity].capability_id == app.capabilities["shop.show"].id


def test_introspection_describes_the_compiled_surface(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    """`plans` exists so an application need not compile them a second time.

    `describe_app` needs a plan for every *declared* capability, and `plans`
    carries the ones this surface exposes. They coincide here because every
    capability is routed; an application with unexposed capabilities compiles
    those separately, which the composition guide states.
    """
    frozen = app.compile()
    asgi = compose(app, dependencies)
    exposures = compile_exposures(frozen, [asgi.exposures])

    document = snapshot(
        [describe_app(app, asgi.plans, exposures=exposures, dependencies=dependencies)]
    ).json_data()

    described = {
        capability["id"]: [entry["name"] for entry in capability["exposures"]]
        for capability in document["apps"][0]["capabilities"]
    }
    assert described["shop.show"] == ["GET /orders/{order_id}"]
    assert described["shop.create"] == ["POST /orders"]
    assert described["shop.archive"] == ["DELETE /orders"]


def test_plans_covers_the_capabilities_this_surface_exposes(
    app: Agnara,
    dependencies: DIRegistry,
) -> None:
    frozen = app.compile()
    http = Http("public")
    http.get(
        "/orders/{order_id}",
        app.capabilities["shop.show"],
        Binding("order_id", BindingSource.PATH),
    )
    asgi = http.compile(frozen, dependencies=dependencies)

    assert [str(plan.definition.id) for plan in asgi.plans] == ["shop.show"]


def test_two_routes_onto_one_capability_share_one_plan() -> None:
    """Introspection refuses two plans for one capability, so they must not exist."""
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)
    http.get("/health", ping)
    asgi = http.compile(application.compile())

    assert len(asgi.plans) == 1
    assert isinstance(asgi.plans[0], ExecutionPlan)
    assert request(asgi, "GET", "/ping")[0] == 200
    assert request(asgi, "GET", "/health")[0] == 200


def test_the_builder_reports_its_own_state() -> None:
    http = Http("public")

    assert repr(http) == "Http('public', 0 routes, open)"
    http.get("/a", lambda: None)
    assert len(http) == 1


def test_the_compiled_application_reports_its_surface_and_size() -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    http.get("/ping", ping)

    assert repr(http.compile(application.compile())) == "HttpApplication('http:default', 1 routes)"


def test_route_declarations_chain() -> None:
    application = Agnara("tiny")

    @application.capability
    def ping() -> str:
        return "pong"

    http = Http()
    returned = http.get("/a", ping).route("OPTIONS", "/b", ping)

    assert returned is http
    assert len(http) == 2


def test_binding_and_publication_values_are_readable() -> None:
    binding = Binding("account_id", BindingSource.HEADER, wire_name="x-account-id")
    operation = OpenApiOperation(summary="Read", tags=("a",), deprecated=True)
    info = OpenApiInfo("Title", "1.0", summary="s", description="d")

    assert binding.input_name == "account_id"
    assert binding.source is BindingSource.HEADER
    assert binding.wire_name == "x-account-id"
    assert "x-account-id" in repr(binding)
    assert operation.summary == "Read"
    assert operation.tags == ("a",)
    assert operation.deprecated is True
    assert operation.publish_description is False
    assert info.title == "Title"
    assert info.version == "1.0"
    assert info.summary == "s"
    assert info.description == "d"
    assert repr(info) == "OpenApiInfo('Title', '1.0')"
    assert "Read" in repr(operation)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"input_name": "", "source": BindingSource.PATH}, "input_name"),
        ({"input_name": "a", "source": "path"}, "BindingSource"),
    ],
)
def test_a_malformed_binding_is_refused(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(HttpDefinitionError, match=match):
        Binding(**kwargs)


def test_a_malformed_binding_wire_name_is_refused() -> None:
    with pytest.raises(HttpDefinitionError, match="wire_name"):
        Binding("a", BindingSource.PATH, wire_name="")


@pytest.mark.parametrize(
    "kwargs",
    [{"title": "", "version": "1.0"}, {"title": "T", "version": " "}],
)
def test_malformed_openapi_info_is_refused(kwargs: dict[str, str]) -> None:
    with pytest.raises(HttpDefinitionError, match="OpenAPI info"):
        OpenApiInfo(**kwargs)


def test_malformed_openapi_operation_is_refused() -> None:
    with pytest.raises(HttpDefinitionError, match="tags"):
        OpenApiOperation(tags=("dup", "dup"))


def test_a_wire_name_renames_an_input_without_the_capability_knowing() -> None:
    application = Agnara("tiny")

    @application.capability
    def show(account_id: str) -> str:
        return account_id

    http = Http()
    http.get("/me", show, Binding("account_id", BindingSource.HEADER, wire_name="x-account-id"))
    asgi = http.compile(application.compile())

    status, _, payload = request(asgi, "GET", "/me", headers=((b"x-account-id", b"A-7"),))

    assert status == 200
    assert json.loads(payload) == "A-7"


def test_a_body_limit_can_be_tightened_per_route() -> None:
    application = Agnara("tiny")

    @application.capability
    def create(order: dict[str, Any]) -> str:
        return "ok"

    http = Http()
    http.post("/orders", create, Binding("order", BindingSource.BODY), max_body_bytes=8)
    asgi = http.compile(application.compile())

    status, _, payload = request(
        asgi,
        "POST",
        "/orders",
        body=json.dumps({"sku": "much too long"}).encode("utf-8"),
        headers=((b"content-type", b"application/json"),),
    )

    assert status == 413
    assert json.loads(payload)["code"] == "content_too_large"


def test_a_dataclass_body_still_fails_and_the_defect_is_tracked() -> None:
    """Issue #296. Pinned so the fix is noticed here rather than in an application.

    A dataclass-typed input publishes a correct JSON Schema and then rejects
    every request that matches it, because the schema port validates without
    coercing. This is recorded as a framework defect rather than worked around,
    and the test documents current behaviour so changing it is deliberate.
    """
    application = Agnara("tiny")

    @application.capability
    def create(order: Order) -> str:  # pragma: no cover - never reached
        return order.sku

    http = Http()
    http.post(
        "/orders",
        create,
        Binding("order", BindingSource.BODY),
        openapi=OpenApiOperation(summary="Create"),
    )
    asgi = http.compile(application.compile(), openapi=OpenApiInfo("Tiny", "1.0"))

    # The published schema promises an object with a `sku` string...
    body_schema = asgi.openapi()["paths"]["/orders"]["post"]["requestBody"]
    assert body_schema["content"]["application/json"]["schema"]["type"] == "object"

    # ...and a request matching it is refused.
    status, _, payload = request(
        asgi,
        "POST",
        "/orders",
        body=b'{"sku": "X"}',
        headers=((b"content-type", b"application/json"),),
    )

    assert status == 400
    assert json.loads(payload)["detail"] == "expected Order, got dict"
