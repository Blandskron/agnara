"""E8.1: the protocol-neutral introspection snapshot and its builder."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, fields
from typing import Any

import pytest

from agnara import Agnara, CapabilityId, Confirmation, Risk, StandardEffect
from agnara.core.di import DIRegistry, Scope, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation
from agnara.introspection import (
    INTROSPECTION_FORMAT,
    INTROSPECTION_VERSION,
    AppDescriptor,
    CapabilityDescriptor,
    ExposureDescriptor,
    InputDescriptor,
    IntrospectionError,
    IntrospectionSnapshot,
    PolicyDescriptor,
    TypeReference,
    describe_app,
    snapshot,
)
from agnara.policy import ConfirmationEvidence, ConfirmationVerdict, Principal


class Ledger:
    """A dependency whose instance must never appear in a snapshot."""

    secret = "do-not-publish"


class Audit:
    """A second dependency, so provider ordering is observable."""


class Verifier:
    """Never consulted: the snapshot describes policies, it does not run them."""

    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id: CapabilityId,
        invocation: Invocation,
        principal: Principal,
    ) -> ConfirmationVerdict:
        raise AssertionError("introspection must not evaluate a policy")


def surface() -> tuple[Agnara, list[ExecutionPlan], DIRegistry]:
    app = Agnara("payments")
    registry = DIRegistry()

    @provider(scope=Scope.SINGLETON)
    def audit() -> Audit:
        return Audit()

    @provider(scope=Scope.INVOCATION)
    async def ledger(audit: Audit) -> AsyncIterator[Ledger]:
        yield Ledger()

    registry.bind(Audit, audit)
    registry.bind(Ledger, ledger)

    @app.capability(
        effects={StandardEffect.FINANCIAL_WRITE, "audit-write"},
        scopes={"payments:write", "payments:read"},
        risk=Risk.HIGH,
        confirmation=Confirmation.REQUIRED,
        idempotent=False,
    )
    def refund(payment_id: str, ledger: Ledger, amount_cents: int = 0) -> str:
        """Refund a captured payment."""
        return "refunded"

    @app.capability
    def ping(ctx: ExecutionContext) -> str:
        return "pong"

    plans = [
        ExecutionPlan.compile(
            app.capabilities[key],
            registry,
            confirmation_verifier=Verifier(),
        )
        for key in app.capabilities
    ]
    return app, plans, registry


def described() -> AppDescriptor:
    app, plans, registry = surface()
    return describe_app(
        app,
        plans,
        dependencies=registry,
        exposures={
            "payments.refund": [
                ExposureDescriptor.of("http", "POST /refunds", {"method": "POST"}),
                ExposureDescriptor.of("mcp", "payments.refund"),
            ]
        },
    )


def capability(app: AppDescriptor, identifier: str) -> CapabilityDescriptor:
    for descriptor in app.capabilities:
        if descriptor.id == identifier:
            return descriptor
    raise AssertionError(f"{identifier} is not described")


def test_a_capability_is_described_by_its_declared_metadata() -> None:
    refund = capability(described(), "payments.refund")

    assert refund.description == "Refund a captured payment."
    assert refund.effects == ("audit-write", "financial-write")
    assert refund.scopes == ("payments:read", "payments:write")
    assert refund.risk == "high"
    assert refund.confirmation == "required"
    assert refund.idempotency == "no"
    assert refund.policies == (PolicyDescriptor("ConfirmationPolicy"),)


def test_inputs_keep_signature_order_and_report_their_compiled_schema() -> None:
    refund = capability(described(), "payments.refund")

    assert [item.name for item in refund.inputs] == ["payment_id", "amount_cents"]
    assert [item.required for item in refund.inputs] == [True, False]
    assert json.loads(refund.inputs[0].schema) == {"type": "string"}


def test_runtime_owned_parameters_are_dependencies_or_absent_but_never_inputs() -> None:
    app = described()
    refund = capability(app, "payments.refund")
    ping = capability(app, "payments.ping")

    assert [item.parameter for item in refund.dependencies] == ["ledger"]
    assert refund.dependencies[0].type == TypeReference("Ledger", __name__)
    # An ExecutionContext parameter is neither an input nor a dependency: the
    # runtime supplies it, and it describes no relationship worth drawing.
    assert ping.inputs == ()
    assert ping.dependencies == ()


def test_the_provider_graph_is_described_without_any_callable_or_instance() -> None:
    app = described()

    assert [item.provides.name for item in app.providers] == ["Audit", "Ledger"]
    assert [item.scope for item in app.providers] == ["singleton", "invocation"]
    assert [item.kind for item in app.providers] == ["sync_function", "async_generator"]
    assert app.providers[0].requires == ()
    assert app.providers[1].requires == (TypeReference("Audit", __name__),)


def test_exposures_are_adapter_supplied_and_define_transport_availability() -> None:
    app = described()
    refund = capability(app, "payments.refund")

    assert [item.transport for item in refund.exposures] == ["http", "mcp"]
    assert json.loads(refund.exposures[0].detail) == {"method": "POST"}
    assert json.loads(refund.exposures[1].detail) == {}
    assert refund.transports == ("http", "mcp")
    assert capability(app, "payments.ping").transports == ()
    assert app.transports == ("http", "mcp")


def test_no_snapshot_value_reaches_a_runtime_object() -> None:
    document = json.dumps(snapshot([described()]).json_data())

    assert Ledger.secret not in document
    assert "handler" not in document
    # Slotted descriptors have no __dict__, so every field is enumerated from
    # the dataclass definition rather than from instance state.
    for descriptor in described().capabilities:
        for group in (descriptor.inputs, descriptor.dependencies, descriptor.policies):
            for item in group:
                for field in fields(item):
                    value = getattr(item, field.name)
                    assert isinstance(value, str | bool | tuple | TypeReference)


def test_descriptors_are_frozen_and_reject_unknown_attributes() -> None:
    app = described()

    with pytest.raises(FrozenInstanceError):
        app.name = "other"  # type: ignore
    with pytest.raises(FrozenInstanceError):
        app.capabilities[0].id = "other"  # type: ignore
    with pytest.raises(FrozenInstanceError):
        app.providers[0].scope = "other"  # type: ignore


def test_the_snapshot_is_versioned_and_deterministic() -> None:
    first = snapshot([described()], project="billing")
    second = snapshot([described()], project="billing")

    assert first.format == INTROSPECTION_FORMAT == "agnara-introspection"
    assert first.version == INTROSPECTION_VERSION == "0"
    assert first == second
    assert json.dumps(first.json_data(), sort_keys=True) == json.dumps(
        second.json_data(), sort_keys=True
    )
    document = first.json_data()
    assert document["project"] == "billing"
    assert document["transports"] == ["http", "mcp"]
    assert [app["name"] for app in document["apps"]] == ["payments"]


def test_a_standalone_application_says_so_instead_of_inventing_a_project() -> None:
    assert snapshot([described()]).json_data()["project"] is None


def test_json_data_reproduces_every_descriptor_field() -> None:
    document = snapshot([described()]).json_data()
    refund = next(
        item for item in document["apps"][0]["capabilities"] if item["id"] == "payments.refund"
    )

    assert set(refund) == {
        "id",
        "description",
        "effects",
        "scopes",
        "risk",
        "confirmation",
        "idempotency",
        "inputs",
        "dependencies",
        "policies",
        "exposures",
        "transports",
    }
    assert refund["inputs"][0] == {
        "name": "payment_id",
        "required": True,
        "schema": {"type": "string"},
    }
    assert refund["dependencies"] == [
        {"parameter": "ledger", "type": {"name": "Ledger", "module": __name__}}
    ]
    assert refund["policies"] == [{"kind": "ConfirmationPolicy"}]


def test_describing_an_uncompiled_capability_is_refused() -> None:
    app, plans, registry = surface()

    with pytest.raises(IntrospectionError, match="no execution plan"):
        describe_app(app, plans[:1], dependencies=registry)


def test_a_plan_for_another_capability_is_refused() -> None:
    app, plans, _ = surface()
    other = Agnara("payments")

    @other.capability
    def refund(payment_id: str) -> str:
        return "other"

    replacement = ExecutionPlan.compile(other.capabilities["payments.refund"], DIRegistry())

    with pytest.raises(IntrospectionError, match="does not retain"):
        describe_app(app, [replacement, *plans[1:]])


def test_an_exposure_naming_an_unknown_capability_is_refused() -> None:
    app, plans, _ = surface()

    with pytest.raises(IntrospectionError, match="unknown capability"):
        describe_app(app, plans, exposures={"payments.absent": [ExposureDescriptor("http", "/x")]})


def test_omitting_the_dependency_registry_omits_the_provider_graph() -> None:
    app, plans, _ = surface()
    without = describe_app(app, plans)

    assert without.providers == ()
    # The capability's own dependency is still named; only scope and
    # relationships are unavailable.
    assert [item.parameter for item in capability(without, "payments.refund").dependencies] == [
        "ledger"
    ]


@pytest.mark.parametrize(
    "detail",
    [object(), {1: "x"}, {"nested": {"value": object()}}, float("inf")],
)
def test_an_exposure_detail_that_is_not_json_is_refused(detail: Any) -> None:
    with pytest.raises(IntrospectionError):
        ExposureDescriptor.of("http", "/x", detail)


def test_deeply_nested_exposure_detail_is_refused() -> None:
    deep: Any = "leaf"
    for _ in range(70):
        deep = {"next": deep}

    with pytest.raises(IntrospectionError, match="nests deeper"):
        ExposureDescriptor.of("http", "/x", deep)


def test_supplied_detail_is_copied_rather_than_shared() -> None:
    mutable: dict[str, Any] = {"tags": ["a"]}
    exposure = ExposureDescriptor.of("http", "/x", mutable)
    mutable["tags"].append("b")
    mutable["added"] = True

    assert json.loads(exposure.detail) == {"tags": ["a"]}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk", "catastrophic"),
        ("confirmation", "maybe"),
        ("idempotency", "sometimes"),
        ("id", "not a capability id"),
    ],
)
def test_a_capability_descriptor_rejects_an_unknown_metadata_value(field: str, value: str) -> None:
    arguments: dict[str, Any] = {"id": "payments.refund", field: value}

    with pytest.raises(IntrospectionError):
        CapabilityDescriptor(**arguments)


def test_a_snapshot_rejects_repeated_apps_and_an_app_rejects_repeated_capabilities() -> None:
    app = described()

    with pytest.raises(IntrospectionError, match="repeats an app name"):
        IntrospectionSnapshot(apps=(app, app))
    with pytest.raises(IntrospectionError, match="repeats a capability id"):
        AppDescriptor("payments", (app.capabilities[0], app.capabilities[0]))


def test_descriptors_reject_values_of_the_wrong_type() -> None:
    with pytest.raises(IntrospectionError):
        AppDescriptor("payments", ("not a descriptor",))  # type: ignore
    with pytest.raises(IntrospectionError):
        IntrospectionSnapshot(apps=("not a descriptor",))  # type: ignore
    with pytest.raises(IntrospectionError):
        InputDescriptor("value", "yes", "{}")  # type: ignore
    with pytest.raises(IntrospectionError):
        describe_app("payments", [])  # type: ignore
    with pytest.raises(IntrospectionError):
        snapshot(["not a descriptor"])  # type: ignore
