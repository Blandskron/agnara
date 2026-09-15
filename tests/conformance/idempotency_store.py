"""Reusable behavioral contract for ADR 0089 idempotency stores.

Third-party store suites can import :func:`assert_idempotency_store_conforms`
and pass a factory that accepts the supplied deterministic clock.  The port
does not prescribe a clock API for production stores; the factory boundary is
test-only so an implementation can connect its own controllable backend time.
"""

from __future__ import annotations

from collections.abc import Callable

from agnara.capability import CapabilityId
from agnara.execution.idempotency import (
    IdempotencyClaimed,
    IdempotencyCompleted,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyScope,
    IdempotencyStore,
)


class IdempotencyStoreClock:
    """A deterministic monotonic clock for the reusable store contract."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


IdempotencyStoreFactory = Callable[[IdempotencyStoreClock], IdempotencyStore]


def idempotency_scope(
    *,
    capability: str = "contracts.capture",
    principal: str = "principal-1",
    key: str = "key-1",
    fingerprint: bytes = b"request-a",
) -> IdempotencyScope:
    """Build one bounded selector for an implementation conformance test."""
    return IdempotencyScope(CapabilityId.parse(capability), principal, key, fingerprint)


async def assert_idempotency_store_conforms(factory: IdempotencyStoreFactory) -> None:
    """Assert the atomic state and exact expiry rules of ADR 0089.

    A TTL starts at the successful ``claim`` or ``complete`` operation.  A
    record is expired at its deadline (``expires_at <= clock``), so a stale
    reservation cannot complete or abandon a successor.  Implementations
    must provide the supplied clock to the backend or an equivalent test-time
    clock control.
    """
    clock = IdempotencyStoreClock()
    store = factory(clock)
    requested = idempotency_scope()

    first = await store.claim(requested, lease_ttl=5)
    assert isinstance(first, IdempotencyClaimed)
    duplicate = await store.claim(requested, lease_ttl=5)
    assert isinstance(duplicate, IdempotencyInProgress)
    assert duplicate.execution_id == first.reservation.execution_id

    clock.value = 4.999
    assert isinstance(await store.lookup(requested), IdempotencyInProgress)
    clock.value = 5
    assert await store.lookup(requested) is None
    assert not await store.complete(first.reservation, b"stale", result_ttl=5)
    assert not await store.abandon(first.reservation)

    replacement = await store.claim(requested, lease_ttl=5)
    assert isinstance(replacement, IdempotencyClaimed)
    assert replacement.reservation.execution_id != first.reservation.execution_id
    clock.value = 7
    assert await store.complete(replacement.reservation, b"success", result_ttl=5)

    clock.value = 11.999
    completed = await store.claim(requested, lease_ttl=5)
    assert isinstance(completed, IdempotencyCompleted)
    assert completed.execution_id == replacement.reservation.execution_id
    assert completed.result == b"success"
    clock.value = 12
    assert await store.lookup(requested) is None

    different_request = idempotency_scope(fingerprint=b"request-b")
    next_claim = await store.claim(requested, lease_ttl=5)
    assert isinstance(next_claim, IdempotencyClaimed)
    assert isinstance(await store.lookup(different_request), IdempotencyConflict)
    assert await store.abandon(next_claim.reservation)
