"""E8.2: what one viewer may see, decided before anything is serialized."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agnara import Agnara, Confirmation, Risk
from agnara.core.di import DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan
from agnara.introspection import (
    AllCapabilitiesVisible,
    CapabilityDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    ExposureDescriptor,
    Hiding,
    IntrospectionError,
    IntrospectionSnapshot,
    NoCapabilityVisible,
    ScopeVisible,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara.policy import AnonymousPrincipal, Principal


class Ledger:
    """A dependency whose type module is internal package structure."""


def built() -> IntrospectionSnapshot:
    app = Agnara("payments")
    registry = DIRegistry()

    @provider(scope=Scope.INVOCATION)
    def ledger() -> Ledger:
        return Ledger()

    registry.bind(Ledger, ledger)

    @app.capability(
        description="Refund a captured payment.",
        effects={"financial-write"},
        scopes={"payments:write"},
        risk=Risk.HIGH,
        confirmation=Confirmation.NEVER,
        idempotent=False,
    )
    def refund(payment_id: str, ledger: Ledger) -> str:
        return "refunded"

    @app.capability(description="Report service health.")
    def health() -> str:
        return "ok"

    @app.capability(description="Reconcile the internal ledger.")
    def reconcile() -> str:
        return "done"

    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]
    described = describe_app(
        app,
        plans,
        dependencies=registry,
        exposures={
            "payments.refund": [
                ExposureDescriptor.of("http", "POST /refunds", {"method": "POST"}),
            ],
            "payments.health": [ExposureDescriptor.of("http", "GET /health")],
        },
    )
    return snapshot([described], project="billing")


def visible_ids(document: IntrospectionSnapshot) -> list[str]:
    return [capability.id for app in document.apps for capability in app.capabilities]


def only(document: IntrospectionSnapshot, identifier: str) -> CapabilityDescriptor:
    for app in document.apps:
        for capability in app.capabilities:
            if capability.id == identifier:
                return capability
    raise AssertionError(f"{identifier} is not visible")


def test_scope_visibility_matches_the_rule_the_mcp_adapter_already_applies() -> None:
    visibility = DiscoveryVisibility.agent_safe(ScopeVisible())

    anonymous = filter_snapshot(built(), visibility, AnonymousPrincipal())
    authorized = filter_snapshot(built(), visibility, Principal("agent", scopes={"payments:write"}))

    assert visible_ids(anonymous) == ["payments.health", "payments.reconcile"]
    assert visible_ids(authorized) == [
        "payments.refund",
        "payments.health",
        "payments.reconcile",
    ]


def test_hiding_composes_with_a_rule_without_becoming_authorization() -> None:
    visibility = DiscoveryVisibility.agent_safe(Hiding({"payments.reconcile"}, ScopeVisible()))

    document = filter_snapshot(built(), visibility, Principal("agent", scopes={"payments:write"}))

    assert visible_ids(document) == ["payments.refund", "payments.health"]
    # The hidden capability is still registered and still compiled; hiding it
    # from discovery changed nothing about whether it can be invoked.
    assert "payments.reconcile" in visible_ids(
        filter_snapshot(
            built(), DiscoveryVisibility.agent_safe(AllCapabilitiesVisible()), AnonymousPrincipal()
        )
    )


def test_a_surface_can_be_turned_off_without_removing_it() -> None:
    document = filter_snapshot(
        built(),
        DiscoveryVisibility.unrestricted(NoCapabilityVisible()),
        Principal("agent", scopes={"payments:write"}),
    )

    assert document.apps == ()
    # An application name is itself a disclosure, so nothing survives.
    assert document.json_data()["apps"] == []
    assert document.json_data()["project"] is None
    assert document.filtered is True


def test_identity_only_publishes_that_a_capability_exists_and_nothing_more() -> None:
    document = filter_snapshot(
        built(), DiscoveryVisibility.identity_only(AllCapabilitiesVisible()), AnonymousPrincipal()
    )
    refund = only(document, "payments.refund")

    assert refund.description is None
    assert refund.effects == ()
    assert refund.scopes == ()
    assert refund.risk == "low"
    assert refund.confirmation == "never"
    assert refund.idempotency == "unknown"
    assert refund.inputs == ()
    assert refund.dependencies == ()
    assert refund.policies == ()
    assert refund.exposures == ()
    assert refund.transports == ()
    assert document.apps[0].providers == ()


def test_agent_safe_publishes_what_a_caller_needs_and_no_implementation_detail() -> None:
    document = filter_snapshot(
        built(), DiscoveryVisibility.agent_safe(AllCapabilitiesVisible()), AnonymousPrincipal()
    )
    refund = only(document, "payments.refund")

    assert refund.description == "Refund a captured payment."
    assert refund.effects == ("financial-write",)
    assert refund.scopes == ("payments:write",)
    assert refund.risk == "high"
    assert refund.idempotency == "no"
    assert [item.name for item in refund.inputs] == ["payment_id"]
    assert [item.name for item in refund.exposures] == ["POST /refunds"]
    # Implementation detail stays unpublished.
    assert refund.dependencies == ()
    assert refund.policies == ()
    assert document.apps[0].providers == ()
    assert json.loads(refund.exposures[0].detail) == {}


def test_unrestricted_publishes_every_field() -> None:
    document = filter_snapshot(
        built(), DiscoveryVisibility.unrestricted(AllCapabilitiesVisible()), AnonymousPrincipal()
    )
    refund = only(document, "payments.refund")

    assert [item.parameter for item in refund.dependencies] == ["ledger"]
    assert refund.dependencies[0].type.module == __name__
    assert json.loads(refund.exposures[0].detail) == {"method": "POST"}
    assert [item.provides.name for item in document.apps[0].providers] == ["Ledger"]
    assert document.apps[0].providers[0].requires == ()


def test_type_modules_are_a_separate_decision_from_dependencies() -> None:
    visibility = DiscoveryVisibility(
        AllCapabilitiesVisible(),
        (DiscoveryField.DEPENDENCIES, DiscoveryField.PROVIDERS),
    )

    document = filter_snapshot(built(), visibility, AnonymousPrincipal())
    refund = only(document, "payments.refund")

    assert [item.parameter for item in refund.dependencies] == ["ledger"]
    assert refund.dependencies[0].type.name == "Ledger"
    assert refund.dependencies[0].type.module is None
    assert document.apps[0].providers[0].provides.module is None
    assert __name__ not in json.dumps(document.json_data())


def test_exposure_detail_is_a_separate_decision_from_exposures() -> None:
    visibility = DiscoveryVisibility(AllCapabilitiesVisible(), (DiscoveryField.EXPOSURES,))

    refund = only(filter_snapshot(built(), visibility, AnonymousPrincipal()), "payments.refund")

    assert [item.name for item in refund.exposures] == ["POST /refunds"]
    assert json.loads(refund.exposures[0].detail) == {}
    assert refund.transports == ("http",)


def test_hiding_exposures_also_hides_derived_transport_availability() -> None:
    document = filter_snapshot(
        built(), DiscoveryVisibility.identity_only(AllCapabilitiesVisible()), AnonymousPrincipal()
    )

    # Transport availability *is* the exposure list in this model, so it
    # cannot describe a transport the viewer was never shown.
    assert document.transports == ()
    assert document.apps[0].transports == ()


def test_an_unpublished_field_is_absent_rather_than_emptied_misleadingly() -> None:
    published = filter_snapshot(
        built(), DiscoveryVisibility.agent_safe(AllCapabilitiesVisible()), AnonymousPrincipal()
    )
    withheld = filter_snapshot(
        built(), DiscoveryVisibility.identity_only(AllCapabilitiesVisible()), AnonymousPrincipal()
    )

    # health genuinely declares no effects; refund declares one that is
    # withheld. Both read as "no effects published", which is why a consumer
    # must be told the snapshot was filtered.
    assert only(published, "payments.health").effects == ()
    assert only(withheld, "payments.refund").effects == ()
    assert withheld.filtered is True
    assert withheld.json_data()["filtered"] is True


def test_a_built_snapshot_is_not_marked_filtered() -> None:
    document = built()

    assert document.filtered is False
    assert document.json_data()["filtered"] is False


def test_filtering_leaves_the_source_snapshot_untouched() -> None:
    source = built()
    before = json.dumps(source.json_data(), sort_keys=True)

    filter_snapshot(
        source, DiscoveryVisibility.identity_only(NoCapabilityVisible()), AnonymousPrincipal()
    )

    assert json.dumps(source.json_data(), sort_keys=True) == before


def test_one_visibility_serves_concurrent_viewers_without_sharing_a_result() -> None:
    visibility = DiscoveryVisibility.agent_safe(ScopeVisible())
    source = built()

    first = filter_snapshot(source, visibility, AnonymousPrincipal())
    second = filter_snapshot(source, visibility, Principal("agent", scopes={"payments:write"}))
    third = filter_snapshot(source, visibility, AnonymousPrincipal())

    assert visible_ids(first) == visible_ids(third)
    assert "payments.refund" not in visible_ids(first)
    assert "payments.refund" in visible_ids(second)


def test_the_publication_decision_has_no_default() -> None:
    with pytest.raises(TypeError):
        DiscoveryVisibility(AllCapabilitiesVisible())  # type: ignore


@pytest.mark.parametrize(
    ("rule", "published"),
    [
        ("not a rule", ()),
        (AllCapabilitiesVisible(), "description"),
        (AllCapabilitiesVisible(), ("not-a-field",)),
    ],
)
def test_an_invalid_visibility_decision_is_refused(rule: Any, published: Any) -> None:
    with pytest.raises(IntrospectionError):
        DiscoveryVisibility(rule, published)


def test_hiding_refuses_an_invalid_rule_or_identifier() -> None:
    with pytest.raises(IntrospectionError):
        Hiding({"payments.refund"}, "not a rule")  # type: ignore
    with pytest.raises(IntrospectionError):
        Hiding({""}, AllCapabilitiesVisible())


@pytest.mark.parametrize(
    ("document", "visibility", "principal"),
    [
        ("not a snapshot", DiscoveryVisibility.identity_only(ScopeVisible()), AnonymousPrincipal()),
        (IntrospectionSnapshot(), "not a visibility", AnonymousPrincipal()),
        (IntrospectionSnapshot(), DiscoveryVisibility.identity_only(ScopeVisible()), "anonymous"),
    ],
)
def test_filtering_refuses_arguments_of_the_wrong_type(
    document: Any, visibility: Any, principal: Any
) -> None:
    with pytest.raises(IntrospectionError):
        filter_snapshot(document, visibility, principal)


def test_every_published_field_is_reachable_through_a_named_decision() -> None:
    """No field may be publishable only by accident of another one."""
    unrestricted = DiscoveryVisibility.unrestricted(AllCapabilitiesVisible())

    assert unrestricted.published == frozenset(DiscoveryField)
    assert DiscoveryVisibility.identity_only(AllCapabilitiesVisible()).published == frozenset()
    for field in DiscoveryField:
        single = DiscoveryVisibility(AllCapabilitiesVisible(), (field,))
        assert single.publishes(field)
        assert not any(single.publishes(other) for other in DiscoveryField if other is not field)
