import asyncio
from dataclasses import FrozenInstanceError

import pytest

from agnara import DefinitionError, ScopePolicy
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, Invocation
from agnara.policy import Policy, PolicyFailure, PolicySuccess, Principal


def context_for(principal: Principal | None = None) -> ExecutionContext:
    invocation = Invocation(CapabilityId("users", "read"), {}, {})
    return ExecutionContext(invocation, DIContainer(DIRegistry()), principal=principal)


def evaluate(policy: ScopePolicy, principal: Principal | None = None):
    return asyncio.run(policy.evaluate(context_for(principal)))


def test_scope_policy_satisfies_policy_protocol() -> None:
    assert isinstance(ScopePolicy(), Policy)


def test_scope_policy_copies_and_freezes_required_scopes() -> None:
    source = {"users:read"}
    policy = ScopePolicy(source)
    source.add("users:write")

    assert policy.required_scopes == frozenset({"users:read"})
    with pytest.raises(FrozenInstanceError):
        policy.required_scopes = frozenset()  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    "required",
    [(), {"users:read"}, {"users:read", "users:write"}],
)
def test_scope_policy_allows_when_all_required_scopes_are_granted(required) -> None:
    principal = Principal("user_123", scopes={"users:read", "users:write", "extra"})

    assert evaluate(ScopePolicy(required), principal) == PolicySuccess()


def test_scope_policy_denies_missing_scopes_deterministically() -> None:
    principal = Principal("user_123", scopes={"users:read"})

    assert evaluate(ScopePolicy({"users:write", "admin:read"}), principal) == PolicyFailure(
        reason="missing required scopes: admin:read, users:write"
    )


def test_scope_policy_fails_closed_for_anonymous_principal() -> None:
    assert evaluate(ScopePolicy({"users:read"})) == PolicyFailure(
        reason="missing required scopes: users:read"
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Principal("user_123", scopes="users:read"),
        lambda: Principal("user_123", scopes={"users:read", 1}),  # ty: ignore[invalid-argument-type]
        lambda: Principal("user_123", scopes={" "}),
        lambda: ScopePolicy("users:read"),
        lambda: ScopePolicy({"users:read", 1}),  # ty: ignore[invalid-argument-type]
        lambda: ScopePolicy({" "}),
    ],
)
def test_scope_labels_reject_invalid_declarations(factory) -> None:
    with pytest.raises(DefinitionError):
        factory()
