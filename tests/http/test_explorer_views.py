"""E8.9: the Explorer's application, schema and dependency views.

Every property E8.8 established still has to hold — no script, no asset, the
strict policy, everything escaped — so the tests that add a view also check
that adding it did not open one of those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pytest

from agnara.introspection import (
    AppDescriptor,
    CapabilityDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    ExposureDescriptor,
    InputDescriptor,
    IntrospectionSnapshot,
    ProviderDescriptor,
    ScopeVisible,
    TypeReference,
    snapshot,
)
from agnara.policy import Principal
from agnara_http._dispatch import _compile_exposures
from agnara_http._explorer import _compile_explorer, _ExplorerDispatcher, _ExplorerRoute
from tests.http.test_explorer_shell import BASE, XSS, request

NESTED_SCHEMA = {
    "type": "object",
    "properties": {
        "amount_cents": {"type": "integer", "minimum": 0},
        "currency": {"type": "string", "enum": ["EUR", "USD"]},
    },
    "required": ["amount_cents"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class Surface:
    """One assembled Explorer and the snapshot behind it."""

    dispatcher: _ExplorerDispatcher
    document: IntrospectionSnapshot


def described(*, hostile: bool = False, providers: bool = True) -> IntrospectionSnapshot:
    """Build descriptors directly, so a schema shape is exactly what is tested."""
    schema = dict(NESTED_SCHEMA)
    if hostile:
        schema = {"type": "object", "title": XSS, "properties": {XSS: {"type": "string"}}}
    refund = CapabilityDescriptor(
        id="billing.refund",
        description="Refund a captured payment.",
        effects=("financial-write",),
        scopes=("billing:write",),
        risk="high",
        confirmation="never",
        idempotency="no",
        inputs=(
            InputDescriptor.of("payment_id", required=True, schema={"type": "string"}),
            InputDescriptor.of("command", required=False, schema=schema),
        ),
        dependencies=(),
        exposures=(ExposureDescriptor.of("http", "POST /refunds"),),
    )
    health = CapabilityDescriptor(id="billing.health", description="Report service health.")
    bound = (
        (
            ProviderDescriptor(
                TypeReference("Ledger" if not hostile else XSS),
                "invocation",
                "async_generator",
                (TypeReference("Audit"),),
            ),
            ProviderDescriptor(TypeReference("Audit"), "singleton", "sync_function"),
        )
        if providers
        else ()
    )
    return snapshot(
        [AppDescriptor("billing", (refund, health), bound)],
        project="billing",
    )


def surface(
    *,
    hostile: bool = False,
    providers: bool = True,
    visibility: DiscoveryVisibility | None = None,
) -> Surface:
    document = described(hostile=hostile, providers=providers)
    decision = (
        DiscoveryVisibility.unrestricted(ScopeVisible()) if visibility is None else visibility
    )

    async def fallback(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        raise AssertionError("the explorer subtree must not fall through")

    compiled = _compile_explorer(
        _ExplorerRoute(
            base_path=BASE,
            snapshot=document,
            visibility=decision,
            principals=lambda scope: Principal("viewer", scopes={"billing:write"}),
            challenge="Bearer",
        ),
        _compile_exposures(()),
    )
    return Surface(_ExplorerDispatcher(compiled, fallback), document)


# --- the application page --------------------------------------------------


def test_the_index_links_to_the_application_page() -> None:
    _, _, index = request(surface().dispatcher)

    assert f'<a href="{BASE}/app/billing">Application billing</a>' in index


def test_the_application_page_lists_its_capabilities_and_providers() -> None:
    status, _, body = request(surface().dispatcher, f"{BASE}/app/billing")

    assert status == 200
    assert "<h1>Application billing</h1>" in body
    assert f'<a href="{BASE}/billing.refund">billing.refund</a>' in body
    assert f'<a href="{BASE}/billing.health">billing.health</a>' in body
    assert "<h2>Providers</h2>" in body
    assert "<li>Ledger: invocation async_generator requires Audit</li>" in body
    assert "<li>Audit: singleton sync_function</li>" in body


def test_an_application_that_binds_nothing_says_so() -> None:
    _, _, body = request(surface(providers=False).dispatcher, f"{BASE}/app/billing")

    assert "This application binds no providers." in body


def test_the_provider_view_disappears_when_providers_are_withheld() -> None:
    withheld = DiscoveryVisibility(
        ScopeVisible(),
        tuple(field for field in DiscoveryField if field is not DiscoveryField.PROVIDERS),
    )

    _, _, body = request(surface(visibility=withheld).dispatcher, f"{BASE}/app/billing")

    assert "<h2>Providers</h2>" not in body
    assert "Ledger" not in body
    assert "Partial view." in body


def test_a_capability_page_links_back_to_its_application() -> None:
    _, _, body = request(surface().dispatcher, f"{BASE}/billing.refund")

    assert f'<a href="{BASE}/app/billing">Application billing</a>' in body
    assert f'<a href="{BASE}">Back to the index</a>' in body


def test_an_unknown_application_is_the_same_answer_as_a_hidden_one() -> None:
    served = surface().dispatcher

    absent = request(served, f"{BASE}/app/absent")
    nested = request(served, f"{BASE}/app/billing/extra")

    assert absent[0] == nested[0] == 404
    assert "billing" not in absent[2] or "no capability is visible" in absent[2]


def test_the_application_marker_cannot_shadow_a_capability_id() -> None:
    served = surface().dispatcher

    # One segment is always a capability id, so this is a capability lookup and
    # not a truncated application page.
    assert request(served, f"{BASE}/app")[0] == 404
    assert request(served, f"{BASE}/app/billing")[0] == 200


# --- the schema view -------------------------------------------------------


def test_an_input_schema_is_rendered_as_structure_not_as_a_blob() -> None:
    _, _, body = request(surface().dispatcher, f"{BASE}/billing.refund")

    assert "<li>payment_id (required)" in body
    assert "<li>type: string</li>" in body
    assert "<li>command (optional)" in body
    assert "<li>additionalProperties: false</li>" in body
    assert "<li>properties:<ul>" in body
    assert "<li>amount_cents:<ul>" in body
    assert "<li>minimum: 0</li>" in body
    assert "<li>enum:<ul>" in body
    assert "<li>0: EUR</li>" in body
    assert "<li>1: USD</li>" in body
    # Not a blob of escaped JSON.
    assert "{&quot;type&quot;" not in body


def test_schema_keys_render_in_a_deterministic_order() -> None:
    served = surface().dispatcher

    first = request(served, f"{BASE}/billing.refund")[2]
    second = request(served, f"{BASE}/billing.refund")[2]

    assert first == second
    assert first.index("<li>additionalProperties") < first.index("<li>properties:")


def test_the_schema_view_disappears_when_inputs_are_withheld() -> None:
    withheld = DiscoveryVisibility(
        ScopeVisible(),
        tuple(field for field in DiscoveryField if field is not DiscoveryField.INPUTS),
    )

    _, _, body = request(surface(visibility=withheld).dispatcher, f"{BASE}/billing.refund")

    assert "<h2>Inputs</h2>" not in body
    assert "amount_cents" not in body


def test_a_deep_schema_is_summarized_rather_than_unrolled_without_bound() -> None:
    deep: Any = {"type": "string"}
    for _ in range(30):
        deep = {"type": "object", "properties": {"next": deep}}
    descriptor = CapabilityDescriptor(
        id="billing.deep",
        inputs=(InputDescriptor.of("nested", required=True, schema=deep),),
    )
    document = snapshot([AppDescriptor("billing", (descriptor,))])

    async def fallback(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        raise AssertionError("unreachable")

    served = _ExplorerDispatcher(
        _compile_explorer(
            _ExplorerRoute(
                base_path=BASE,
                snapshot=document,
                visibility=DiscoveryVisibility.unrestricted(ScopeVisible()),
                principals=lambda scope: Principal("viewer"),
                challenge="Bearer",
            ),
            _compile_exposures(()),
        ),
        fallback,
    )

    status, _, body = request(served, f"{BASE}/billing.deep")

    assert status == 200
    assert "(nested further)" in body


# --- the properties E8.8 established still hold ----------------------------


@pytest.mark.parametrize("path", [f"{BASE}/app/billing", f"{BASE}/billing.refund"])
def test_a_schema_fragment_cannot_inject_markup(path: str) -> None:
    """The index carries neither schemas nor providers, so the payload reaches
    only the two pages that render them."""
    status, _, body = request(surface(hostile=True).dispatcher, path)

    assert status == 200
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_the_index_never_renders_a_schema_or_a_provider() -> None:
    _, _, body = request(surface(hostile=True).dispatcher, BASE)

    assert "<script>alert" not in body
    assert "amount_cents" not in body
    assert "async_generator" not in body


@pytest.mark.parametrize("path", [BASE, f"{BASE}/app/billing", f"{BASE}/billing.refund"])
def test_every_page_keeps_the_strict_policy_and_loads_nothing(path: str) -> None:
    _, headers, body = request(surface().dispatcher, path)

    assert headers[b"content-security-policy"] == (
        b"default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    for tag in ("<script", "<style", "<link", "<img", "<form", "<button", "<input"):
        assert tag not in body
    assert not re.search(r"\son[a-z]+=", body)


@pytest.mark.parametrize("path", [f"{BASE}/app/billing", f"{BASE}/billing.refund"])
def test_every_page_says_that_seeing_is_not_authorization(path: str) -> None:
    _, _, body = request(surface().dispatcher, path)

    assert "not permission to invoke it" in body
