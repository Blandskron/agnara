"""Reusable behavioral contract for transport-neutral idempotency stores."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from agnara.capability import CapabilityId
from agnara.execution.idempotency import (
    IdempotencyClaimed,
    IdempotencyCompleted,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyScope,
    IdempotencyStorageError,
    IdempotencyStore,
)


class ControlledClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


StoreFactory = Callable[[ControlledClock, int], IdempotencyStore]


def make_scope(
    *,
    capability: str = "payments.capture",
    principal: str = "customer-1",
    key: str = "payment-1",
    fingerprint: bytes = b"request-a",
) -> IdempotencyScope:
    return IdempotencyScope(CapabilityId.parse(capability), principal, key, fingerprint)


async def assert_idempotency_store_conforms(factory: StoreFactory) -> None:
    """Run the provider-independent ADR 0089 contract against one store.

    Providers supply a store factory that accepts a controlled clock and
    capacity. The factory is the only provider-specific fixture required.
    """
    clock = ControlledClock()
    store = factory(clock, 128)
    requested = make_scope()

    first = await store.claim(requested, lease_ttl=5)
    assert isinstance(first, IdempotencyClaimed)
    duplicate = await store.claim(requested, lease_ttl=5)
    assert isinstance(duplicate, IdempotencyInProgress)
    assert duplicate.execution_id == first.reservation.execution_id

    conflict = await store.claim(make_scope(fingerprint=b"request-b"), lease_ttl=5)
    assert isinstance(conflict, IdempotencyConflict)
    assert repr(conflict) == "IdempotencyConflict()"

    assert await store.complete(first.reservation, b"opaque-success", result_ttl=5)
    completed = await store.claim(requested, lease_ttl=5)
    assert isinstance(completed, IdempotencyCompleted)
    assert completed.result == b"opaque-success"
    assert await store.lookup(requested) == completed

    boundary = await store.claim(make_scope(key="boundary"), lease_ttl=5)
    assert isinstance(boundary, IdempotencyClaimed)
    clock.value = 4.999
    assert isinstance(
        await store.claim(make_scope(key="boundary"), lease_ttl=5), IdempotencyInProgress
    )
    clock.value = 5
    boundary_replacement = await store.claim(make_scope(key="boundary"), lease_ttl=5)
    assert isinstance(boundary_replacement, IdempotencyClaimed)
    assert await store.complete(boundary_replacement.reservation, b"boundary", result_ttl=5)
    clock.value = 9.999
    assert isinstance(
        await store.claim(make_scope(key="boundary"), lease_ttl=5), IdempotencyCompleted
    )
    clock.value = 10
    assert isinstance(
        await store.claim(make_scope(key="boundary"), lease_ttl=5), IdempotencyClaimed
    )

    assert not await store.complete(first.reservation, b"stale", result_ttl=5)
    assert not await store.abandon(first.reservation)

    abandoned = await store.claim(make_scope(key="abandoned"), lease_ttl=5)
    assert isinstance(abandoned, IdempotencyClaimed)
    assert await store.abandon(abandoned.reservation)
    replacement = await store.claim(make_scope(key="abandoned"), lease_ttl=5)
    assert isinstance(replacement, IdempotencyClaimed)

    clock.value = 10
    expired = await store.claim(make_scope(key="expired"), lease_ttl=5)
    assert isinstance(expired, IdempotencyClaimed)
    clock.value = 14.999
    assert isinstance(
        await store.claim(make_scope(key="expired"), lease_ttl=5), IdempotencyInProgress
    )
    clock.value = 15
    expired_replacement = await store.claim(make_scope(key="expired"), lease_ttl=5)
    assert isinstance(expired_replacement, IdempotencyClaimed)
    assert not await store.complete(expired.reservation, b"stale", result_ttl=5)

    limited = factory(clock, 1)
    limited_first = await limited.claim(make_scope(key="capacity-a"), lease_ttl=5)
    assert isinstance(limited_first, IdempotencyClaimed)
    assert await limited.abandon(limited_first.reservation)
    reclaimed = await limited.claim(make_scope(key="capacity-b"), lease_ttl=5)
    assert isinstance(reclaimed, IdempotencyClaimed)
    assert await limited.complete(reclaimed.reservation, b"retained", result_ttl=5)
    try:
        await limited.claim(make_scope(key="capacity-c"), lease_ttl=5)
    except IdempotencyStorageError:
        pass
    else:
        raise AssertionError("a completed record must consume the configured capacity")
    clock.value = 20
    expired_capacity = await limited.claim(make_scope(key="capacity-c"), lease_ttl=5)
    assert isinstance(expired_capacity, IdempotencyClaimed)

    outcomes = await asyncio.gather(
        *(store.claim(make_scope(key="concurrent"), lease_ttl=5) for _ in range(32))
    )
    assert sum(isinstance(outcome, IdempotencyClaimed) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, IdempotencyInProgress) for outcome in outcomes) == 31
