"""I1: HTTP and MCP compile through one model, and introspection reads it.

The unit tests in `tests/unit/test_exposure_model.py` exercise the kernel with
no adapter present. This module is the part that matters architecturally: two
adapters that were written independently, with different lifecycles and
different runtime artifacts, now produce the same neutral records from their
own compiled dispatch surfaces, and the snapshot is derived from those records
rather than told about them by hand.
"""

from __future__ import annotations

import json

import pytest

from agnara import Agnara
from agnara.capability import CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara.exposure import (
    ExposureError,
    ExposureId,
    FrozenExposureRegistry,
    SurfaceId,
    compile_exposures,
)
from agnara.introspection import (
    AllCapabilitiesVisible,
    DiscoveryField,
    DiscoveryVisibility,
    ExposureDescriptor,
    ScopeVisible,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara.policy import AnonymousPrincipal, Principal
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _HTTPExposure
from agnara_http._exposures import _compile_exposure_surface
from agnara_mcp import Mcp

REFUND = CapabilityId("billing", "refund")
STATEMENT = CapabilityId("billing", "statement")
HEALTH = CapabilityId("billing", "health")


@pytest.fixture
def app() -> Agnara:
    application = Agnara("billing")

    @application.capability(scopes={"billing:write"})
    def refund(payment_id: str) -> str:
        """Refund a captured payment."""
        return "refunded"

    @application.capability(scopes={"billing:read"})
    def statement(account_id: str) -> str:
        """Read an account statement."""
        return "statement"

    @application.capability
    def health() -> str:
        """Report service health."""
        return "ok"

    return application


def plans(app: Agnara) -> list[ExecutionPlan]:
    registry = DIRegistry()
    return [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]


def plan_for(app: Agnara, name: str) -> ExecutionPlan:
    return ExecutionPlan.compile(app.capabilities[name], DIRegistry())


def refund_exposure(app: Agnara, method: str = "POST", path: str = "/refunds") -> _HTTPExposure:
    return _HTTPExposure(
        method,
        path,
        plan_for(app, "billing.refund"),
        (_InputBinding("payment_id", _BindingSource.QUERY),),
    )


def http_surface(app: Agnara, *, surface: str = "default"):
    """Compile the HTTP surface the same way a composition root would."""
    return _compile_exposure_surface(
        [
            refund_exposure(app),
            _HTTPExposure(
                "GET",
                "/statements/{account_id}",
                plan_for(app, "billing.statement"),
                (_InputBinding("account_id", _BindingSource.PATH),),
            ),
        ],
        surface=surface,
    )


def mcp_surface(app: Agnara, *, surface: str = "default"):
    mcp = Mcp(app, surface=surface)
    mcp.tool(app.capabilities["billing.refund"])
    mcp.tool(app.capabilities["billing.health"], name="billing.health")
    return mcp.compile_surface()


# ---------------------------------------------------------------------------
# One model, two adapters
# ---------------------------------------------------------------------------


def test_one_capability_reaches_two_transports_through_one_registry(app: Agnara) -> None:
    exposures = compile_exposures(app.compile(), [http_surface(app), mcp_surface(app)])

    assert exposures.transports(REFUND) == ("http", "mcp")
    assert exposures.transports(STATEMENT) == ("http",)
    assert exposures.transports(HEALTH) == ("mcp",)
    assert exposures.surfaces == (SurfaceId("http", "default"), SurfaceId("mcp", "default"))


def test_each_adapter_derives_its_records_from_its_own_compiled_artifact(app: Agnara) -> None:
    """A record cannot describe a target the runtime does not hold, or vice versa."""
    http = http_surface(app)
    mcp = mcp_surface(app)

    routed = {(route.method, route.path_template) for route in http.runtime}
    recorded = {
        (json.loads(exposure.detail)["method"], json.loads(exposure.detail)["path"])
        for exposure in http.exposures
    }
    assert routed == recorded

    assert {exposure.name for exposure in mcp.runtime.exposures} == {
        exposure.id.name for exposure in mcp.exposures
    }


def test_a_record_names_the_capability_its_runtime_target_invokes(app: Agnara) -> None:
    http = http_surface(app)

    by_name = {exposure.id.name: exposure for exposure in http.exposures}
    for route in http.runtime:
        record = by_name[f"{route.method} {route.path_template}"]
        assert record.capability_id == route.target.plan.definition.id


def test_two_named_surfaces_of_one_adapter_coexist(app: Agnara) -> None:
    """A public and an admin HTTP deployment reuse paths without colliding."""
    frozen = app.compile()
    exposures = compile_exposures(
        frozen,
        [http_surface(app, surface="public"), http_surface(app, surface="admin")],
    )

    assert len(exposures) == 4
    assert exposures.surfaces == (SurfaceId("http", "public"), SurfaceId("http", "admin"))
    assert exposures.transports(REFUND) == ("http",)


def test_an_mcp_surface_carries_its_declared_name(app: Agnara) -> None:
    mcp = Mcp(app, surface="agents")

    assert mcp.surface == SurfaceId("mcp", "agents")
    assert mcp.compile_surface().surface == SurfaceId("mcp", "agents")


def test_mcp_compile_surface_is_consistent_with_compile(app: Agnara) -> None:
    """The pre-existing entry point and the new one describe one tool table."""
    mcp = Mcp(app, surface="agents")
    mcp.tool(app.capabilities["billing.refund"])

    compilation = mcp.compile_surface()

    assert compilation.runtime is mcp.compile()
    assert [exposure.id.name for exposure in compilation.exposures] == ["billing.refund"]


def test_registering_a_tool_after_the_surface_compiled_is_refused(app: Agnara) -> None:
    from agnara_mcp import McpToolDefinitionError

    mcp = Mcp(app)
    mcp.tool(app.capabilities["billing.refund"])
    mcp.compile_surface()

    with pytest.raises(McpToolDefinitionError, match="after MCP compilation"):
        mcp.tool(app.capabilities["billing.health"])


def test_a_wire_name_collision_inside_one_adapter_still_fails_in_the_adapter(
    app: Agnara,
) -> None:
    """Protocol grammar and collisions stay with the adapter that understands them."""
    from agnara_http._routing import _DuplicateRouteError

    with pytest.raises(_DuplicateRouteError):
        _compile_exposure_surface(
            [
                refund_exposure(app),
                _HTTPExposure(
                    "POST",
                    "/refunds",
                    plan_for(app, "billing.statement"),
                    (_InputBinding("account_id", _BindingSource.QUERY),),
                ),
            ]
        )


def test_two_adapters_may_use_the_same_local_name(app: Agnara) -> None:
    """`billing.refund` is a legal MCP tool name and a legal HTTP path; the
    full identities differ, so neither has to know about the other."""
    frozen = app.compile()
    http = _compile_exposure_surface([refund_exposure(app, path="/billing.refund")])
    exposures = compile_exposures(frozen, [http, mcp_surface(app)])

    assert exposures[ExposureId(SurfaceId("http", "default"), "POST /billing.refund")]
    assert exposures[ExposureId(SurfaceId("mcp", "default"), "billing.refund")]


# ---------------------------------------------------------------------------
# Introspection reflects compiled reality
# ---------------------------------------------------------------------------


def described(
    app: Agnara,
    exposures: FrozenExposureRegistry | None = None,
) -> dict[str, list[dict[str, object]]]:
    document = snapshot([describe_app(app, plans(app), exposures=exposures)]).json_data()
    return {
        capability["id"]: capability["exposures"]
        for capability in document["apps"][0]["capabilities"]
    }


def test_the_snapshot_derives_every_compiled_exposure(app: Agnara) -> None:
    exposures = compile_exposures(app.compile(), [http_surface(app), mcp_surface(app)])

    by_capability = described(app, exposures)

    assert [entry["name"] for entry in by_capability["billing.refund"]] == [
        "POST /refunds",
        "billing.refund",
    ]
    assert [entry["transport"] for entry in by_capability["billing.refund"]] == ["http", "mcp"]
    assert [entry["name"] for entry in by_capability["billing.health"]] == ["billing.health"]


def test_the_snapshot_reports_no_exposure_for_a_capability_exposed_nowhere(
    app: Agnara,
) -> None:
    exposures = compile_exposures(app.compile(), [mcp_surface(app)])

    assert described(app, exposures)["billing.statement"] == []


def test_surface_identity_survives_into_the_published_detail(app: Agnara) -> None:
    exposures = compile_exposures(app.compile(), [http_surface(app, surface="admin")])

    entry = described(app, exposures)["billing.refund"][0]

    assert entry["detail"] == {"method": "POST", "path": "/refunds", "surface": "admin"}


def test_a_project_wide_registry_can_describe_each_application_in_turn() -> None:
    """Another application's exposures are that application's to report."""
    billing = Agnara("billing")
    shipping = Agnara("shipping")

    @billing.capability
    def refund() -> str:
        return "refunded"

    @shipping.capability
    def dispatch() -> str:
        return "dispatched"

    combined = Agnara("project")
    billing_http = _compile_exposure_surface(
        [_HTTPExposure("POST", "/refunds", plan_for(billing, "billing.refund"))],
        surface="billing",
    )
    shipping_http = _compile_exposure_surface(
        [_HTTPExposure("POST", "/dispatch", plan_for(shipping, "shipping.dispatch"))],
        surface="shipping",
    )  # both capabilities take no inputs, so neither needs a binding
    del combined

    # One registry per project needs one frozen capability view per project,
    # so aggregate against each application that actually declared them.
    with pytest.raises(ExposureError, match="did not compile"):
        compile_exposures(billing.compile(), [billing_http, shipping_http])

    only_billing = compile_exposures(billing.compile(), [billing_http])
    assert described(billing, only_billing)["billing.refund"][0]["name"] == "POST /refunds"


def test_introspection_cannot_invent_an_exposure_the_runtime_did_not_compile(
    app: Agnara,
) -> None:
    """The handwritten mapping could; the registry structurally cannot."""
    exposures = compile_exposures(app.compile(), [])

    assert described(app, exposures) == {
        "billing.refund": [],
        "billing.statement": [],
        "billing.health": [],
    }


# ---------------------------------------------------------------------------
# Availability is not discovery, publication or authorization
# ---------------------------------------------------------------------------


def test_hiding_a_capability_from_a_viewer_leaves_availability_untouched(
    app: Agnara,
) -> None:
    exposures = compile_exposures(app.compile(), [http_surface(app), mcp_surface(app)])
    document = snapshot([describe_app(app, plans(app), exposures=exposures)])

    reader = filter_snapshot(
        document,
        DiscoveryVisibility(ScopeVisible(), (DiscoveryField.EXPOSURES,)),
        Principal("reader", scopes={"billing:read"}),
    )
    visible = {capability.id for capability in reader.apps[0].capabilities}

    assert "billing.refund" not in visible
    assert "billing.statement" in visible
    assert exposures.transports(REFUND) == ("http", "mcp")
    assert len(exposures) == 4


def test_filtering_one_viewer_does_not_change_what_another_sees(app: Agnara) -> None:
    exposures = compile_exposures(app.compile(), [http_surface(app), mcp_surface(app)])
    document = snapshot([describe_app(app, plans(app), exposures=exposures)])
    visibility = DiscoveryVisibility(ScopeVisible(), (DiscoveryField.EXPOSURES,))

    filter_snapshot(document, visibility, Principal("reader", scopes={"billing:read"}))
    writer = filter_snapshot(
        document,
        visibility,
        Principal("writer", scopes={"billing:read", "billing:write"}),
    )

    refund = next(item for item in writer.apps[0].capabilities if item.id == "billing.refund")
    assert [exposure.name for exposure in refund.exposures] == [
        "POST /refunds",
        "billing.refund",
    ]


def test_a_viewer_without_detail_does_not_learn_the_deployment_topology(
    app: Agnara,
) -> None:
    """Surface identity travels as detail, so redacting detail redacts topology."""
    exposures = compile_exposures(app.compile(), [http_surface(app, surface="admin")])
    document = snapshot([describe_app(app, plans(app), exposures=exposures)])

    def refund_exposures(
        published: tuple[DiscoveryField, ...],
    ) -> tuple[ExposureDescriptor, ...]:
        filtered = filter_snapshot(
            document,
            DiscoveryVisibility(AllCapabilitiesVisible(), published),
            AnonymousPrincipal(),
        )
        capability = next(
            item for item in filtered.apps[0].capabilities if item.id == "billing.refund"
        )
        return capability.exposures

    without_detail = refund_exposures((DiscoveryField.EXPOSURES,))
    with_detail = refund_exposures(
        (DiscoveryField.EXPOSURES, DiscoveryField.EXPOSURE_DETAIL),
    )

    assert without_detail[0].name == "POST /refunds"
    assert json.loads(without_detail[0].detail) == {}
    assert json.loads(with_detail[0].detail)["surface"] == "admin"


def test_the_registry_carries_nothing_that_could_invoke_a_capability(
    app: Agnara,
) -> None:
    exposures = compile_exposures(app.compile(), [http_surface(app), mcp_surface(app)])

    for exposure in exposures.values():
        assert not hasattr(exposure, "plan")
        assert not hasattr(exposure, "handler")
        assert not hasattr(exposure, "runtime")
        assert isinstance(json.loads(exposure.detail), dict)
