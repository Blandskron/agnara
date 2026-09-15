"""The operational idempotency storage contract (ADR 0089)."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from agnara.capability import CapabilityId
from agnara.errors import DefinitionError
from agnara.execution.idempotency import (
    IdempotencyClaimed,
    IdempotencyCompleted,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyScope,
    IdempotencyStorageError,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    _Record,
)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def scope(
    *,
    capability: str = "payments.capture",
    principal: str = "customer-1",
    key: str = "payment-1",
    fingerprint: bytes = b"request-a",
) -> IdempotencyScope:
    return IdempotencyScope(CapabilityId.parse(capability), principal, key, fingerprint)


def test_first_claim_completes_and_reuses_only_the_stored_success() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore()
        requested = scope()

        first = await store.claim(requested, lease_ttl=30)
        assert isinstance(first, IdempotencyClaimed)
        assert await store.complete(first.reservation, b'{"status":"captured"}', result_ttl=60)

        reused = await store.claim(requested, lease_ttl=30)
        assert isinstance(reused, IdempotencyCompleted)
        assert reused.execution_id == first.reservation.execution_id
        assert reused.result == b'{"status":"captured"}'

    asyncio.run(run())


def test_duplicate_claim_is_in_progress_and_never_check_then_set() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore()
        requested = scope()

        outcomes = await asyncio.gather(*(store.claim(requested, lease_ttl=30) for _ in range(40)))

        claimed = [outcome for outcome in outcomes if isinstance(outcome, IdempotencyClaimed)]
        in_progress = [
            outcome for outcome in outcomes if isinstance(outcome, IdempotencyInProgress)
        ]
        assert len(claimed) == 1
        assert len(in_progress) == 39
        assert {outcome.execution_id for outcome in in_progress} == {
            claimed[0].reservation.execution_id
        }

    asyncio.run(run())


def test_lookup_detects_fingerprint_conflict_without_disclosing_the_existing_record() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore()
        await store.claim(scope(), lease_ttl=30)

        conflict = await store.lookup(scope(fingerprint=b"request-b"))
        assert isinstance(conflict, IdempotencyConflict)
        assert repr(conflict) == "IdempotencyConflict()"

    asyncio.run(run())


def test_capability_and_principal_are_separate_idempotency_namespaces() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore()

        first = await store.claim(scope(), lease_ttl=30)
        other_key = await store.claim(scope(key="payment-2"), lease_ttl=30)
        other_capability = await store.claim(scope(capability="orders.capture"), lease_ttl=30)
        other_principal = await store.claim(scope(principal="customer-2"), lease_ttl=30)

        assert isinstance(first, IdempotencyClaimed)
        assert isinstance(other_key, IdempotencyClaimed)
        assert isinstance(other_capability, IdempotencyClaimed)
        assert isinstance(other_principal, IdempotencyClaimed)
        assert (
            len(
                {
                    first.reservation.execution_id,
                    other_key.reservation.execution_id,
                    other_capability.reservation.execution_id,
                    other_principal.reservation.execution_id,
                }
            )
            == 4
        )

    asyncio.run(run())


def test_failure_or_cancellation_abandons_the_reservation_for_a_later_explicit_attempt() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore()
        requested = scope()
        first = await store.claim(requested, lease_ttl=30)
        assert isinstance(first, IdempotencyClaimed)

        assert await store.abandon(first.reservation)
        replacement = await store.claim(requested, lease_ttl=30)
        assert isinstance(replacement, IdempotencyClaimed)
        assert replacement.reservation.execution_id != first.reservation.execution_id

    asyncio.run(run())


def test_expiry_releases_in_progress_and_completed_entries_for_deterministic_cleanup() -> None:
    async def run() -> None:
        clock = Clock()
        store = InMemoryIdempotencyStore(max_entries=1, clock=clock)
        requested = scope()
        first = await store.claim(requested, lease_ttl=5)
        assert isinstance(first, IdempotencyClaimed)

        clock.value = 5
        after_lease_expiry = await store.claim(requested, lease_ttl=5)
        assert isinstance(after_lease_expiry, IdempotencyClaimed)
        assert await store.complete(after_lease_expiry.reservation, b"ok", result_ttl=5)

        clock.value = 10
        after_result_expiry = await store.claim(scope(key="payment-2"), lease_ttl=5)
        assert isinstance(after_result_expiry, IdempotencyClaimed)

    asyncio.run(run())


def test_only_the_current_reservation_can_complete_or_abandon_after_expiry() -> None:
    async def run() -> None:
        clock = Clock()
        store = InMemoryIdempotencyStore(clock=clock)
        requested = scope()
        first = await store.claim(requested, lease_ttl=5)
        assert isinstance(first, IdempotencyClaimed)

        clock.value = 5
        replacement = await store.claim(requested, lease_ttl=5)
        assert isinstance(replacement, IdempotencyClaimed)
        assert not await store.complete(first.reservation, b"stale", result_ttl=5)
        assert not await store.abandon(first.reservation)
        assert await store.complete(replacement.reservation, b"current", result_ttl=5)

    asyncio.run(run())


def test_capacity_failure_is_explicit_and_expired_entries_make_space() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore(max_entries=1)
        await store.claim(scope(), lease_ttl=30)

        with pytest.raises(IdempotencyStorageError, match="capacity"):
            await store.claim(scope(key="payment-2"), lease_ttl=30)

    asyncio.run(run())


def test_expired_entries_are_collected_before_capacity_is_checked_for_many_keys() -> None:
    async def run() -> None:
        clock = Clock()
        store = InMemoryIdempotencyStore(max_entries=3, clock=clock)
        for index in range(3):
            claimed = await store.claim(scope(key=f"payment-{index}"), lease_ttl=5)
            assert isinstance(claimed, IdempotencyClaimed)

        clock.value = 4.999
        with pytest.raises(IdempotencyStorageError, match="capacity"):
            await store.claim(scope(key="payment-before-expiry"), lease_ttl=5)

        clock.value = 5
        for index in range(3):
            replacement = await store.claim(scope(key=f"replacement-{index}"), lease_ttl=5)
            assert isinstance(replacement, IdempotencyClaimed)

    asyncio.run(run())


def test_a_third_party_store_can_satisfy_the_port_without_runtime_internals() -> None:
    class ThirdPartyStore:
        async def claim(self, scope: IdempotencyScope, *, lease_ttl: float) -> IdempotencyConflict:
            return IdempotencyConflict()

        async def lookup(self, scope: IdempotencyScope) -> None:
            return None

        async def complete(self, reservation: object, result: bytes, *, result_ttl: float) -> bool:
            return False

        async def abandon(self, reservation: object) -> bool:
            return False

    assert isinstance(ThirdPartyStore(), IdempotencyStore)


@pytest.mark.parametrize("key", ["", "has a space", "café", "a" * 129])
def test_untrusted_keys_are_bounded_opaque_ascii_tokens(key: str) -> None:
    with pytest.raises(DefinitionError, match="idempotency key"):
        scope(key=key)


def test_fingerprints_and_results_are_bounded_and_not_implicitly_serialized() -> None:
    with pytest.raises(DefinitionError, match="fingerprint"):
        scope(fingerprint=b"")

    async def run() -> None:
        store = InMemoryIdempotencyStore()
        claim = await store.claim(scope(), lease_ttl=30)
        assert isinstance(claim, IdempotencyClaimed)
        with pytest.raises(TypeError, match="result must be bytes"):
            await store.complete(claim.reservation, cast("bytes", "not bytes"), result_ttl=30)

    asyncio.run(run())


def test_incompatible_stored_state_fails_closed_without_an_assertion() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore(clock=lambda: 0.0)
        requested = scope()
        store._records[(requested.capability_id, requested.principal_id, requested.key)] = _Record(
            fingerprint=requested.fingerprint,
            execution_id="e" * 32,
            token=None,
            expires_at=30,
            result=None,
        )

        with pytest.raises(IdempotencyStorageError, match="incompatible state"):
            await store.lookup(requested)

    asyncio.run(run())


def test_synchronized_claims_have_one_owner_and_one_conflict() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore()
        barrier = asyncio.Barrier(2)

        async def claim(requested: IdempotencyScope) -> object:
            await barrier.wait()
            return await store.claim(requested, lease_ttl=30)

        outcomes = await asyncio.gather(
            claim(scope()),
            claim(scope(fingerprint=b"request-b")),
        )

        assert sum(isinstance(outcome, IdempotencyClaimed) for outcome in outcomes) == 1
        assert sum(isinstance(outcome, IdempotencyConflict) for outcome in outcomes) == 1

    asyncio.run(run())


def test_synchronized_distinct_claims_fail_closed_under_capacity_pressure() -> None:
    async def run() -> None:
        store = InMemoryIdempotencyStore(max_entries=1)
        barrier = asyncio.Barrier(2)

        async def claim(requested: IdempotencyScope) -> object:
            await barrier.wait()
            try:
                return await store.claim(requested, lease_ttl=30)
            except IdempotencyStorageError as error:
                return error

        outcomes = await asyncio.gather(
            claim(scope(key="capacity-a")),
            claim(scope(key="capacity-b")),
        )

        assert sum(isinstance(outcome, IdempotencyClaimed) for outcome in outcomes) == 1
        assert sum(isinstance(outcome, IdempotencyStorageError) for outcome in outcomes) == 1

    asyncio.run(run())
