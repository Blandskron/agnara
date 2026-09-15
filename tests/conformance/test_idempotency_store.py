"""ADR 0089 contract exercised against the bundled reference store."""

from __future__ import annotations

import asyncio

from agnara.execution.idempotency import InMemoryIdempotencyStore
from tests.conformance.idempotency_store import assert_idempotency_store_conforms


def test_in_memory_store_satisfies_the_reusable_idempotency_port_contract() -> None:
    asyncio.run(
        assert_idempotency_store_conforms(lambda clock: InMemoryIdempotencyStore(clock=clock))
    )
